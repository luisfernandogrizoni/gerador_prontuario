"""
Atualiza um banco que já existe quando o modelo ganha colunas novas.

db.create_all() só cria tabelas que não existem; ele NÃO acrescenta colunas
numa tabela antiga. Por isso cada mudança de estrutura vira um passo aqui,
que roda uma vez só (confere se a coluna já existe antes de mexer).
"""

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def _colunas(db, tabela):
    return {c["name"] for c in inspect(db.engine).get_columns(tabela)}


def migrar(db):
    # 1) agendamento x internação efetiva
    if "internacao_agendada" not in _colunas(db, "internacoes"):
        db.session.execute(text("ALTER TABLE internacoes ADD COLUMN internacao_agendada DATE"))
        db.session.execute(text("ALTER TABLE internacoes ADD COLUMN hora_agendada TIME"))
        # quem está em triagem (inclusive desistência) e não tem saída nunca internou:
        # a data que estava em "inicio" era o agendamento
        db.session.execute(text("""
            UPDATE internacoes
               SET internacao_agendada = inicio, hora_agendada = hora_internacao,
                   inicio = NULL, hora_internacao = NULL, data_documento = NULL
             WHERE status IN ('em_admissao', 'lista_espera', 'desistiu')
               AND termino IS NULL AND inicio IS NOT NULL"""))
        db.session.commit()

    # 2) envelope do prontuário: quem já tinha baixa fica "sem controle" ('') e não gera aviso
    if "envelope" not in _colunas(db, "internacoes"):
        db.session.execute(text("ALTER TABLE internacoes ADD COLUMN envelope VARCHAR(10) NOT NULL DEFAULT ''"))
        db.session.execute(text("ALTER TABLE internacoes ADD COLUMN envelope_recebido_em DATE"))
        db.session.commit()

    # 3) pedido de exames e enxoval: para qual data de internação já foram impressos (vazio = ainda não)
    if "exames_impressos_para" not in _colunas(db, "internacoes"):
        db.session.execute(text("ALTER TABLE internacoes ADD COLUMN exames_impressos_para DATE"))
        db.session.commit()

    # 4) exclusão em duas etapas: nada é apagado do banco ao excluir, só marcado (exclusao.py)
    if "excluido_em" not in _colunas(db, "internacoes"):
        db.session.execute(text("ALTER TABLE internacoes ADD COLUMN excluido_em TIMESTAMP"))
        db.session.execute(text("ALTER TABLE internacoes ADD COLUMN excluido_por VARCHAR(50) NOT NULL DEFAULT ''"))
        db.session.commit()
    if "excluido_em" not in _colunas(db, "pessoas"):
        db.session.execute(text("ALTER TABLE pessoas ADD COLUMN excluido_em TIMESTAMP"))
        db.session.commit()

    # 5) cadastros: na primeira subida trazem os convênios e o funcionário com que o sistema sempre trabalhou
    semear(db)


def semear(db):
    """Cria os convênios, os níveis de acesso e o funcionário de fábrica se os cadastros estão vazios.
    Pode rodar quantas vezes quiser."""
    from catalogo import CONVENIOS_DE_FABRICA, NIVEIS_DE_FABRICA
    from documentos import EMISSOR_CARGO, EMISSOR_NOME
    from modelos import Convenio, Funcionario, NivelAcesso

    try:
        if not db.session.execute(db.select(db.func.count(Convenio.id))).scalar():
            for ordem, (nome, tela, slug, gratuito, vagas, cor) in enumerate(CONVENIOS_DE_FABRICA, 1):
                db.session.add(Convenio(nome=nome, nome_tela=tela, slug=slug, gratuito=gratuito, vagas=vagas, cor=cor,
                                        ativo=True, ordem=ordem))
        if not db.session.execute(db.select(db.func.count(NivelAcesso.id))).scalar():
            for ordem, nome in enumerate(NIVEIS_DE_FABRICA, 1):
                db.session.add(NivelAcesso(nome=nome, ordem=ordem, ativo=True))
            db.session.flush()
        if not db.session.execute(db.select(db.func.count(Funcionario.id))).scalar():
            topo = db.session.execute(db.select(NivelAcesso).order_by(NivelAcesso.ordem, NivelAcesso.id)).scalars().first()
            db.session.add(Funcionario(nome=EMISSOR_NOME, cargo=EMISSOR_CARGO, ativo=True, padrao=True,
                                       nivel_id=topo.id if topo else None))
        db.session.commit()
    except IntegrityError:          # outro processo do servidor semeou ao mesmo tempo
        db.session.rollback()
