"""
Notificações entre os dois polos (cadastros.POLOS): o que um polo faz e o outro precisa ficar sabendo.

  * **Novo prontuário do Escritório** (PRONTUARIO_NOVO): quando alguém que não é do polo Saúde (o Escritório, o administrador) cadastra um prontuário novo ou admite uma
    triagem, a enfermeira(o) recebe um aviso no quadro da página inicial. Ele some quando ela abre a ficha da pessoa, e só para ela: cada destinatário tem a sua
    notificação, que não depende da dos outros (o "Ciente" do quadro vale para todos, por isso não serve aqui).
  * **Baixa** (BAIXA): quando alguém dá baixa em um interno (na prática, a enfermeira), o administrador e as assistentes sociais recebem uma notificação, no sino do
    cabeçalho. A assistente social ainda ganha, no quadro, a cobrança do relatório de alta (avisos.py).
  * Quem fez a ação nunca é avisado dela. Os destinatários são escolhidos pela **função** no cadastro (enfermeira(o), assistente social, administrador), não pelo
    polo inteiro. Só vale daqui para a frente: o que aconteceu antes de estas notificações existirem não vira aviso.
  * O sino (o número de não lidas) e a lista de notificações (todas, as mais novas primeiro) são de cada pessoa; abrir a ficha de um acolhido marca como lidas as
    notificações dela sobre ele.

Gravar uma notificação nunca derruba a tela: se algo falhar, vai para o registro do servidor e a ação que já deu certo segue.
"""

import logging
from datetime import datetime

import cadastros
from modelos import Notificacao, db

log = logging.getLogger(__name__)

PRONTUARIO_NOVO = "prontuario_novo"
BAIXA = "baixa"
TIPOS = {PRONTUARIO_NOVO: "Novo prontuário", BAIXA: "Baixa"}
LIMITE_DA_LISTA = 200


# ====================================================================== quem recebe
def _com_login(funcionarios):
    """Só quem está ativo e tem um login que existe e está ativo (os logins repetidos contam uma vez)."""
    logins, saida = cadastros._logins_ativos(), []
    for f in funcionarios:
        if f.ativo and f.usuario in logins and f.usuario not in saida:
            saida.append(f.usuario)
    return saida


def enfermeiras():
    """Os logins de quem tem a função de enfermeira(o): recebem o aviso do prontuário novo."""
    return _com_login(f for f in cadastros.funcionarios() if cadastros.profissao_de(f) == "enfermeiro")


def da_baixa():
    """Os logins do administrador e da assistente social: recebem a notificação da baixa."""
    return _com_login([*cadastros.administradores(), *(f for f in cadastros.funcionarios() if f.servico_social)])


def _quem(usuario):
    """Como a pessoa aparece no texto: o nome do funcionário dela (ou o login, se não há funcionário)."""
    funcionario = cadastros.funcionario_do_usuario(usuario)
    return funcionario.nome if funcionario is not None else (usuario.nome if usuario is not None else "")


# ====================================================================== criar
def _notificar(tipo, internacao, logins, texto, por):
    """Uma notificação para cada login (menos o de quem fez a ação), sem repetir uma que a pessoa ainda não leu."""
    try:
        feitor = por.nome if por is not None else ""
        for login in logins:
            if login == feitor:
                continue
            ja_tem = db.session.execute(db.select(Notificacao.id).filter_by(usuario=login, tipo=tipo, internacao_id=internacao.id, lida_em=None).limit(1)).first()
            if not ja_tem:
                db.session.add(Notificacao(usuario=login, tipo=tipo, internacao_id=internacao.id, texto=texto[:300]))
        db.session.commit()
    except Exception:                                                  # noqa: BLE001 — um aviso que não saiu não desfaz o que a pessoa acabou de gravar
        db.session.rollback()
        log.exception("Não consegui gravar a notificação %s da internação %s", tipo, getattr(internacao, "id", None))


def avisar_prontuario_novo(internacao, usuario, admitido=False):
    """Um prontuário foi cadastrado (ou uma triagem foi admitida) por `usuario`: avisa a enfermeira(o), a não ser que quem fez seja do polo Saúde."""
    if cadastros.polo_do_usuario(usuario) == "saude":
        return
    acao = "admitido(a) pelo Escritório" if admitido else "prontuário cadastrado pelo Escritório"
    _notificar(PRONTUARIO_NOVO, internacao, enfermeiras(), f"{internacao.pessoa.nome}: {acao} ({_quem(usuario)}).", usuario)


def avisar_baixa(internacao, usuario):
    """Foi dada a baixa de `internacao` por `usuario`: avisa o administrador e a assistente social."""
    saida = internacao.termino.strftime("%d/%m/%Y") if internacao.termino else "sem data"
    motivo = internacao.motivo or "motivo não informado"
    _notificar(BAIXA, internacao, da_baixa(), f"{internacao.pessoa.nome}: baixa dada por {_quem(usuario)} (saída em {saida}; {motivo}).", usuario)


# ====================================================================== ler
def _do_usuario(usuario):
    """As notificações da pessoa (só as de registros que não foram excluídos: a junção com a internação aplica o filtro da lixeira)."""
    return db.select(Notificacao).join(Notificacao.internacao).filter(Notificacao.usuario == (usuario.nome if usuario is not None else None))


def nao_lidas(usuario):
    """Quantas notificações a pessoa ainda não leu (o número do sino)."""
    if usuario is None:
        return 0
    consulta = _do_usuario(usuario).filter(Notificacao.lida_em.is_(None)).with_only_columns(db.func.count(Notificacao.id))
    return db.session.execute(consulta).scalar() or 0


def tem_alguma(usuario):
    """A pessoa já recebeu alguma notificação (lida ou não)? É o que faz o sino aparecer para quem não é destinatário de nascença."""
    if usuario is None:
        return False
    return db.session.execute(_do_usuario(usuario).with_only_columns(Notificacao.id).limit(1)).first() is not None


def da_pessoa(usuario, limite=LIMITE_DA_LISTA):
    """As notificações da pessoa, as mais novas primeiro."""
    if usuario is None:
        return []
    return db.session.execute(_do_usuario(usuario).order_by(Notificacao.id.desc()).limit(limite)).scalars().all()


def do_quadro(usuario):
    """O que o quadro de avisos mostra à pessoa: os prontuários novos do Escritório que ela ainda não viu, o mais antigo primeiro."""
    if usuario is None:
        return []
    consulta = _do_usuario(usuario).filter(Notificacao.tipo == PRONTUARIO_NOVO, Notificacao.lida_em.is_(None)).order_by(Notificacao.id)
    return db.session.execute(consulta).scalars().all()


# ====================================================================== marcar como lidas
def marcar_lidas(usuario, internacao_id=None):
    """Marca como lidas as notificações da pessoa (as de uma ficha só, se vier `internacao_id`). Devolve quantas mudaram."""
    if usuario is None:
        return 0
    try:
        consulta = db.update(Notificacao).where(Notificacao.usuario == usuario.nome, Notificacao.lida_em.is_(None)).values(lida_em=datetime.now())
        if internacao_id is not None:
            consulta = consulta.where(Notificacao.internacao_id == internacao_id)
        mudou = db.session.execute(consulta).rowcount
        db.session.commit()
        return mudou
    except Exception:                                                  # noqa: BLE001 — abrir a ficha não pode falhar por causa do aviso
        db.session.rollback()
        log.exception("Não consegui marcar as notificações como lidas")
        return 0
