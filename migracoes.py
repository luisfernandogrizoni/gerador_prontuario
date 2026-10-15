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

    # 5) acolhimento social: rascunho/finalizado e assinatura no relatório; marca do Serviço Social e registro profissional
    #    (CRESS) no funcionário
    if "situacao" not in _colunas(db, "relatorios_sociais"):
        db.session.execute(text("ALTER TABLE relatorios_sociais ADD COLUMN situacao VARCHAR(12) NOT NULL DEFAULT 'rascunho'"))
        db.session.execute(text("ALTER TABLE relatorios_sociais ADD COLUMN finalizado_em TIMESTAMP"))
        db.session.execute(text("ALTER TABLE relatorios_sociais ADD COLUMN finalizado_por VARCHAR(50) NOT NULL DEFAULT ''"))
        db.session.execute(text("ALTER TABLE relatorios_sociais ADD COLUMN assinatura VARCHAR(200) NOT NULL DEFAULT ''"))
        db.session.commit()
    if "servico_social" not in _colunas(db, "funcionarios"):
        db.session.execute(text("ALTER TABLE funcionarios ADD COLUMN servico_social BOOLEAN NOT NULL DEFAULT FALSE"))
        db.session.execute(text("ALTER TABLE funcionarios ADD COLUMN registro_profissional VARCHAR(30) NOT NULL DEFAULT ''"))
        db.session.commit()

    # 6a) fase 3 do plano de segurança: e-mail do funcionário; troca obrigatória de senha e segundo fator do usuário
    if "email" not in _colunas(db, "funcionarios"):
        db.session.execute(text("ALTER TABLE funcionarios ADD COLUMN email VARCHAR(120) NOT NULL DEFAULT ''"))
        db.session.execute(text("ALTER TABLE funcionarios ADD COLUMN email_confirmado_em TIMESTAMP"))
        db.session.commit()
    if "trocar_senha" not in _colunas(db, "usuarios"):
        db.session.execute(text("ALTER TABLE usuarios ADD COLUMN trocar_senha BOOLEAN NOT NULL DEFAULT FALSE"))
        db.session.execute(text("ALTER TABLE usuarios ADD COLUMN totp_segredo VARCHAR(200) NOT NULL DEFAULT ''"))
        db.session.execute(text("ALTER TABLE usuarios ADD COLUMN totp_ativo BOOLEAN NOT NULL DEFAULT FALSE"))
        db.session.execute(text("ALTER TABLE usuarios ADD COLUMN totp_ultimo_passo INTEGER NOT NULL DEFAULT 0"))
        db.session.execute(text("ALTER TABLE usuarios ADD COLUMN totp_recuperacao VARCHAR(2000) NOT NULL DEFAULT ''"))
        db.session.commit()

    # 6) o relatório de rejeição virou o parecer do acolhimento social: o que já foi escrito passa para lá
    _rejeicoes_para_o_acolhimento(db)

    # 7) cadastros: na primeira subida trazem os convênios e o funcionário com que o sistema sempre trabalhou
    semear(db)


def _rejeicoes_para_o_acolhimento(db):
    """A tabela rejeicoes_triagem (o relatório de rejeição, que existiu por pouco tempo) deixou de existir no modelo.
    Cada relatório dela vira o parecer 'Não condizente' do acolhimento social da mesma triagem, como rascunho: a
    assistente social completa o que falta (classificação) e finaliza. Depois as linhas são apagadas, então rodar de
    novo não repete nada. Bancos novos nem têm a tabela."""
    if "rejeicoes_triagem" not in inspect(db.engine).get_table_names():
        return
    import json
    from datetime import datetime

    from modelos import RelatorioSocial
    from servico_social import NAO_CONDIZENTE

    linhas = db.session.execute(text("SELECT internacao_id, dados, atualizado_por, atualizado_em FROM rejeicoes_triagem")).all()
    for internacao_id, dados, por, em in linhas:
        if isinstance(dados, str):
            dados = json.loads(dados or "{}")
        dados = dados or {}
        novos = {"parecer": NAO_CONDIZENTE}
        if dados.get("motivo"):
            novos["motivo_rejeicao"] = dados["motivo"]
        texto = (dados.get("relatorio") or "").strip()
        if dados.get("data_da_rejeicao"):
            try:
                quando = datetime.strptime(dados["data_da_rejeicao"], "%Y-%m-%d").strftime("%d/%m/%Y")
                texto = f"Rejeição registrada em {quando}." + (f"\n\n{texto}" if texto else "")
            except ValueError:
                pass
        if texto:
            novos["parecer_texto"] = texto
        relatorio = db.session.execute(db.select(RelatorioSocial).filter_by(internacao_id=internacao_id)).scalars().first()
        if relatorio is None:
            db.session.add(RelatorioSocial(internacao_id=internacao_id, dados=novos, atualizado_por=(por or "")[:50]))
        else:
            relatorio.dados = {**novos, **(relatorio.dados or {})}      # o que já estava no acolhimento tem a palavra final
    db.session.execute(text("DELETE FROM rejeicoes_triagem"))
    db.session.commit()


def semear(db):
    """Cria os convênios, os níveis de acesso e o funcionário de fábrica se os cadastros estão vazios.
    Pode rodar quantas vezes quiser."""
    from catalogo import CONVENIOS_DE_FABRICA, NIVEIS_DE_FABRICA
    from documentos import EMISSOR_CARGO, EMISSOR_NOME
    import permissoes
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
    permissoes.semear()             # o nível de fábrica de cada permissão (a nova de uma versão futura entra sozinha)
