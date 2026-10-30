"""
Níveis de acesso em cascata: o que cada nível pode fazer.

Como funciona (plano de segurança, fase 1 — docs/plano-de-seguranca.md):

  * Os níveis (Cadastros > Níveis de acesso) formam uma cascata: o primeiro é o do administrador, e cada nível tem tudo o
    que os de baixo têm. Cada pessoa tem o nível do funcionário ao qual o login dela está ligado.
  * Cada permissão (a lista está em GRUPOS) tem um **nível mínimo**: quem está nele, ou acima na cascata, pode. É isso que a
    tela Cadastros > Permissões mostra e o administrador muda. Mover um nível na cascata muda quem passa, sem refazer nada.
  * **Nega por padrão**: toda rota precisa estar em REGRAS (um teste confere); rota nova sem regra fica fechada, para todos.
    A regra é conferida num lugar só, antes da rota rodar (exigir_permissao), nunca espalhada pelas telas. As telas só
    **escondem** o que a pessoa não pode usar (`pode(...)` nos templates), para não oferecer botão que não funciona.
  * O administrador pode tudo. Enquanto nenhum administrador tem usuário vinculado (sistema recém-instalado), quem está
    logado conta como administrador (cadastros.pode_gerenciar_acessos), senão ninguém conseguiria vincular o primeiro.
  * Login sem funcionário ativo vinculado tem o nível de menos acesso (o último da cascata); login de funcionário
    **desativado** não entra (cadastros.acesso_desativado), nem com a sessão já aberta.
  * Fora da cascata: o acolhimento social e a ficha de saúde (sigilosos) são pela função da pessoa no cadastro do funcionário (assistente
    social, enfermeira com COREN válido: cadastros.pode_servico_social e pode_assinar_saude) e, para só ler, por uma permissão dada pessoa a pessoa
    (cadastros.pode_ler_sigilosos), porque são funções e acessos pontuais, não uma hierarquia.
  * O que só o administrador faz (criar usuário e senha, mexer nos níveis e nas permissões, lixeira) é fixo: não se configura.

Toda negação vai para o registro do servidor (logs/servidor.log), com quem foi, o quê e qual permissão faltou.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from flask import g, jsonify, render_template, request, session
from sqlalchemy.exc import IntegrityError

import auditoria
import autenticacao
import cadastros
from modelos import Internacao, PermissaoNivel, db

log = logging.getLogger(__name__)


# ====================================================================== o catálogo
@dataclass(frozen=True)
class Permissao:
    chave: str
    rotulo: str            # o que a tela mostra: "Registrar e editar triagens"
    detalhe: str           # o que isso inclui, numa linha
    padrao: int = 1        # de fábrica, até que posição da cascata vale (0 = só o administrador, 1 = até o 2º nível, ...)
    fixa: bool = False     # só o administrador, não se configura
    todos: bool = False    # todo mundo que entrou, não se configura


@dataclass(frozen=True)
class Grupo:
    titulo: str
    icone: str             # símbolo do base.html (sem o "i-")
    tom: str               # cor da seção (tom-*)
    permissoes: tuple


GRUPOS = (
    Grupo("Consultar", "busca", "azul", (
        Permissao("ver", "Ver triagens, internos, fichas e o início", "Todo mundo que entrou no sistema", todos=True),
        Permissao("relatorios", "Ver e baixar relatórios", "Internos ativos por convênio e quem passou pela casa no ano", padrao=2),
        Permissao("documentos", "Imprimir e baixar os documentos do acolhido", "Prontuário, declaração, pedido de exames e enxoval"),
    )),
    Grupo("Triagem e internação", "prancheta", "verde", (
        Permissao("triagem", "Registrar e editar triagens", "Inclui mudar a situação e admitir"),
        Permissao("internacao", "Registrar e editar prontuários", "Internações e dados do acolhido"),
        Permissao("baixa", "Dar baixa e anotar o prontuário em papel", "Saída do interno e retorno do envelope"),
        Permissao("financeiro", "Lançar e excluir parcelas", "Contribuição de cada internação"),
        Permissao("excluir", "Excluir registros", "Vão para a lixeira; só o administrador apaga de vez"),
        Permissao("unificar", "Unificar cadastros duplicados", "Junta duas fichas da mesma pessoa", padrao=0),
    )),
    Grupo("Cadastros", "usuarios", "roxo", (
        Permissao("cadastros", "Cadastrar convênios e funcionários", "Vagas, cores, nome, cargo e quem assina; sem usuário e senha", padrao=0),
    )),
    Grupo("Só o administrador", "cadeado", "neutro", (
        Permissao("acessos", "Criar usuários, trocar senhas e definir níveis e permissões", "Cadastros > Funcionários, Níveis e Permissões", padrao=0, fixa=True),
        Permissao("lixeira", "Restaurar da lixeira e apagar de vez", "O que os outros excluíram", padrao=0, fixa=True),
        Permissao("backup", "Ver a situação do backup e dos pen-drives", "Cadastros > Backup", padrao=0, fixa=True),
        Permissao("auditoria", "Ver a trilha de auditoria", "Cadastros > Auditoria: quem fez o quê e quando", padrao=0, fixa=True),
    )),
)

PERMISSOES = tuple(p for grupo in GRUPOS for p in grupo.permissoes)
POR_CHAVE = {p.chave: p for p in PERMISSOES}
CONFIGURAVEIS = tuple(p for p in PERMISSOES if not p.fixa and not p.todos)

# O acolhimento social e a ficha de saúde não estão na cascata: quem escreve é o administrador e quem tem a função no cadastro do funcionário
# (cadastros.pode_servico_social, pode_escrever_saude); quem só lê recebeu a permissão `le_sigilosos` (cadastros.pode_ler_sigilosos). A tela de
# permissões mostra isso em linhas à parte.
ACOLHIMENTO_SOCIAL = "Acolhimento social (sigiloso)"


# ====================================================================== quem pode
def e_administrador(usuario=None):
    """O usuário (o logado, se não vier nenhum) é o administrador? Guardado por requisição: as telas perguntam várias vezes."""
    logado = g.get("usuario")
    if usuario is not None and usuario is not logado:
        return cadastros.pode_gerenciar_acessos(usuario)
    if "e_administrador" not in g:
        g.e_administrador = cadastros.pode_gerenciar_acessos(logado)
    return g.e_administrador


def _niveis():
    """Os níveis na ordem da cascata, guardados por requisição."""
    if "niveis_da_cascata" not in g:
        g.niveis_da_cascata = cadastros.niveis()
    return g.niveis_da_cascata


def _nivel_padrao(permissao):
    niveis = _niveis()
    return niveis[min(permissao.padrao, len(niveis) - 1)] if niveis else None


def _ordem_minima(permissao):
    """A ordem do nível mínimo da permissão: o que o administrador escolheu, ou o de fábrica se ainda não escolheu."""
    if "minimos_de_permissao" not in g:
        ordens = {n.id: n.ordem for n in _niveis()}
        g.minimos_de_permissao = {linha.chave: ordens.get(linha.nivel_id)
                                  for linha in db.session.execute(db.select(PermissaoNivel)).scalars()}
    ordem = g.minimos_de_permissao.get(permissao.chave)
    if ordem is None:
        padrao = _nivel_padrao(permissao)
        ordem = padrao.ordem if padrao else 0
    return ordem


def _ordem_do_usuario(usuario):
    """Onde a pessoa está na cascata (1 = administrador). Sem funcionário ativo ligado ao login: no último nível."""
    nivel = cadastros.nivel_do_usuario(usuario)
    if nivel is not None:
        return nivel.ordem
    niveis = _niveis()
    return max((n.ordem for n in niveis), default=0)


def _pode(chave, usuario):
    permissao = POR_CHAVE[chave]          # chave com erro de digitação: quebra alto, nunca libera sem querer
    if usuario is None:
        return False
    if permissao.todos:
        return True
    if e_administrador(usuario):
        return True
    if permissao.fixa:
        return False
    if usuario is g.get("usuario"):
        if "ordem_do_usuario" not in g:
            g.ordem_do_usuario = _ordem_do_usuario(usuario)
        ordem = g.ordem_do_usuario
    else:
        ordem = _ordem_do_usuario(usuario)
    return ordem <= _ordem_minima(permissao)


def pode(*chaves, usuario=None):
    """A pessoa logada (ou `usuario`) pode alguma destas permissões? Também é usada nos templates: {% if pode('triagem') %}."""
    usuario = usuario if usuario is not None else g.get("usuario")
    return any(_pode(chave, usuario) for chave in chaves)


def do_usuario():
    """{permissão: pode?} de quem está logado, para o JavaScript das listas esconder o que não vale."""
    return {p.chave: pode(p.chave) for p in PERMISSOES}


# ====================================================================== a regra de cada rota
LIVRE = "livre"        # basta ter entrado (sair e trocar a própria senha)


def _quem_edita():
    """Editar um registro abre o formulário da triagem ou o do prontuário: cada um com a sua permissão."""
    internacao = db.session.get(Internacao, (request.view_args or {}).get("id"))
    return "triagem" if internacao is not None and internacao.e_triagem else "internacao"


# Os impressos dos relatórios sigilosos (o acolhimento social e a ficha de saúde): pedidos sozinhos, quem pode lê-los (quem escreve e quem recebeu a
# permissão de ler os sigilosos) os abre mesmo num nível sem "documentos". Pedidos com outros impressos (prontuário, exames...) continuam pedindo
# "documentos".
QUEM_LE_O_IMPRESSO = {"relatorio-social": cadastros.pode_ler_social, "resumo-social": cadastros.pode_ler_social, "multiprofissional": cadastros.pode_ler_saude}


def _quem_imprime():
    itens = {p.strip() for p in (request.args.get("itens") or "").split(",") if p.strip()}
    if itens and itens <= set(QUEM_LE_O_IMPRESSO) and all(QUEM_LE_O_IMPRESSO[item](g.get("usuario")) for item in itens):
        return LIVRE
    return "documentos"


# Uma permissão, várias (basta uma delas) ou uma função que devolve isso (ou LIVRE). Rota que não está aqui fica FECHADA.
# (relatorio_social, o histórico de versões e as rotas da ficha de saúde só pedem "ver" aqui: o sigilo é conferido na própria rota, com o aviso
# explicando por que não abriu — veja _pode_servico_social, _pode_ler_saude e _pode_assinar_saude em app.py.)
REGRAS = {
    "sair": LIVRE, "alterar_senha": LIVRE, "seguranca": LIVRE, "enviar_codigo_email": LIVRE, "confirmar_email": LIVRE,
    "ativar_autenticador": LIVRE, "desativar_autenticador": LIVRE,
    "salvar_rascunho": LIVRE, "lista_rascunhos": LIVRE, "descartar_rascunho": LIVRE,    # rascunhos: só os da própria pessoa, e a tela de cada um confere a permissão (rascunhos.py)
    # (a página de entrada, o código e o "esqueci minha senha" são autenticacao.ROTAS_LIVRES)

    "home": "ver", "api_pessoas": "ver", "lista_triagens": "ver", "api_triagens": "ver", "lista_internos": "ver",
    "api_internos": "ver", "api_internos_busca": "ver", "ficha": "ver", "relatorio_social": "ver", "relatorio_de_rejeicao": "ver",
    "ficha_saude": "ver", "saude_enfermagem": "ver", "saude_evolucao": "ver",
    "historico_do_relatorio": "ver", "ver_versao_do_relatorio": "ver",
    "aviso_ciente": ("triagem", "internacao", "baixa"),

    "ver_prontuario": "documentos", "baixar_prontuario": "documentos", "ver_declaracao": "documentos",
    "baixar_declaracao": "documentos", "ver_impressos": _quem_imprime, "baixar_impressos": _quem_imprime,
    "pagina_relatorios": "relatorios", "ver_relatorio": "relatorios", "baixar_relatorio": "relatorios",
    "ver_relatorio_anual": "relatorios", "baixar_relatorio_anual": "relatorios",

    "nova_triagem": "triagem", "salvar_triagem": "triagem", "mudar_status": "triagem",
    "formulario": "internacao", "gerar": "internacao", "editar_internacao": _quem_edita,
    "baixa_interno": "baixa", "registrar_envelope": "baixa",
    "lancar_parcela": "financeiro", "excluir_parcela": "financeiro",
    "excluir_registro": "excluir", "unificar_pessoas": "unificar",

    "cadastros": "cadastros", "lista_convenios": "cadastros", "novo_convenio": "cadastros", "editar_convenio": "cadastros",
    "lista_funcionarios": "cadastros", "novo_funcionario": "cadastros", "editar_funcionario": "cadastros",
    "lista_niveis": "cadastros", "lista_permissoes": "cadastros",

    "novo_nivel": "acessos", "editar_nivel": "acessos", "mover_nivel": "acessos", "salvar_permissoes": "acessos",
    "lixeira": "lixeira", "restaurar_registro": "lixeira", "apagar_registro": "lixeira", "pagina_backup": "backup",
    "pagina_auditoria": "auditoria", "exportar_auditoria": "auditoria",
    "revisao_de_acessos": "acessos", "marcar_revisao": "acessos",
}


def exigir_permissao():
    """before_request, depois do login: a rota pede uma permissão e a pessoa tem? Se não, nega sem rodar a rota."""
    endpoint, usuario = request.endpoint, g.get("usuario")
    if endpoint is None or endpoint in autenticacao.ROTAS_LIVRES or usuario is None:
        return None                       # (endereço que não existe: o Flask responde 404)
    if cadastros.acesso_desativado(usuario):
        session.clear()
        log.warning("Acesso de %s negado: o funcionário dele está desativado", usuario.nome)
        auditoria.registrar("sessao.derrubada", usuario=usuario.nome)
        if request.path.startswith("/api/") or request.is_json:
            return jsonify(ok=False, erros={"sessao": "Este acesso foi desativado."}), 401
        return render_template("login.html", erro="Este acesso foi desativado. Procure o administrador.", proximo=""), 401
    regra = REGRAS.get(endpoint)
    if regra is None:
        log.error("Rota %s sem regra de acesso em permissoes.REGRAS: fechada para todos", endpoint)
        auditoria.registrar("acesso.negado", detalhe=f"{request.method} {request.path}: rota sem regra de acesso")
        return _negar(usuario, ())
    if regra == LIVRE:
        return None
    chaves = regra() if callable(regra) else regra
    if chaves == LIVRE:
        return None
    chaves = (chaves,) if isinstance(chaves, str) else tuple(chaves)
    if pode(*chaves, usuario=usuario):
        return None
    log.warning("Acesso negado a %s: %s %s pede %s", usuario.nome, request.method, request.path, " ou ".join(chaves))
    auditoria.registrar("acesso.negado", detalhe=f"{request.method} {request.path} pede {' ou '.join(chaves)}")
    return _negar(usuario, chaves)


def _negar(usuario, chaves):
    nivel = cadastros.nivel_do_usuario(usuario)
    de_quem = f"Seu nível de acesso ({nivel.nome})" if nivel else "Seu acesso"
    falta = " ou ".join(POR_CHAVE[c].rotulo[0].lower() + POR_CHAVE[c].rotulo[1:] for c in chaves)
    texto = f"{de_quem} não inclui: {falta}. Se precisar, peça ao administrador." if falta else \
        "Esta página não está liberada. Avise o administrador."
    if request.path.startswith("/api/") or request.is_json:
        return jsonify(ok=False, erros={"permissao": f"{de_quem} não permite esta ação."}), 403
    return render_template("erro.html", codigo=403, titulo="Sem permissão", texto=texto), 403


# ====================================================================== a tela de permissões
def matriz():
    """Para Cadastros > Permissões: os níveis ativos, na ordem da cascata, e, de cada permissão, em quais deles ela vale.
    `escolhido` marca o nível mínimo (o ponto de onde a permissão passa a valer); se ele foi desativado, nenhum é marcado."""
    niveis = [n for n in _niveis() if n.ativo]
    topo = _niveis()[0] if _niveis() else None
    grupos = []
    for grupo in GRUPOS:
        linhas = []
        for p in grupo.permissoes:
            if p.todos:
                celulas = [(n, True, False) for n in niveis]
            elif p.fixa:
                celulas = [(n, topo is not None and n.id == topo.id, False) for n in niveis]
            else:
                minimo = _ordem_minima(p)
                celulas = [(n, n.ordem <= minimo, n.ordem == minimo) for n in niveis]
            linhas.append({"permissao": p, "celulas": celulas, "editavel": not p.fixa and not p.todos})
        grupos.append({"grupo": grupo, "linhas": linhas})
    return niveis, grupos


def salvar_matriz(form, por=""):
    """Grava o nível mínimo de cada permissão que veio no formulário (`perm_<chave>` = id do nível). Devolve
    (erros, quantas mudaram). O que não veio fica como estava; nível desativado ou que não existe é recusado."""
    ativos = {str(n.id): n for n in _niveis() if n.ativo}
    escolhas, erros = {}, {}
    for p in CONFIGURAVEIS:
        valor = form.get("perm_" + p.chave)
        if valor is None:
            continue
        if valor not in ativos:
            erros[p.chave] = f"Escolha um nível para: {p.rotulo}."
        else:
            escolhas[p.chave] = ativos[valor]
    if erros:
        return erros, 0
    linhas = {linha.chave: linha for linha in db.session.execute(db.select(PermissaoNivel)).scalars()}
    mudou = []
    for chave, nivel in escolhas.items():
        linha = linhas.get(chave)
        if linha is None:
            db.session.add(PermissaoNivel(chave=chave, nivel_id=nivel.id, alterado_por=por[:50]))
            mudou.append((chave, "(padrão)", nivel.nome))
        elif linha.nivel_id != nivel.id:
            mudou.append((chave, linha.nivel.nome, nivel.nome))
            linha.nivel_id, linha.alterado_em, linha.alterado_por = nivel.id, datetime.now(), por[:50]
    db.session.commit()
    for chave, antes, depois in mudou:
        log.info("Permissão %s mudou de %s para %s, por %s", chave, antes, depois, por or "?")
    if mudou:
        auditoria.registrar("permissao.alterar", detalhe="; ".join(f"{chave}: {antes} → {depois}" for chave, antes, depois in mudou))
    return {}, len(mudou)


def semear():
    """Grava o nível de fábrica das permissões que ainda não têm nível mínimo. Pode rodar quantas vezes quiser; uma
    permissão nova de uma versão futura entra aqui sozinha, sem mexer no que o administrador já escolheu."""
    niveis = cadastros.niveis()
    if not niveis:
        return
    existentes = set(db.session.execute(db.select(PermissaoNivel.chave)).scalars())
    for p in CONFIGURAVEIS:
        if p.chave not in existentes:
            db.session.add(PermissaoNivel(chave=p.chave, nivel_id=niveis[min(p.padrao, len(niveis) - 1)].id, alterado_por="sistema"))
    try:
        db.session.commit()
    except IntegrityError:          # outro processo do servidor semeou ao mesmo tempo
        db.session.rollback()
