"""
Salvamento automático e rascunhos.

Um formulário longo (triagem, prontuário, acolhimento social, ficha de saúde, registro de enfermagem, evolução) leva minutos para ser
preenchido. Uma queda de energia, uma aba fechada sem querer, um navegador travado, a rede que cai ou o login que vence no meio da digitação
custavam o trabalho todo. Agora a página (static/rascunho.js) manda uma cópia do que foi digitado a cada pausa na digitação, e essa cópia é
o **rascunho**. O rascunho nunca vira registro sozinho: só a gravação de verdade (o botão Salvar, que valida) escreve no prontuário.

Onde fica e quem vê:

  * **No servidor, não no navegador**: dado de saúde não fica solto no computador de quem digitou, entra no backup e obedece às mesmas regras
    de acesso do resto. Tabela `rascunhos` (modelos.Rascunho), uma linha por formulário em andamento.
  * **Só de quem digitou.** Toda consulta é por `usuario_id` da pessoa logada; um token que não é dela não encontra nada. Para os formulários
    sigilosos (acolhimento social, ficha de saúde...) vale também a permissão de hoje: quem perdeu o acesso não vê nem continua o rascunho.
  * **Dura 30 dias sem mexer** (DIAS_DE_VALIDADE) e some sozinho; apagar um registro de vez leva os rascunhos dele (exclusao.apagar).
  * **Sem senha**: campo de senha, o token CSRF e o botão apertado nunca vão (static/rascunho.js e CAMPOS_FORA). Cadastros (funcionários,
    níveis...) não têm rascunho.
  * **Não entra na trilha de auditoria a cada cópia** (seria ruído): o que se audita é a gravação de verdade, como sempre, e o descarte manual.

Como se liga a uma tela (veja templates/_rascunho.html):

  * o formulário leva `<input type="hidden" name="rascunho" value="TOKEN">`, que nasce na página; é o mesmo token em todos os envios daquela
    tela, e o servidor o devolve se o formulário volta com erro;
  * **registro novo** (nova triagem, novo prontuário): cada vez que a tela abre, o token é novo, e o rascunho antigo continua na lista de
    rascunhos (`/rascunhos`) para ser retomado por `?rascunho=TOKEN`;
  * **tela de um registro** (editar, acolhimento, ficha de saúde...): há no máximo um rascunho por pessoa e por registro, e a tela já abre com
    ele, com um aviso e o botão de descartar para voltar ao que está gravado;
  * ao gravar de verdade, `concluir` troca o rascunho por uma **lápide** (sem dados): se uma cópia atrasada chegar depois, não ressuscita.
"""

import logging
import re
import secrets
from dataclasses import dataclass
from types import SimpleNamespace
from datetime import datetime, timedelta
from typing import Callable

from flask import url_for
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import MultiDict

import cadastros
import permissoes
from modelos import Internacao, Rascunho, db

log = logging.getLogger(__name__)

DIAS_DE_VALIDADE = 30           # sem mexer por tanto tempo, o rascunho some
DIAS_DA_LAPIDE = 2              # a lápide só precisa durar mais que uma cópia atrasada
LIMITE_DO_ENVIO = 250_000       # bytes de uma cópia (um formulário inteiro tem uns 20 mil)
LIMITE_DO_CAMPO = 20_000        # caracteres de um campo
LIMITE_POR_PESSOA = 100         # rascunhos abertos por pessoa
CAMPOS_FORA = {"csrf_token", "rascunho", "acao"}      # o que vai no envio do formulário e não é conteúdo dele
TOKEN = re.compile(r"^[0-9a-f]{32}$")


class ErroDeRascunho(Exception):
    def __init__(self, texto, status=400):
        super().__init__(texto)
        self.texto, self.status = texto, status


@dataclass(frozen=True)
class Tipo:
    rotulo: str
    pode: Callable            # (usuario) -> pode escrever esse formulário hoje?
    novo: bool = False        # também existe como registro novo (sem internação): triagem e prontuário


TIPOS = {
    "triagem": Tipo("Triagem", lambda u: permissoes.pode("triagem", usuario=u), novo=True),
    "prontuario": Tipo("Prontuário", lambda u: permissoes.pode("internacao", usuario=u), novo=True),
    "acolhimento": Tipo("Acolhimento social", cadastros.pode_servico_social),
    "saude": Tipo("Ficha de saúde (anamnese)", cadastros.pode_escrever_saude),
    "enfermagem": Tipo("Registro de enfermagem", cadastros.pode_assinar_saude),
    "evolucao": Tipo("Evolução multiprofissional", cadastros.pode_evoluir),
}


