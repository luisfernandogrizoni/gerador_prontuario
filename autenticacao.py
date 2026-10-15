"""
Login: quem pode entrar no sistema e como a sessão é protegida.

O que este módulo garante:
  - toda rota exige login (exigir_login), menos as páginas de entrada (ROTAS_LIVRES) e os arquivos estáticos;
  - a senha só existe como hash (scrypt, do Werkzeug) — nem o banco guarda a senha — e não pode ser das fáceis de adivinhar
    (senhas_fracas.py: as mais usadas, o nome da casa, o usuário e o nome da pessoa);
  - a senha que o administrador define (criar usuário, redefinir) é provisória: a pessoa troca antes de usar qualquer outra tela;
  - 5 senhas erradas seguidas bloqueiam o usuário por 10 minutos, e 15 erradas vindas do mesmo computador em 10 minutos
    bloqueiam aquele computador (o atacante que troca de usuário a cada 5 erros também para);
  - quem ativou o segundo fator (aplicativo autenticador, contas.py e totp.py) digita também o código depois da senha;
  - o login vale no máximo 10 horas e **sai sozinho depois de 30 minutos sem uso** (a página avisa antes, com um pop-up);
  - trocar a senha derruba as outras sessões abertas desse usuário;
  - as páginas não ficam guardadas no cache do navegador (botão "voltar" após sair).

Não existe tela pública de cadastro, de propósito: quem cria usuários e define senhas é o administrador, em
Cadastros > Funcionários (veja cadastros.pode_gerenciar_acessos). O terminal continua servindo para o primeiro
usuário e para quem ficar sem nenhum administrador:

    flask --app app criar-usuario maria           pede a senha e cria
    flask --app app redefinir-senha maria         pede a senha nova (e desbloqueia)

Hospedagem sem terminal: defina ADMIN_USUARIO e ADMIN_SENHA no painel do serviço.
Se ainda não houver NENHUM usuário, o sistema cria esse na inicialização (depois de
entrar, pode apagar ADMIN_SENHA do painel — ela não é mais usada).
Defina também SECRET_KEY (um texto longo e aleatório) para as sessões não caírem
a cada reinício.
"""

import hashlib
import logging
import math
import os
import secrets
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import click
from flask import g, has_request_context, jsonify, redirect, request, session, url_for
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

import auditoria
import senhas_fracas
from modelos import Usuario, db

log = logging.getLogger(__name__)

SENHA_MINIMA = 10
MAX_FALHAS = 5
BLOQUEIO = timedelta(minutes=10)
DURACAO_LOGIN = timedelta(hours=10)
OCIOSO = timedelta(minutes=30)                 # sem usar o sistema por este tempo, a sessão acaba (a página avisa 5 minutos antes)
AVISO_DE_OCIOSO = timedelta(minutes=25)
LIMITE_POR_ENDERECO = 15                       # senhas ou códigos errados vindos do mesmo computador...
JANELA_POR_ENDERECO = timedelta(minutes=10)    # ...nesta janela de tempo bloqueiam aquele computador
VALIDADE_DO_CODIGO = 300                       # segundos para digitar o código do autenticador depois de acertar a senha
# páginas que funcionam sem a pessoa ter entrado (e o que ela pode abrir com a senha provisória, antes de trocá-la)
ROTAS_LIVRES = {"login", "static", "login_codigo", "esqueci_senha", "redefinir_senha"}
ROTAS_COM_SENHA_PROVISORIA = {"alterar_senha", "sair", "sessao_ping", "static"}
COMANDOS_DE_USUARIO = {"criar-usuario", "redefinir-senha"}
# hash de uma senha qualquer: testar um usuário que não existe gasta o mesmo tempo
# que testar um que existe (sem isso, o tempo de resposta revelaria quem existe)
_HASH_FALSO = generate_password_hash(secrets.token_hex(8))


# ------------------------------------------------------------------ chave da sessão
def chave_secreta(pasta_instance):
    """SECRET_KEY do ambiente; sem ela, uma chave aleatória guardada em instance/."""
    chave = os.environ.get("SECRET_KEY")
    if chave:
        return chave
    arquivo = Path(pasta_instance) / "secret.key"
    if not arquivo.exists():
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(secrets.token_hex(32))
    return arquivo.read_text().strip()


