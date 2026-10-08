"""
Atualiza um banco que já existe quando o modelo ganha colunas novas.

db.create_all() só cria tabelas que não existem; ele NÃO acrescenta colunas
numa tabela antiga. Por isso cada mudança de estrutura vira um passo aqui,
que roda uma vez só (confere se a coluna já existe antes de mexer).
"""

from sqlalchemy import inspect, text


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