def novo_token():
    return secrets.token_hex(16)


# ====================================================================== guardar
def _campos(bruto):
    """O que a página mandou ([[nome, valor], ...]) como {nome: texto} (ou {nome: [textos]} se o nome se repete)."""
    if not isinstance(bruto, list):
        raise ErroDeRascunho("Cópia inválida.")
    dados = {}
    for par in bruto:
        if not (isinstance(par, (list, tuple)) and len(par) == 2 and isinstance(par[0], str) and isinstance(par[1], str)):
            continue
        nome, valor = par[0][:100], par[1][:LIMITE_DO_CAMPO]
        if not nome or nome in CAMPOS_FORA:
            continue
        if nome in dados:
            dados[nome] = (dados[nome] if isinstance(dados[nome], list) else [dados[nome]]) + [valor]
        else:
            dados[nome] = valor
    return dados


def _conferir_tela(usuario, tipo, internacao_id):
    """A tela existe e a pessoa pode escrever nela? Devolve a internação (ou None, no registro novo)."""
    if not isinstance(tipo, str) or tipo not in TIPOS:
        raise ErroDeRascunho("Formulário desconhecido.")
    if not TIPOS[tipo].pode(usuario):
        raise ErroDeRascunho("Você não escreve neste formulário.", 403)
    if internacao_id is None:
        if not TIPOS[tipo].novo:
            raise ErroDeRascunho("Faltou o registro.")
        return None
    if not isinstance(internacao_id, int) or isinstance(internacao_id, bool):
        raise ErroDeRascunho("Registro inválido.")
    internacao = db.session.get(Internacao, internacao_id)          # (excluído conta como inexistente)
    if internacao is None:
        raise ErroDeRascunho("O registro não existe mais.", 404)
    return internacao


def _titulo(tipo, dados, internacao):
    nome = internacao.pessoa.nome if internacao is not None else dados.get("nome", "")
    return (nome if isinstance(nome, str) else "")[:200]


def salvar(usuario, tipo, token, internacao_id, campos):
    """Guarda (ou atualiza) a cópia. Devolve {"quando": datetime, "concluido": bool}; ErroDeRascunho se não pode."""
    if not isinstance(token, str) or not TOKEN.match(token):
        raise ErroDeRascunho("Cópia inválida.")
    internacao = _conferir_tela(usuario, tipo, internacao_id)
    dados = _campos(campos)
    agora = datetime.now()
    expurgar_se_for_hora(agora)
    for tentativa in (1, 2):
        linha = _linha(usuario, token)
        if linha is not None and linha.concluido_em is not None:
            return {"quando": agora, "concluido": True}             # já foi gravado de verdade: a cópia atrasada não conta
        if linha is None:
            if db.session.execute(db.select(db.func.count(Rascunho.id)).filter_by(usuario_id=usuario.id, concluido_em=None)).scalar() >= LIMITE_POR_PESSOA:
                raise ErroDeRascunho(f"Há {LIMITE_POR_PESSOA} rascunhos guardados. Descarte alguns em Rascunhos para guardar mais.", 409)
            linha = Rascunho(usuario_id=usuario.id, token=token, tipo=tipo, internacao_id=internacao.id if internacao else None, criado_em=agora)
            db.session.add(linha)
        elif (linha.tipo, linha.internacao_id) != (tipo, internacao.id if internacao else None):
            raise ErroDeRascunho("Este rascunho é de outra tela.", 409)
        linha.dados, linha.titulo, linha.atualizado_em = dados, _titulo(tipo, dados, internacao), agora
        try:
            db.session.commit()
            return {"quando": agora, "concluido": False}
        except IntegrityError:           # duas cópias do mesmo rascunho novo ao mesmo tempo: a segunda atualiza a primeira
            db.session.rollback()
            if tentativa == 2:
                raise
    raise AssertionError("inalcançável")


def _linha(usuario, token):
    return db.session.execute(db.select(Rascunho).filter_by(usuario_id=usuario.id, token=token)).scalars().first()


def _vivos(usuario):
    limite = datetime.now() - timedelta(days=DIAS_DE_VALIDADE)
    return db.select(Rascunho).filter(Rascunho.usuario_id == usuario.id, Rascunho.concluido_em.is_(None), Rascunho.atualizado_em >= limite)


