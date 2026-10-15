"""
Trilha de auditoria (plano de segurança, fase 2: docs/plano-de-seguranca.md).

Responde, depois do fato, "quem abriu, alterou, baixou ou apagou isto, e quando?". Cada ação vira uma linha em
`eventos_auditoria` (modelos.Evento) com quem fez (o login), o quê (um código, com o texto em palavras em ACOES), em qual
registro (o acolhido e/ou o objeto), o endereço de rede e o navegador.

Regras:

  * **Só se acrescenta.** Nenhuma tela edita nem apaga evento; a tela Cadastros > Auditoria só lê e exporta.
  * **Sem o conteúdo.** Registra *qual* campo mudou, nunca o valor; não guarda o que foi digitado numa busca, nem o usuário
    digitado em um login que não existe, nem senha. O nome do acolhido aparece na tela, vindo do cadastro (não é copiado para
    cá), então um registro apagado de vez deixa só o número.
  * **Registrar nunca derruba a tela.** Falha ao gravar vai para o registro do servidor (logs/servidor.log) e a ação segue.
  * **Tudo está classificado.** Cada rota está em LEITURAS (registrada aqui, depois da resposta), em EXPLICITAS (registrada
    no ponto exato em que a ação deu certo) ou em NAO_REGISTRA (com o motivo); um teste confere que nenhuma ficou de fora.
  * Leituras só contam quando a resposta foi 200; alterações só quando a ação **deu certo** (um formulário recusado não vira
    "alterou").

Limite: quem controla o computador e o banco consegue mexer na tabela. A trilha protege contra o uso indevido pelo sistema,
não contra o dono da máquina; os backups (que levam a tabela) permitem comparar.
"""

import csv
import io
import logging
from datetime import date, datetime, time, timedelta

from flask import g, has_request_context, request
from sqlalchemy import distinct, func

import exclusao
from modelos import Evento, Funcionario, Internacao, Pessoa, db

log = logging.getLogger(__name__)

CATEGORIAS = {"entrada": "Entradas", "leitura": "Leituras", "alteracao": "Alterações", "administracao": "Administração", "negado": "Acessos negados"}

