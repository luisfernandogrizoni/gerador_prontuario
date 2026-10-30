"""
Excluir um registro em duas etapas.

  * Quem não é administrador "exclui": o registro (a triagem ou a internação, e a pessoa, se era o único registro dela)
    é só marcado como excluído. Ele some das listas, da página inicial, das vagas, dos relatórios, das buscas e dos
    avisos, mas continua no banco.
  * O administrador vê o que foi excluído (Cadastros > Lixeira), pode restaurar ou apagar de vez do banco, e também pode
    apagar de vez direto da ficha.

O "some de tudo" é uma regra só, aplicada a TODA consulta ao banco (o gancho `do_orm_execute` abaixo): nenhuma tela
precisa lembrar de filtrar. Quem precisa ver os excluídos (a lixeira, restaurar, apagar) abre `vendo_tudo()`.
Este módulo precisa ser importado uma vez na subida do sistema (app.py).
"""

from contextlib import contextmanager
from datetime import datetime

from flask import g, has_app_context
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from modelos import AvisoDispensado, Internacao, Pessoa, Rascunho, db

# avisos que citam o registro (avisos.py): ao apagar de vez, as dispensas deles também vão (o SQLite reaproveita ids)
AVISOS_DA_INTERNACAO = ("respcpf", "seminicio", "semtermino", "desistinicio", "agendavencida", "envelope", "rejeicao", "acolhimento")
AVISOS_DA_PESSOA = ("cpf", "tel")


def _vendo_tudo():
    return has_app_context() and g.get("vendo_excluidos", False)


@event.listens_for(Session, "do_orm_execute")
def _esconder_excluidos(estado):
    """Toda leitura ignora o que foi excluído (as releituras de colunas e as cargas de relacionamento já herdam isso)."""
    if estado.is_select and not estado.is_column_load and not estado.is_relationship_load and not _vendo_tudo():
        estado.statement = estado.statement.options(
            with_loader_criteria(Internacao, lambda c: c.excluido_em.is_(None), include_aliases=True),
            with_loader_criteria(Pessoa, lambda c: c.excluido_em.is_(None), include_aliases=True))


@contextmanager
def vendo_tudo():
    """Dentro do bloco, as consultas enxergam também os registros excluídos."""
    antes = g.get("vendo_excluidos", False)
    g.vendo_excluidos = True
    try:
        yield
    finally:
        g.vendo_excluidos = antes


# ------------------------------------------------------------------ as ações
def excluir(internacao, usuario=""):
    """Tira o registro de circulação (sem apagar). A pessoa também sai, se este era o único registro dela."""
    agora = datetime.now()
    internacao.excluido_em, internacao.excluido_por = agora, (usuario or "")[:50]
    pessoa = internacao.pessoa
    if not any(outro.id != internacao.id for outro in pessoa.internacoes):     # só enxerga os que não foram excluídos
        pessoa.excluido_em = agora
    db.session.commit()


def restaurar(internacao):
    """Devolve à circulação. Chamar dentro de `vendo_tudo()`."""
    internacao.excluido_em, internacao.excluido_por = None, ""
    internacao.pessoa.excluido_em = None
    db.session.commit()


def apagar(internacao):
    """Apaga do banco: o registro, o que depende dele (parcelas, relatórios) e a pessoa, se não sobrou nenhum registro
    dela. Não tem volta. Chamar dentro de `vendo_tudo()`."""
    pessoa, id_internacao, id_pessoa = internacao.pessoa, internacao.id, internacao.pessoa_id
    db.session.delete(internacao)
    db.session.execute(db.delete(Rascunho).filter_by(internacao_id=id_internacao))        # o que alguém digitava sobre este registro
    db.session.flush()
    _limpar_dispensas(AVISOS_DA_INTERNACAO, id_internacao)
    if not db.session.execute(db.select(db.func.count(Internacao.id)).filter_by(pessoa_id=id_pessoa)).scalar():
        db.session.delete(pessoa)
        _limpar_dispensas(AVISOS_DA_PESSOA, id_pessoa)
    db.session.commit()


def _limpar_dispensas(prefixos, id_):
    for prefixo in prefixos:
        for chave in db.session.execute(db.select(AvisoDispensado).filter(AvisoDispensado.chave.like(f"{prefixo}:{id_}%"))).scalars():
            if chave.chave == f"{prefixo}:{id_}" or chave.chave.startswith(f"{prefixo}:{id_}:"):
                db.session.delete(chave)


# ------------------------------------------------------------------ a lixeira
def excluidos():
    """Os registros excluídos, o mais recente primeiro. Chamar dentro de `vendo_tudo()`."""
    return db.session.execute(db.select(Internacao).filter(Internacao.excluido_em.isnot(None))
                              .order_by(Internacao.excluido_em.desc(), Internacao.id.desc())).scalars().all()


def quantos_excluidos():
    with vendo_tudo():
        return db.session.execute(db.select(db.func.count(Internacao.id)).filter(Internacao.excluido_em.isnot(None))).scalar()