# ====================================================================== encerrar
def concluir(usuario, token, tipo=None, internacao_id=None):
    """O formulário foi gravado de verdade (ou o rascunho foi descartado): vira lápide, sem dados. Sem token, não faz nada."""
    if usuario is None or not isinstance(token, str) or not TOKEN.match(token):
        return
    agora = datetime.now()
    linha = _linha(usuario, token)
    if linha is None:                                  # a primeira cópia ainda não chegou: a lápide impede que chegue depois
        if tipo not in TIPOS:
            return
        linha = Rascunho(usuario_id=usuario.id, token=token, tipo=tipo, internacao_id=internacao_id, criado_em=agora)
        db.session.add(linha)
    linha.dados, linha.titulo, linha.concluido_em, linha.atualizado_em = {}, "", agora, agora
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        linha = _linha(usuario, token)
        if linha is not None:
            linha.dados, linha.titulo, linha.concluido_em = {}, "", agora
            db.session.commit()


def descartar(usuario, token):
    """Joga fora o rascunho (só se for da pessoa). Devolve o rascunho que era, para quem chamou saber a tela, ou None."""
    linha = _linha(usuario, token) if isinstance(token, str) and TOKEN.match(token) else None
    if linha is None or linha.concluido_em is not None:
        return None
    resumo = SimpleNamespace(tipo=linha.tipo, internacao_id=linha.internacao_id, titulo=linha.titulo, token=linha.token)
    concluir(usuario, token)
    return resumo


# ====================================================================== limpeza
_ultimo_expurgo = datetime.min


def expurgar(agora=None):
    """Apaga os rascunhos que passaram de DIAS_DE_VALIDADE sem mexer e as lápides velhas. Devolve quantos."""
    agora = agora or datetime.now()
    apagados = db.session.execute(db.delete(Rascunho).filter(Rascunho.concluido_em.is_(None), Rascunho.atualizado_em < agora - timedelta(days=DIAS_DE_VALIDADE))).rowcount
    apagados += db.session.execute(db.delete(Rascunho).filter(Rascunho.concluido_em.isnot(None), Rascunho.concluido_em < agora - timedelta(days=DIAS_DA_LAPIDE))).rowcount
    db.session.commit()
    return apagados


def expurgar_se_for_hora(agora=None):
    """A limpeza roda no máximo de hora em hora, quando alguém guarda ou lista rascunhos (não precisa de tarefa agendada)."""
    global _ultimo_expurgo
    agora = agora or datetime.now()
    if agora - _ultimo_expurgo < timedelta(hours=1):
        return
    _ultimo_expurgo = agora
    try:
        expurgar(agora)
    except Exception:                                  # noqa: BLE001   (a limpeza nunca derruba a cópia)
        db.session.rollback()
        log.exception("Falha ao limpar os rascunhos velhos")


# ====================================================================== ler
def do_registro(usuario, tipo, internacao_id):
    """O rascunho em andamento desta pessoa nesta tela de um registro (editar, acolhimento...), ou None."""
    if usuario is None or tipo not in TIPOS:
        return None
    return db.session.execute(_vivos(usuario).filter_by(tipo=tipo, internacao_id=internacao_id).order_by(Rascunho.atualizado_em.desc())).scalars().first()


def do_token(usuario, token, tipo, internacao_id=None):
    """O rascunho de um registro novo, chamado por `?rascunho=TOKEN`. Só vale se for da pessoa e desta tela."""
    if usuario is None or not isinstance(token, str) or not TOKEN.match(token):
        return None
    return db.session.execute(_vivos(usuario).filter_by(token=token, tipo=tipo, internacao_id=internacao_id)).scalars().first()


def formulario(rascunho):
    """O rascunho como o formulário que voltou da tela: o mesmo `.get` e `.getlist` do request.form."""
    return MultiDict([(nome, valor) for nome, valores in (rascunho.dados or {}).items() for valor in (valores if isinstance(valores, list) else [valores])])


def quantos(usuario):
    if usuario is None:
        return 0
    return db.session.execute(db.select(db.func.count()).select_from(_vivos(usuario).subquery())).scalar()


def quantos_do_tipo(usuario, tipo):
    """Quantos rascunhos de registro novo desta pessoa (para o aviso da tela de registro novo)."""
    return db.session.execute(db.select(db.func.count()).select_from(_vivos(usuario).filter_by(tipo=tipo, internacao_id=None).subquery())).scalar()


def quando_legivel(momento, agora=None):
    agora = agora or datetime.now()
    hora = momento.strftime("%H:%M")
    if momento.date() == agora.date():
        return f"hoje às {hora}"
    if momento.date() == (agora - timedelta(days=1)).date():
        return f"ontem às {hora}"
    return f"{momento.strftime('%d/%m')} às {hora}"