# ------------------------------------------------------------------ usuários
def _buscar(nome):
    nome = (nome or "").strip().lower()
    return db.session.execute(db.select(Usuario).filter_by(nome=nome)).scalar_one_or_none()


buscar_usuario = _buscar


def validar_senha(senha, nomes=()):
    """O motivo de a senha não servir (curta demais, ou fácil de adivinhar: senhas_fracas.py), ou None. `nomes`: o usuário e o nome da pessoa."""
    if len(senha or "") < SENHA_MINIMA:
        return f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres."
    return senhas_fracas.senha_fraca(senha, nomes)


def validar_nome_de_usuario(nome):
    """Devolve o erro, se houver (o nome é sempre guardado em minúsculas)."""
    nome = (nome or "").strip().lower()
    if not nome:
        return "Informe o nome do usuário."
    if len(nome) > 50:
        return "O nome do usuário pode ter até 50 caracteres."
    if _buscar(nome):
        return f"O usuário {nome} já existe."
    return None


def criar_usuario(nome, senha, confirmar=True, provisoria=False, nomes=()):
    """Devolve (usuario, erro). `confirmar=False` deixa a gravação para quem chamou (cadastro de funcionário:
    o usuário e o funcionário são gravados juntos, ou nenhum dos dois). `provisoria`: a senha foi o administrador que definiu, e a
    pessoa tem de trocá-la antes de usar o sistema."""
    if erro := validar_nome_de_usuario(nome):
        return None, erro
    if erro := validar_senha(senha, [nome, *nomes]):
        return None, erro
    usuario = Usuario(nome=(nome or "").strip().lower(), senha_hash=generate_password_hash(senha), trocar_senha=provisoria)
    db.session.add(usuario)
    if confirmar:
        db.session.commit()
    return usuario, None


def definir_senha(usuario, senha, confirmar=True, provisoria=False, nomes=()):
    """Troca a senha, desbloqueia o usuário e derruba as sessões antigas. Devolve o erro, se houver. `provisoria`: veja criar_usuario."""
    if erro := validar_senha(senha, [usuario.nome, *nomes]):
        return erro
    usuario.senha_hash = generate_password_hash(senha)
    usuario.falhas, usuario.bloqueado_ate, usuario.ativo, usuario.trocar_senha = 0, None, True, provisoria
    if confirmar:
        db.session.commit()
    return None


def trocar_senha(usuario, atual, nova, confirmacao, nomes=()):
    """Tela 'Alterar minha senha'. Devolve o erro, se houver. A senha nova é sempre a da própria pessoa (não é mais provisória)."""
    if not check_password_hash(usuario.senha_hash, atual or ""):
        return "A senha atual não confere."
    if nova != confirmacao:
        return "A confirmação não é igual à senha nova."
    if nova == atual:
        return "A senha nova precisa ser diferente da atual."
    return definir_senha(usuario, nova, nomes=nomes)


def criar_usuario_inicial():
    """Roda na inicialização: cria o usuário de ADMIN_USUARIO/ADMIN_SENHA se não houver nenhum."""
    if db.session.execute(db.select(db.func.count(Usuario.id))).scalar():
        return
    nome, senha = os.environ.get("ADMIN_USUARIO"), os.environ.get("ADMIN_SENHA")
    if not (nome and senha):
        if COMANDOS_DE_USUARIO & set(sys.argv):
            return    # quem está criando o usuário agora não precisa do aviso "crie um usuário"
        log.warning("Nenhum usuário cadastrado: ninguém consegue entrar. "
                    "Crie um com: flask --app app criar-usuario NOME")
        return
    try:
        _, erro = criar_usuario(nome, senha)
    except IntegrityError:   # outro processo do servidor criou no mesmo instante
        db.session.rollback()
        return
    if erro:
        log.warning("ADMIN_USUARIO/ADMIN_SENHA não foram usados: %s", erro)


# ------------------------------------------------------------------ entrar
def _endereco():
    return (request.remote_addr or "") if has_request_context() else ""


def registrar_falha(usuario, acao="login.falha"):
    """Uma senha ou um código errado de um usuário que existe: soma, bloqueia na quinta (10 minutos) e registra na trilha."""
    usuario.falhas += 1
    bloqueou = usuario.falhas >= MAX_FALHAS
    if bloqueou:
        usuario.falhas, usuario.bloqueado_ate = 0, datetime.now() + BLOQUEIO
    db.session.commit()
    auditoria.registrar("login.bloqueio" if bloqueou else acao, usuario=usuario.nome)
    return bloqueou


