"""
Login: quem pode entrar no sistema e como a sessão é protegida.

O que este módulo garante:
  - toda rota exige login (exigir_login), menos /login e os arquivos estáticos;
  - a senha só existe como hash (scrypt, do Werkzeug) — nem o banco guarda a senha;
  - 5 senhas erradas seguidas bloqueiam o usuário por 10 minutos;
  - o login vale no máximo 10 horas (não renova sozinho, mesmo com a tela aberta);
  - trocar a senha derruba as outras sessões abertas desse usuário;
  - as páginas não ficam guardadas no cache do navegador (botão "voltar" após sair).

Não existe tela de cadastro, de propósito: quem cria usuários é quem administra.

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
from datetime import datetime, timedelta
from pathlib import Path

import click
from flask import g, jsonify, redirect, request, session, url_for
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from modelos import Usuario, db

log = logging.getLogger(__name__)

SENHA_MINIMA = 10
MAX_FALHAS = 5
BLOQUEIO = timedelta(minutes=10)
DURACAO_LOGIN = timedelta(hours=10)
ROTAS_LIVRES = {"login", "static"}
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


def validar_senha(senha):
    if len(senha or "") < SENHA_MINIMA:
        return f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres."
    return None


def criar_usuario(nome, senha):
    """Devolve (usuario, erro)."""
    nome = (nome or "").strip().lower()
    if not nome:
        return None, "Informe o nome do usuário."
    if len(nome) > 50:
        return None, "O nome do usuário pode ter até 50 caracteres."
    if _buscar(nome):
        return None, f"O usuário {nome} já existe."
    if erro := validar_senha(senha):
        return None, erro
    usuario = Usuario(nome=nome, senha_hash=generate_password_hash(senha))
    db.session.add(usuario)
    db.session.commit()
    return usuario, None


def definir_senha(usuario, senha):
    """Troca a senha, desbloqueia o usuário e derruba as sessões antigas. Devolve o erro, se houver."""
    if erro := validar_senha(senha):
        return erro
    usuario.senha_hash = generate_password_hash(senha)
    usuario.falhas, usuario.bloqueado_ate, usuario.ativo = 0, None, True
    db.session.commit()
    return None


def trocar_senha(usuario, atual, nova, confirmacao):
    """Tela 'Alterar minha senha'. Devolve o erro, se houver."""
    if not check_password_hash(usuario.senha_hash, atual or ""):
        return "A senha atual não confere."
    if nova != confirmacao:
        return "A confirmação não é igual à senha nova."
    if nova == atual:
        return "A senha nova precisa ser diferente da atual."
    return definir_senha(usuario, nova)


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
def entrar(nome, senha):
    """Confere usuário e senha. Devolve (usuario, erro). A mensagem de erro é a mesma para
    usuário inexistente e senha errada, para não revelar quem tem cadastro."""
    usuario = _buscar(nome)
    agora = datetime.now()
    if usuario and usuario.bloqueado_ate and usuario.bloqueado_ate > agora:
        minutos = math.ceil((usuario.bloqueado_ate - agora).total_seconds() / 60)
        return None, f"Muitas tentativas erradas. Tente de novo em {minutos} min."

    confere = check_password_hash(usuario.senha_hash if usuario else _HASH_FALSO, senha or "")
    if not (usuario and usuario.ativo and confere):
        if usuario:
            usuario.falhas += 1
            if usuario.falhas >= MAX_FALHAS:
                usuario.falhas, usuario.bloqueado_ate = 0, agora + BLOQUEIO
            db.session.commit()
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
    session.permanent = True


def usuario_da_sessao():
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return None
    usuario = db.session.get(Usuario, usuario_id)
    if not usuario or not usuario.ativo or session.get("versao") != _versao(usuario):
        session.clear()
        return None
    return usuario


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
    if g.usuario or request.endpoint in ROTAS_LIVRES:
        return None
    if request.path.startswith("/api/") or request.is_json:
        # chamadas do JavaScript: responde em JSON (o formato de erro é o que a tela já espera)
        return jsonify(ok=False, erros={"sessao": "Sessão expirada. Entre de novo."}), 401
    destino = request.path + ("?" + request.query_string.decode() if request.query_string else "")
    return redirect(url_for("login", next=destino if request.method == "GET" else None))


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
