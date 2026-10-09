"""
Dados do painel da página inicial: os números do topo e a agenda dos próximos dias.

Como os avisos e as vagas, nada fica gravado: tudo é calculado a cada visita.

Agenda = o que está marcado para os próximos dias, de quem ainda está na triagem
(em admissão ou lista de espera):
    Triagem      -> data_triagem (+ hora_triagem), com a modalidade (presencial/online)
    Internação   -> internacao_agendada (+ hora_agendada), com o convênio
Quem já foi admitido, desistiu ou virou inativo não aparece.
"""

from datetime import date, timedelta

from flask import url_for
from sqlalchemy import or_

from modelos import STATUS, Internacao, db
from prontuario import MESES, fmt_data, previsao_termino
from validacao import fmt_hora

DIAS_DA_AGENDA = 14
DIAS_FIM_DO_TRATAMENTO = 60      # quantos dias à frente a lista "tratamentos próximos do fim" olha
LINHAS_FIM_DO_TRATAMENTO = 8     # quantas linhas aparecem na home (o resto fica no link "ver todos")
URGENTE_ATE = 7                  # faltando até 7 dias, o prazo fica em destaque
DIAS_DA_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
                  "sábado", "domingo"]
DIAS_CURTOS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
NA_TRIAGEM = ("em_admissao", "lista_espera")


def data_por_extenso(d):
    """date(2026, 10, 9) -> 'sexta-feira, 9 de outubro de 2026'."""
    return f"{DIAS_DA_SEMANA[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}"


def resumo():
    """Quantos registros há em cada situação (chaves de modelos.STATUS; 0 quando não há nenhum)."""
    contagem = dict(db.session.execute(
        db.select(Internacao.status, db.func.count()).group_by(Internacao.status)).all())
    return {status: contagem.get(status, 0) for status in STATUS}


def _rotulo_do_dia(dia, hoje):
    if dia == hoje:
        return "Hoje"
    if dia == hoje + timedelta(days=1):
        return "Amanhã"
    return DIAS_DA_SEMANA[dia.weekday()].split("-")[0].capitalize()   # "Segunda", "Terça"...


def _eventos(internacao, hoje, fim):
    """Os agendamentos desta pessoa que caem na janela [hoje, fim]."""
    convenio_definido = internacao.convenio not in ("", "A definir")
    for tipo, dia, hora, detalhe in (
        ("Triagem", internacao.data_triagem, internacao.hora_triagem,
         internacao.modalidade or "modalidade a definir"),
        ("Internação", internacao.internacao_agendada, internacao.hora_agendada,
         internacao.convenio_txt if convenio_definido else "convênio a definir"),
    ):
        if dia and hoje <= dia <= fim:
            yield {
                "tipo": tipo, "classe": "triagem" if tipo == "Triagem" else "internacao",
                "dia": dia, "hora": fmt_hora(hora), "nome": internacao.pessoa.nome,
                "detalhe": detalhe, "url": url_for("ficha", id=internacao.id),
                "_ordem_hora": hora.strftime("%H:%M") if hora else "99:99",   # sem horário vai por último
            }


def _rotulo_do_prazo(restam):
    if restam == 0:
        return "termina hoje"
    if restam == 1:
        return "termina amanhã"
    if restam > 1:
        return f"em {restam} dias"
    if restam == -1:
        return "venceu ontem"
    return f"venceu há {-restam} dias"


def tratamentos_a_finalizar(dias=DIAS_FIM_DO_TRATAMENTO, hoje=None, maximo=LINHAS_FIM_DO_TRATAMENTO):
    """Internos ativos cujo tratamento termina em até `dias` dias — e os que JÁ passaram da previsão
    e continuam ativos (esses vêm primeiro: alguém precisa dar baixa ou prorrogar).

    A previsão é a "Tratamento mantido até" do prontuário ou, sem ela, a internação + 9 meses
    (prontuario.previsao_termino). Quem não tem data de internação não dá para estimar: não entra
    na lista, mas é contado em `sem_data` para o painel avisar.

        {"itens": [...só os `maximo` primeiros...], "total": n, "vencidos": k, "dias": dias, "sem_data": m}"""
    hoje = hoje or date.today()
    ativos = db.session.execute(db.select(Internacao).filter(Internacao.status == "ativo")).scalars().all()

    itens, sem_data = [], 0
    for i in ativos:
        if not i.inicio:
            sem_data += 1
            continue
        prevista = previsao_termino(i.inicio, i.tratamento_ate)
        restam = (prevista - hoje).days
        if restam > dias:
            continue
        duracao = (prevista - i.inicio).days
        percentual = 100 if duracao <= 0 else max(0, min(100, round((hoje - i.inicio).days * 100 / duracao)))
        itens.append({
            "nome": i.pessoa.nome, "url": url_for("ficha", id=i.id),
            "detalhe": f"{i.convenio_txt} · internado em {fmt_data(i.inicio)}",
            "previsao": prevista, "previsao_fmt": fmt_data(prevista), "restam": restam,
            "rotulo": _rotulo_do_prazo(restam), "percentual": percentual,
            "situacao": "vencido" if restam < 0 else "urgente" if restam <= URGENTE_ATE else "proximo",
        })
    itens.sort(key=lambda t: (t["restam"], t["nome"].lower()))
    return {"itens": itens[:maximo], "total": len(itens), "dias": dias, "sem_data": sem_data,
            "vencidos": sum(1 for t in itens if t["restam"] < 0)}


def agenda(dias=DIAS_DA_AGENDA, hoje=None):
    """Agendamentos de hoje até daqui a `dias` dias, agrupados por dia:
         [{"data": date, "rotulo": "Hoje", "data_curta": "sex, 09/10", "hoje": True, "eventos": [...]}, ...]"""
    hoje = hoje or date.today()
    fim = hoje + timedelta(days=dias)
    candidatos = db.session.execute(
        db.select(Internacao).filter(
            Internacao.status.in_(NA_TRIAGEM),
            or_(Internacao.data_triagem.between(hoje, fim),
                Internacao.internacao_agendada.between(hoje, fim)))).scalars().all()

    eventos = [e for i in candidatos for e in _eventos(i, hoje, fim)]
    eventos.sort(key=lambda e: (e["dia"], e["_ordem_hora"], e["nome"].lower()))

    grupos = []
    for e in eventos:
        if not grupos or grupos[-1]["data"] != e["dia"]:
            dia = e["dia"]
            rotulo = _rotulo_do_dia(dia, hoje)
            # "Hoje · sex, 09/10"; para os outros dias o rótulo já é o dia da semana: "Segunda · 12/10"
            curta = f"{DIAS_CURTOS[dia.weekday()]}, {dia:%d/%m}" if rotulo in ("Hoje", "Amanhã") else f"{dia:%d/%m}"
            grupos.append({"data": dia, "rotulo": rotulo, "hoje": dia == hoje, "data_curta": curta, "eventos": []})
        grupos[-1]["eventos"].append(e)
    return grupos