def entrar(nome, senha):
    """Confere usuário e senha. Devolve (usuario, erro). A mensagem de erro é a mesma para
    usuário inexistente e senha errada, para não revelar quem tem cadastro."""
    usuario = _buscar(nome)
    agora = datetime.now()
    endereco = _endereco()
    if endereco and auditoria.falhas_do_endereco(endereco, agora - JANELA_POR_ENDERECO) >= LIMITE_POR_ENDERECO:
        auditoria.registrar("login.bloqueado_endereco", usuario=usuario.nome if usuario else "")
        return None, "Muitas tentativas erradas vindas deste computador. Espere alguns minutos e tente de novo."
    if usuario and usuario.bloqueado_ate and usuario.bloqueado_ate > agora:
        minutos = math.ceil((usuario.bloqueado_ate - agora).total_seconds() / 60)
        auditoria.registrar("login.bloqueado", usuario=usuario.nome)
        return None, f"Muitas tentativas erradas. Tente de novo em {minutos} min."

    confere = check_password_hash(usuario.senha_hash if usuario else _HASH_FALSO, senha or "")
    if not (usuario and usuario.ativo and confere):
        if usuario:
            registrar_falha(usuario)
        else:
            auditoria.registrar("login.inexistente", usuario="")       # (o que foi digitado como usuário não é guardado: pode ser uma senha no campo errado)
        return None, "Usuário ou senha incorretos."

    usuario.falhas, usuario.bloqueado_ate = 0, None
    db.session.commit()
    return usuario, None


# ------------------------------------------------------------------ sessão
def _versao(usuario):
    """Muda quando a senha muda. Vai na sessão para invalidar as sessões antigas;
    é um resumo do hash, para o cookie (que o usuário consegue ler) não expor o hash."""
    return hashlib.sha256(usuario.senha_hash.encode()).hexdigest()[:16]


def abrir_sessao(usuario):
    session.clear()    # nunca reaproveita uma sessão que veio de antes do login
    session["usuario_id"] = usuario.id
    session["versao"] = _versao(usuario)
    session["inicio"] = session["ultimo_uso"] = time.time()
    session.permanent = True


def usuario_da_sessao():
    """O usuário da sessão, ou None. A sessão acaba por inatividade (OCIOSO) e no máximo em DURACAO_LOGIN; cada pedido conta como uso.
    Quando acaba por tempo, `g.sessao_encerrada` diz qual foi o motivo (a página de entrada explica)."""
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return None
    agora = time.time()
    if agora - session.get("ultimo_uso", agora) > OCIOSO.total_seconds():
        g.sessao_encerrada, g.sessao_de = "ocioso", usuario_id
        session.clear()
        return None
    if agora - session.get("inicio", agora) > DURACAO_LOGIN.total_seconds():
        g.sessao_encerrada, g.sessao_de = "duracao", usuario_id
        session.clear()
        return None
    usuario = db.session.get(Usuario, usuario_id)
    if not usuario or not usuario.ativo or session.get("versao") != _versao(usuario):
        session.clear()
        return None
    session.setdefault("inicio", agora)
    if request.headers.get("X-Atualizacao-Automatica") != "1":      # a lista que se atualiza sozinha não conta como uso (static/tabela.js)
        session["ultimo_uso"] = agora
    return usuario


# ---- entrar em duas etapas: a senha certa leva à página do código; só o código certo abre a sessão
def iniciar_segundo_fator(usuario, proximo=""):
    session.clear()
    session["mfa"] = {"uid": usuario.id, "ate": time.time() + VALIDADE_DO_CODIGO, "tentativas": 0, "proximo": proximo, "versao": _versao(usuario)}


def usuario_aguardando_codigo():
    """O usuário que acertou a senha e ainda não digitou o código (e a espera não venceu), ou None."""
    espera = session.get("mfa")
    if not espera or time.time() > espera.get("ate", 0):
        session.pop("mfa", None)
        return None
    usuario = db.session.get(Usuario, espera["uid"])
    bloqueado = usuario and usuario.bloqueado_ate and usuario.bloqueado_ate > datetime.now()
    if not usuario or not usuario.ativo or not usuario.totp_ativo or bloqueado or espera.get("versao") != _versao(usuario):
        session.pop("mfa", None)
        return None
    return usuario