# código: (categoria, o que aconteceu, em palavras)
ACOES = {
    # ---- entradas
    "login.ok": ("entrada", "Entrou no sistema"),
    "login.falha": ("entrada", "Tentativa de entrada com a senha errada"),
    "login.inexistente": ("entrada", "Tentativa de entrada com um usuário que não existe"),
    "login.bloqueado": ("entrada", "Tentativa de entrada durante o bloqueio"),
    "login.bloqueio": ("entrada", "Usuário bloqueado por senhas erradas seguidas"),
    "login.codigo_errado": ("entrada", "Código do aplicativo autenticador errado"),
    "login.bloqueado_endereco": ("entrada", "Entrada bloqueada: muitas tentativas erradas vindas deste computador"),
    "sessao.expirada": ("entrada", "Sessão encerrada (sem uso por 30 minutos, ou mais de 10 horas)"),
    "senha.pedido_reset": ("entrada", "Pediu para redefinir a senha pelo e-mail"),
    "login.desativado": ("entrada", "Entrada recusada: o funcionário está desativado"),
    "sair": ("entrada", "Saiu do sistema"),
    "sessao.derrubada": ("entrada", "Sessão derrubada: o funcionário foi desativado"),
    # ---- leituras
    "ver.ficha": ("leitura", "Abriu a ficha"),
    "ver.edicao": ("leitura", "Abriu o formulário de edição"),
    "ver.pessoa_no_formulario": ("leitura", "Abriu um formulário com os dados de um acolhido já cadastrado"),
    "ver.acolhimento": ("leitura", "Abriu o acolhimento social"),
    "ver.lista": ("leitura", "Carregou a lista de acolhidos"),
    "busca.pessoa": ("leitura", "Buscou um acolhido pelo nome"),
    "doc.ver": ("leitura", "Abriu um documento"),
    "doc.imprimir": ("leitura", "Mandou imprimir um documento"),
    "doc.baixar": ("leitura", "Baixou um documento"),
    "relatorio.ver": ("leitura", "Abriu um relatório"),
    "relatorio.baixar": ("leitura", "Baixou um relatório"),
    "ver.lixeira": ("leitura", "Abriu a lixeira"),
    "ver.funcionario": ("leitura", "Abriu o cadastro de um funcionário"),
    "ver.funcionarios": ("leitura", "Abriu a lista de funcionários"),
    "ver.niveis": ("leitura", "Abriu os níveis de acesso"),
    "ver.permissoes": ("leitura", "Abriu as permissões"),
    "ver.backup": ("leitura", "Abriu a situação do backup"),
    "auditoria.ver": ("leitura", "Abriu a trilha de auditoria"),
    "auditoria.exportar": ("leitura", "Baixou a trilha de auditoria"),
    # ---- alterações nos registros dos acolhidos
    "triagem.criar": ("alteracao", "Registrou uma triagem"),
    "triagem.editar": ("alteracao", "Editou uma triagem"),
    "prontuario.criar": ("alteracao", "Registrou um prontuário"),
    "prontuario.editar": ("alteracao", "Editou um prontuário"),
    "status.mudar": ("alteracao", "Mudou a situação de uma triagem"),
    "baixa.dar": ("alteracao", "Deu baixa em um interno"),
    "envelope.registrar": ("alteracao", "Anotou onde está o prontuário em papel"),
    "parcela.lancar": ("alteracao", "Lançou uma parcela"),
    "parcela.excluir": ("alteracao", "Excluiu uma parcela"),
    "pessoa.unificar": ("alteracao", "Unificou dois cadastros"),
    "registro.excluir": ("alteracao", "Excluiu um registro (foi para a lixeira)"),
    "registro.restaurar": ("alteracao", "Restaurou um registro da lixeira"),
    "registro.apagar": ("alteracao", "Apagou um registro do banco, sem volta"),
    "acolhimento.salvar": ("alteracao", "Salvou o rascunho do acolhimento social"),
    "acolhimento.finalizar": ("alteracao", "Finalizou o acolhimento social"),
    "acolhimento.adendo": ("alteracao", "Escreveu um adendo no acolhimento social"),
    "aviso.ciente": ("alteracao", "Tirou um aviso do quadro (ciente)"),
    # ---- administração
    "funcionario.criar": ("administracao", "Cadastrou um funcionário"),
    "funcionario.editar": ("administracao", "Editou o cadastro de um funcionário"),
    "usuario.criar": ("administracao", "Criou um usuário de login"),
    "senha.redefinida": ("administracao", "Definiu uma senha nova para um usuário"),
    "senha.trocada": ("administracao", "Trocou a própria senha"),
    "senha.redefinida_por_email": ("administracao", "Redefiniu a senha pelo link do e-mail"),
    "email.codigo_enviado": ("administracao", "Pediu o código para confirmar o e-mail"),
    "email.confirmado": ("administracao", "Confirmou o e-mail"),
    "totp.ativado": ("administracao", "Ativou o segundo fator (aplicativo autenticador)"),
    "totp.desativado": ("administracao", "Desativou o segundo fator"),
    "totp.recuperacao_usada": ("administracao", "Entrou com um código de recuperação do segundo fator"),
    "nivel.criar": ("administracao", "Criou um nível de acesso"),
    "nivel.editar": ("administracao", "Editou um nível de acesso"),
    "nivel.mover": ("administracao", "Mudou um nível de lugar na cascata"),
    "permissao.alterar": ("administracao", "Mudou o que um nível pode fazer"),
    "convenio.criar": ("administracao", "Cadastrou um convênio"),
    "convenio.editar": ("administracao", "Editou um convênio"),
    # ---- negados
    "acesso.negado": ("negado", "Acesso negado pelo nível de acesso"),
}


# ====================================================================== gravar
def registrar(acao, alvo_tipo="", alvo_id=None, pessoa_id=None, detalhe="", usuario=None):
    """Acrescenta um evento. `usuario` é o login (texto); sem ele, vale quem está logado. Nunca levanta erro."""
    try:
        categoria = ACOES[acao][0]
        com_pedido = has_request_context()
        nome = usuario if usuario is not None else (g.usuario.nome if com_pedido and g.get("usuario") else "")
        valores = {"quando": datetime.now(), "usuario": (nome or "")[:50], "acao": acao, "categoria": categoria, "alvo_tipo": alvo_tipo[:20],
                   "alvo_id": alvo_id, "pessoa_id": pessoa_id, "detalhe": (detalhe or "")[:300],
                   "endereco": (request.remote_addr or "")[:45] if com_pedido else "",
                   "navegador": (request.headers.get("User-Agent") or "")[:120] if com_pedido else ""}
        with db.engine.begin() as conexao:         # uma conexão só dela: não mexe na transação da tela
            conexao.execute(Evento.__table__.insert().values(**valores))
    except Exception:                              # noqa: BLE001 — a trilha nunca derruba a tela
        log.exception("Não consegui gravar o evento de auditoria %s", acao)