def _alterado_depois(rascunho, internacao):
    """O registro foi mudado (por quem for) depois que este rascunho começou? Então gravar o rascunho passa por cima dessa mudança."""
    registro = {"triagem": internacao, "prontuario": internacao, "acolhimento": internacao.relatorio_social, "saude": internacao.ficha_saude}.get(rascunho.tipo)
    em = getattr(registro, "atualizado_em", None)
    return bool(em and em > rascunho.criado_em)


@dataclass
class Tela:
    """O que o modelo da tela precisa saber do rascunho (templates/_rascunho.html)."""
    token: str
    tipo: str
    alvo: int | None = None            # a internação da tela, se for de um registro
    carregado: bool = False            # a tela abriu com um rascunho no lugar do que está gravado
    quando: str = ""                   # "hoje às 14:32": a última cópia
    registro_mudou: bool = False       # o registro foi alterado depois de o rascunho começar
    outros: int = 0                    # rascunhos de registro novo que a pessoa já tem (aviso na tela de registro novo)
    rotulo: str = ""


def da_tela(usuario, tipo, internacao=None, rascunho=None, form=None, alvo=None):
    """Monta `Tela` para o modelo. `rascunho` é o que a rota abriu (ou None); `form` é o request.form de um envio que voltou com erro
    (a tela devolve o mesmo token, para o rascunho seguir sendo o mesmo); `alvo`, o registro da tela quando só se tem o número dele."""
    alvo = alvo or (internacao.id if internacao is not None else None)
    if rascunho is not None:
        return Tela(rascunho.token, tipo, alvo, carregado=True, quando=quando_legivel(rascunho.atualizado_em),
                    registro_mudou=internacao is not None and _alterado_depois(rascunho, internacao), rotulo=TIPOS[tipo].rotulo)
    token = (form.get("rascunho") if form is not None else "") or ""
    outros = quantos_do_tipo(usuario, tipo) if alvo is None and tipo in TIPOS and TIPOS[tipo].novo else 0
    return Tela(token if TOKEN.match(token) else novo_token(), tipo, alvo, outros=outros, rotulo=TIPOS[tipo].rotulo)


def endereco(tipo, internacao_id, token=None):
    """Onde se abre a tela deste rascunho. Registro novo leva o token (`?rascunho=`); tela de um registro abre sozinha com o rascunho da pessoa.
    Sem token, a tela de registro novo abre em branco."""
    if tipo in ("triagem", "prontuario"):
        if internacao_id:
            return url_for("editar_internacao", id=internacao_id)
        return url_for("nova_triagem" if tipo == "triagem" else "formulario", rascunho=token)
    rota = {"acolhimento": "relatorio_social", "saude": "ficha_saude", "enfermagem": "saude_enfermagem", "evolucao": "saude_evolucao"}.get(tipo)
    return url_for(rota, id=internacao_id) if rota and internacao_id else ""


def listar(usuario):
    """Os rascunhos da pessoa, o mais recente primeiro, com o que a lista mostra e para onde cada um leva. `url` vazio: já não dá para retomar
    (perdeu o acesso, o registro foi excluído ou mudou de tipo); só dá para descartar."""
    expurgar_se_for_hora()
    itens = []
    for r in db.session.execute(_vivos(usuario).order_by(Rascunho.atualizado_em.desc())).scalars():
        tipo = TIPOS.get(r.tipo)
        internacao = db.session.get(Internacao, r.internacao_id) if r.internacao_id else None
        retomavel = tipo is not None and tipo.pode(usuario) and (r.internacao_id is None or internacao is not None)
        if retomavel and internacao is not None and r.tipo in ("triagem", "prontuario"):
            retomavel = (r.tipo == "triagem") == internacao.e_triagem        # o registro mudou de triagem para internação depois
        url = endereco(r.tipo, r.internacao_id, r.token) if retomavel else ""
        sigiloso = r.tipo in ("acolhimento", "saude", "enfermagem", "evolucao")
        itens.append({"token": r.token, "rotulo": tipo.rotulo if tipo else r.tipo, "titulo": (r.titulo if retomavel or not sigiloso else "") or "(sem nome)",
                      "quando": quando_legivel(r.atualizado_em), "url": url, "de_registro": r.internacao_id is not None,
                      "motivo": "" if retomavel else "Você não tem mais acesso a esta tela, ou o registro foi excluído ou mudou."})
    return itens