def errou_o_codigo():
    """Soma um código errado nesta espera. Devolve quantos já foram (acima de 5, a espera acaba)."""
    espera = session["mfa"]
    espera["tentativas"] += 1
    session["mfa"] = espera
    return espera["tentativas"]


def destino_seguro(destino, padrao):
    """Para onde ir depois do login (?next=...): só caminhos deste site, nunca outro endereço."""
    if (destino and destino.startswith("/") and not destino.startswith("//")
            and "\\" not in destino):
        return destino
    return padrao


# ------------------------------------------------------------------ ganchos do Flask
def exigir_login():
    """before_request: barra qualquer rota (inclusive as de dados) sem usuário logado."""
    if request.endpoint == "static":
        return None
    g.usuario = usuario_da_sessao()
    if g.get("sessao_encerrada"):
        antigo = db.session.get(Usuario, g.sessao_de)
        auditoria.registrar("sessao.expirada", usuario=antigo.nome if antigo else "", detalhe="sem uso por 30 minutos" if g.sessao_encerrada == "ocioso" else "passou de 10 horas")
    if g.usuario and g.usuario.trocar_senha and request.endpoint not in ROTAS_COM_SENHA_PROVISORIA:
        if request.path.startswith("/api/") or request.is_json:
            return jsonify(ok=False, erros={"senha": "Troque a senha provisória antes de continuar."}), 403
        return redirect(url_for("alterar_senha"))
    if g.usuario or request.endpoint in ROTAS_LIVRES:
        return None
    if request.path.startswith("/api/") or request.is_json:
        # chamadas do JavaScript: responde em JSON (o formato de erro é o que a tela já espera)
        motivo = "Sessão encerrada por falta de uso. Entre de novo." if g.get("sessao_encerrada") == "ocioso" else "Sessão expirada. Entre de novo."
        return jsonify(ok=False, erros={"sessao": motivo}), 401
    destino = request.path + ("?" + request.query_string.decode() if request.query_string else "")
    return redirect(url_for("login", next=destino if request.method == "GET" else None, encerrada="ocioso" if g.get("sessao_encerrada") == "ocioso" else None))


def cabecalhos_de_seguranca(resposta):
    """after_request: nada de cache das páginas e proteção contra rodar dentro de outro site."""
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "same-origin"
    if request.endpoint != "static":
        resposta.headers["Cache-Control"] = "no-store"
    return resposta


# ------------------------------------------------------------------ comandos do terminal
def _pedir_senha(rotulo, visivel):
    """Pede a senha duas vezes. Escondida por padrão: nada aparece enquanto se digita."""
    if visivel:
        click.echo(f"Digite a senha (mínimo {SENHA_MINIMA} caracteres) e tecle Enter. "
                   "Ela APARECE na tela. Depois repita para confirmar.")
    else:
        click.echo(f"Digite a senha (mínimo {SENHA_MINIMA} caracteres) e tecle Enter. Ela NÃO "
                   "aparece na tela enquanto você digita (é normal). Depois repita para confirmar.\n"
                   "Se o terminal não aceitar a digitação escondida, rode de novo com --visivel.")
    return click.prompt(rotulo, hide_input=not visivel, confirmation_prompt=True)


def registrar_comandos(app):
    @app.cli.command("criar-usuario")
    @click.argument("nome")
    @click.option("--visivel", is_flag=True, help="mostra a senha enquanto você digita")
    def criar_usuario_cmd(nome, visivel):
        """Cria um usuário (a senha é pedida na hora)."""
        senha = _pedir_senha("Senha", visivel)
        usuario, erro = criar_usuario(nome, senha)
        if erro:
            raise click.ClickException(erro)
        click.echo(f"Usuário {usuario.nome} criado.")

    @app.cli.command("redefinir-senha")
    @click.argument("nome")
    @click.option("--visivel", is_flag=True, help="mostra a senha enquanto você digita")
    def redefinir_senha_cmd(nome, visivel):
        """Define uma senha nova para um usuário (e tira o bloqueio, se houver)."""
        usuario = _buscar(nome)
        if not usuario:
            raise click.ClickException(f"O usuário {nome} não existe.")
        senha = _pedir_senha("Senha nova", visivel)
        if erro := definir_senha(usuario, senha):
            raise click.ClickException(erro)
        click.echo(f"Senha de {usuario.nome} alterada.")