def _internacao(id_):
    with exclusao.vendo_tudo():
        return db.session.get(Internacao, id_) if id_ else None


def _da_internacao(acao, detalhe=""):
    """A leitura é de uma ficha: acha o acolhido dela (mesmo se o registro estiver na lixeira)."""
    id_ = (request.view_args or {}).get("id")
    internacao = _internacao(id_)
    return (acao, "internacao", id_, internacao.pessoa_id if internacao else None, detalhe)


def _itens():
    return request.args.get("itens") or "padrão"


# ====================================================================== o que se registra sozinho (leituras, depois da resposta 200)
# endpoint -> função que devolve (acao, alvo_tipo, alvo_id, pessoa_id, detalhe) ou None
LEITURAS = {
    "ficha": lambda: _da_internacao("ver.ficha"),
    "editar_internacao": lambda: _da_internacao("ver.edicao"),
    "relatorio_social": lambda: _da_internacao("ver.acolhimento"),
    "formulario": lambda: ("ver.pessoa_no_formulario", "pessoa", request.args.get("pessoa", type=int), request.args.get("pessoa", type=int), "") if request.args.get("pessoa", type=int) else None,
    "nova_triagem": lambda: ("ver.pessoa_no_formulario", "pessoa", request.args.get("pessoa", type=int), request.args.get("pessoa", type=int), "") if request.args.get("pessoa", type=int) else None,
    "ver_prontuario": lambda: _da_internacao("doc.ver", "prontuário"),
    "ver_declaracao": lambda: _da_internacao("doc.ver", "declaração"),
    "ver_impressos": lambda: _da_internacao("doc.imprimir" if request.args.get("imprimir") else "doc.ver", _itens()),
    "baixar_prontuario": lambda: _da_internacao("doc.baixar", "prontuário"),
    "baixar_declaracao": lambda: _da_internacao("doc.baixar", "declaração"),
    "baixar_impressos": lambda: _da_internacao("doc.baixar", _itens()),
    "pagina_relatorios": lambda: ("relatorio.ver", "", None, None, "painel de relatórios"),
    "ver_relatorio": lambda: ("relatorio.ver", "", None, None, f"internos ativos: {(request.view_args or {}).get('slug', '')}"),
    "baixar_relatorio": lambda: ("relatorio.baixar", "", None, None, f"internos ativos: {(request.view_args or {}).get('slug', '')}"),
    "ver_relatorio_anual": lambda: ("relatorio.ver", "", None, None, "quem passou pela casa no ano"),
    "baixar_relatorio_anual": lambda: ("relatorio.baixar", "", None, None, "quem passou pela casa no ano"),
    "api_triagens": lambda: ("ver.lista", "", None, None, "triagens"),
    "api_internos": lambda: ("ver.lista", "", None, None, "internos"),
    "api_pessoas": lambda: ("busca.pessoa", "", None, None, ""),
    "lixeira": lambda: ("ver.lixeira", "", None, None, ""),
    "lista_funcionarios": lambda: ("ver.funcionarios", "", None, None, ""),
    "editar_funcionario": lambda: ("ver.funcionario", "funcionario", (request.view_args or {}).get("id"), None, ""),
    "lista_niveis": lambda: ("ver.niveis", "", None, None, ""),
    "lista_permissoes": lambda: ("ver.permissoes", "", None, None, ""),
    "pagina_backup": lambda: ("ver.backup", "", None, None, ""),
}

# registradas no ponto exato em que a ação deu certo (app.py, autenticacao.py, permissoes.py)
EXPLICITAS = {
    "login", "sair", "alterar_senha", "aviso_ciente", "unificar_pessoas", "salvar_triagem", "mudar_status", "baixa_interno", "registrar_envelope",
    "gerar", "lancar_parcela", "excluir_parcela", "adendo_social", "excluir_registro", "restaurar_registro", "apagar_registro",
    "novo_convenio", "editar_convenio", "novo_funcionario", "novo_nivel", "editar_nivel", "mover_nivel", "salvar_permissoes",
    "pagina_auditoria", "exportar_auditoria", "login_codigo", "esqueci_senha", "redefinir_senha", "enviar_codigo_email", "confirmar_email",
    "ativar_autenticador", "desativar_autenticador",
}

# o que não se registra, e por quê
NAO_REGISTRA = {
    "static": "arquivos do próprio sistema (imagens, estilos, scripts)",
    "home": "o Início é um resumo; o que ele leva a abrir (fichas, listas, documentos) é registrado quando abre",
    "lista_triagens": "só a página vazia; a lista chega pela API, que é registrada",
    "lista_internos": "só a página vazia; a lista chega pela API, que é registrada",
    "cadastros": "redireciona para a lista de convênios",
    "lista_convenios": "convênios não são dado pessoal",
    "relatorio_de_rejeicao": "redireciona para o acolhimento social, que é registrado",
    "seguranca": "a página da própria pessoa (as ações dela são registradas quando acontecem)",
    "sessao_ping": "só avisa que a pessoa continua usando o sistema (renova o tempo de inatividade)",
}


def depois_da_requisicao(resposta):
    """after_request: registra a leitura (GET com resposta 200) das rotas de LEITURAS. Só registra quem está logado."""
    try:
        if resposta.status_code == 200 and request.method == "GET" and g.get("usuario") is not None:
            regra = LEITURAS.get(request.endpoint or "")
            dados = regra() if regra else None
            if dados:
                acao, alvo_tipo, alvo_id, pessoa_id, detalhe = dados
                registrar(acao, alvo_tipo, alvo_id, pessoa_id, detalhe)
    except Exception:                              # noqa: BLE001
        log.exception("Falha ao registrar a leitura de %s", request.endpoint)
    return resposta


def endpoints_sem_classificacao(app):
    """Rotas que não estão em LEITURAS, EXPLICITAS nem NAO_REGISTRA: o teste exige que seja vazio."""
    todas = {r.endpoint for r in app.url_map.iter_rules()}
    return sorted(todas - set(LEITURAS) - EXPLICITAS - set(NAO_REGISTRA))


# ====================================================================== a tela Cadastros > Auditoria
POR_PAGINA = 50
LIMITE_DO_CSV = 20000


def falhas_do_endereco(endereco, desde):
    """Quantas senhas ou códigos errados vieram deste endereço de rede desde `desde` (o limite por computador da entrada)."""
    return db.session.execute(db.select(func.count()).select_from(Evento).filter(
        Evento.acao.in_(("login.falha", "login.inexistente", "login.bloqueio", "login.codigo_errado")), Evento.endereco == endereco, Evento.quando >= desde)).scalar()


def _data(texto):
    try:
        return date.fromisoformat((texto or "").strip())
    except ValueError:
        return None


def filtros_da_requisicao(args):
    """Os filtros da tela, já limpos: {'de', 'ate' (datas ou None), 'usuario', 'categoria', 'acolhido', 'pagina'}."""
    categoria = args.get("categoria", "")
    return {"de": _data(args.get("de")), "ate": _data(args.get("ate")), "usuario": (args.get("usuario") or "").strip()[:50],
            "categoria": categoria if categoria in CATEGORIAS else "", "acolhido": (args.get("acolhido") or "").strip()[:100],
            "pagina": max(args.get("pagina", 1, type=int) or 1, 1)}


def _pessoas_do_nome(texto):
    with exclusao.vendo_tudo():
        achadas = db.session.execute(db.select(Pessoa.id).filter(Pessoa.nome.ilike(f"%{texto}%")).limit(500)).scalars().all()
    return achadas


def _consulta(filtros):
    q = db.select(Evento)
    if filtros["de"]:
        q = q.filter(Evento.quando >= datetime.combine(filtros["de"], time.min))
    if filtros["ate"]:
        q = q.filter(Evento.quando < datetime.combine(filtros["ate"] + timedelta(days=1), time.min))
    if filtros["usuario"]:
        q = q.filter(Evento.usuario == filtros["usuario"])
    if filtros["categoria"]:
        q = q.filter(Evento.categoria == filtros["categoria"])
    if filtros["acolhido"]:
        q = q.filter(Evento.pessoa_id.in_(_pessoas_do_nome(filtros["acolhido"]) or [-1]))
    return q.order_by(Evento.quando.desc(), Evento.id.desc())


def consultar(filtros):
    """(eventos da página, total que casa com os filtros, tem próxima página)."""
    q = _consulta(filtros)
    total = db.session.execute(db.select(func.count()).select_from(q.order_by(None).subquery())).scalar()
    inicio = (filtros["pagina"] - 1) * POR_PAGINA
    eventos = db.session.execute(q.limit(POR_PAGINA + 1).offset(inicio)).scalars().all()
    return eventos[:POR_PAGINA], total, len(eventos) > POR_PAGINA


def usuarios_com_eventos():
    return db.session.execute(db.select(distinct(Evento.usuario)).filter(Evento.usuario != "").order_by(Evento.usuario)).scalars().all()


def descrever(eventos):
    """Para a tela: cada evento com o nome de quem fez (do cadastro de funcionários), o nome do acolhido (do cadastro de pessoas) e
    se a ficha ainda existe (para virar link)."""
    logins = {f.usuario: f.nome for f in db.session.execute(db.select(Funcionario).filter(Funcionario.usuario != "")).scalars()}
    ids_pessoas = {e.pessoa_id for e in eventos if e.pessoa_id}
    with exclusao.vendo_tudo():
        pessoas = {p.id: p.nome for p in db.session.execute(db.select(Pessoa).filter(Pessoa.id.in_(ids_pessoas))).scalars()} if ids_pessoas else {}
        ids_fichas = {e.alvo_id for e in eventos if e.alvo_tipo == "internacao" and e.alvo_id}
        fichas = set(db.session.execute(db.select(Internacao.id).filter(Internacao.id.in_(ids_fichas))).scalars()) if ids_fichas else set()
    saida = []
    for e in eventos:
        saida.append({"evento": e, "texto": ACOES.get(e.acao, (e.categoria, e.acao))[1], "funcionario": logins.get(e.usuario, ""),
                      "acolhido": pessoas.get(e.pessoa_id, "") if e.pessoa_id else "",
                      "apagado": bool(e.pessoa_id and e.pessoa_id not in pessoas),
                      "ficha": e.alvo_id if e.alvo_tipo == "internacao" and e.alvo_id in fichas else None})
    return saida


def resumo_dos_filtros(filtros):
    """Os filtros em palavras, para o registro de quem consultou a trilha."""
    partes = []
    if filtros["de"] or filtros["ate"]:
        partes.append(f"período {filtros['de'] or '…'} a {filtros['ate'] or '…'}")
    if filtros["usuario"]:
        partes.append(f"usuário {filtros['usuario']}")
    if filtros["categoria"]:
        partes.append(f"categoria {filtros['categoria']}")
    if filtros["acolhido"]:
        partes.append("busca por acolhido")                    # (o nome buscado não é guardado)
    if filtros["pagina"] > 1:
        partes.append(f"página {filtros['pagina']}")
    return "filtros: " + "; ".join(partes) if partes else "sem filtros"


def _segura(texto):
    """Célula de planilha: nada que comece com = + - @ vira fórmula."""
    texto = "" if texto is None else str(texto)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@") else texto


def csv_da_trilha(filtros):
    """O CSV dos eventos que casam com os filtros (até LIMITE_DO_CSV, do mais novo para o mais velho). Separador ';' e BOM, para o Excel em português."""
    q = _consulta({**filtros, "pagina": 1})
    eventos = db.session.execute(q.limit(LIMITE_DO_CSV)).scalars().all()
    saida = io.StringIO()
    saida.write("﻿")
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(["Quando", "Usuário", "Funcionário", "Categoria", "O que aconteceu", "Código", "Acolhido (nº do cadastro)", "Acolhido", "Objeto", "Detalhe", "Endereço", "Navegador"])
    for linha in descrever(eventos):
        e = linha["evento"]
        escritor.writerow([_segura(x) for x in (f"{e.quando:%d/%m/%Y %H:%M:%S}", e.usuario, linha["funcionario"], CATEGORIAS.get(e.categoria, e.categoria), linha["texto"], e.acao,
                                                 e.pessoa_id or "", linha["acolhido"] or ("(apagado do banco)" if linha["apagado"] else ""),
                                                 f"{e.alvo_tipo} {e.alvo_id}".strip() if e.alvo_tipo else "", e.detalhe, e.endereco, e.navegador)])
    return saida.getvalue(), len(eventos)
