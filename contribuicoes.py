"""
Contribuições financeiras dos internos: o que entrou, a partir das parcelas lançadas na ficha (Parcela: número, data e valor).

  * o bloco "Contribuições do mês" do Início (`do_mes`): o que já entrou no mês, quanto se esperava de quem contribui, o que ainda falta receber no mês, a inadimplência
    (`inadimplencia`: parcelas que já venceram e não foram lançadas) e as últimas entradas;
  * o relatório do ano (`resumo_do_ano`, `documento_do_ano`): o total recebido, mês a mês, por categoria e por interno, em Word e no navegador.

Quem contribui é quem tem contribuição maior que zero (Internacao.contribuicao_valor; os convênios gratuitos ficam em R$ 0,00). O valor combinado é tratado como o valor
de cada mês: "esperado" é a soma do combinado de quem está internado e contribui, e "falta receber" é o combinado de quem não tem nenhuma parcela com data no mês. A parcela 1 vence
no dia da internação (o valor é pago no ato) e as seguintes, uma por mês, no mesmo dia, até o fim do tratamento; a inadimplência é o que já venceu e não tem parcela lançada. Parcela sem valor
informado conta como lançamento mas não entra nas somas (e a tela avisa). Registros excluídos (lixeira) não entram. Nada fica gravado: tudo é calculado a cada visita.
Dado financeiro: só quem tem a permissão `financeiro` vê (permissoes.py).
"""

import calendar
from datetime import date

from flask import url_for
from sqlalchemy.orm import joinedload, selectinload

import relatorios
from documentos import N, Coluna, Documento, Paragrafo, Tabela, Texto, Titulo, fecho
from modelos import Internacao, Parcela, Pessoa, db
from prontuario import MESES, fmt_data, fmt_reais, previsao_termino, somar_meses

LINHAS_NA_HOME = 3                      # quantas entradas e quantos em atraso aparecem no Início (o resto está no relatório)
LARGURA = 9638                          # largura útil da folha em pé, em twips (o mesmo dos outros relatórios)


def _parcelas(inicio, fim):
    """[(Parcela, Internacao)] com data de `inicio` a `fim` (inclusive), da mais nova para a mais antiga. Só de registros que não foram excluídos."""
    consulta = (db.select(Parcela, Internacao).join(Internacao, Parcela.internacao_id == Internacao.id).join(Pessoa, Internacao.pessoa_id == Pessoa.id)
                .filter(Parcela.data >= inicio, Parcela.data <= fim, Internacao.excluido_em.is_(None), Pessoa.excluido_em.is_(None))
                .order_by(Parcela.data.desc(), Parcela.id.desc()))
    return [(p, i) for p, i in db.session.execute(consulta).all()]


def _valor(parcela):
    return parcela.valor or 0.0


def _contribuintes():
    """Quem está internado e contribui (contribuição maior que zero), em ordem alfabética."""
    internacoes = db.session.execute(
        db.select(Internacao).join(Pessoa, Internacao.pessoa_id == Pessoa.id)
        .filter(Internacao.status == "ativo", Internacao.contribuicao_valor > 0, Internacao.excluido_em.is_(None), Pessoa.excluido_em.is_(None))
        .options(joinedload(Internacao.pessoa), selectinload(Internacao.parcelas))).scalars().all()
    return sorted(internacoes, key=lambda i: relatorios._chave_de_ordem(i.pessoa.nome))


def _percentual(parte, todo):
    return min(100, round(parte * 100 / todo)) if todo else 0


def do_mes(hoje, maximo=LINHAS_NA_HOME):
    """O bloco do Início: o que entrou no mês de `hoje` (as parcelas com data nele), o esperado de quem contribui, o que ainda falta receber no mês, a inadimplência (parcelas de
    meses anteriores que não foram pagas) e as últimas entradas. Devolve um dicionário só com texto e números prontos para a tela."""
    primeiro, ultimo = hoje.replace(day=1), hoje.replace(day=calendar.monthrange(hoje.year, hoje.month)[1])
    parcelas = _parcelas(primeiro, ultimo)
    recebido = sum(_valor(p) for p, _ in parcelas)
    contribuintes = _contribuintes()
    esperado = sum(i.contribuicao_valor for i in contribuintes)
    pagaram = {i.id for _, i in parcelas}
    em_aberto = [i for i in contribuintes if i.id not in pagaram]
    falta = sum(i.contribuicao_valor for i in em_aberto)
    return {
        "mes": MESES[hoje.month - 1], "ano": hoje.year,
        "recebido": recebido, "recebido_fmt": fmt_reais(recebido), "lancamentos": len(parcelas), "sem_valor": sum(1 for p, _ in parcelas if p.valor is None),
        "esperado": esperado, "esperado_fmt": fmt_reais(esperado), "percentual": _percentual(recebido, esperado),
        "contribuintes": len(contribuintes), "pagaram": len(contribuintes) - len(em_aberto),
        "a_receber": {"internos": len(em_aberto), "valor": falta, "valor_fmt": fmt_reais(falta)},
        "ultimas": [{"nome": i.pessoa.nome, "url": url_for("ficha", id=i.id, _anchor="aba-financeiro"), "valor_fmt": fmt_reais(_valor(p)) if p.valor is not None else "sem valor",
                     "data_fmt": fmt_data(p.data), "numero": p.numero} for p, i in parcelas[:maximo]],
        "inadimplencia": inadimplencia(hoje, contribuintes, maximo),
    }


def _vencimentos(internacao, hoje):
    """As datas em que as parcelas de `internacao` venceram até ontem: a 1ª no dia da internação (o valor é pago no ato) e uma por mês, no mesmo dia, enquanto durar o tratamento
    (a previsão de término ou, sem ela, 9 meses). Quem não tem data de internação não tem como saber: sem vencimentos."""
    if not internacao.inicio:
        return []
    fim = previsao_termino(internacao.inicio, internacao.tratamento_ate)
    datas, k = [], 0
    while k < 240:
        vencimento = somar_meses(internacao.inicio, k)
        if vencimento >= hoje or (fim and vencimento >= fim):
            break
        datas.append(vencimento)
        k += 1
    return datas


def inadimplencia(hoje, contribuintes=None, maximo=LINHAS_NA_HOME):
    """Quem está com parcela em atraso: de quem está internado e contribui, as parcelas que já venceram (veja _vencimentos) menos as que foram lançadas na ficha, a R$ do combinado
    cada uma. Pagar atrasado quita as mais antigas (conta a quantidade de parcelas, não o mês). `taxa`: quanto do que já venceu está em atraso. Devolve o total e os `maximo`
    que estão há mais tempo em atraso."""
    contribuintes = _contribuintes() if contribuintes is None else contribuintes
    devedores, devido = [], 0.0
    for i in contribuintes:
        vencimentos = _vencimentos(i, hoje)
        devido += len(vencimentos) * i.contribuicao_valor
        pagas = len(i.parcelas)
        if len(vencimentos) > pagas:
            em_atraso = len(vencimentos) - pagas
            devedores.append({"internacao": i, "parcelas": em_atraso, "valor": em_atraso * i.contribuicao_valor, "dias": (hoje - vencimentos[pagas]).days})
    devedores.sort(key=lambda d: (-d["dias"], relatorios._chave_de_ordem(d["internacao"].pessoa.nome)))
    valor = sum(d["valor"] for d in devedores)
    return {"internos": len(devedores), "parcelas": sum(d["parcelas"] for d in devedores), "valor": valor, "valor_fmt": fmt_reais(valor), "taxa": _percentual(valor, devido),
            "itens": [{"nome": d["internacao"].pessoa.nome, "url": url_for("ficha", id=d["internacao"].id, _anchor="aba-financeiro"), "valor_fmt": fmt_reais(d["valor"]),
                       "detalhe": f"{d['parcelas']} parcela{'s' if d['parcelas'] != 1 else ''} · há {_tempo(d['dias'])}"} for d in devedores[:maximo]]}


def _tempo(dias):
    """'12 dias', '1 mês', '3 meses' (o atraso mais antigo de quem está devendo)."""
    if dias < 60:
        return f"{dias} dia{'s' if dias != 1 else ''}"
    meses = round(dias / 30.44)
    return f"{meses} meses"


# ------------------------------------------------------------ o relatório do ano
def anos_disponiveis(hoje):
    """Os anos com contribuição lançada e o ano de `hoje`, do mais novo para o mais antigo (para escolher o relatório)."""
    anos = {hoje.year}
    for (data,) in db.session.execute(db.select(Parcela.data).join(Internacao, Parcela.internacao_id == Internacao.id)
                                      .filter(Parcela.data.is_not(None), Internacao.excluido_em.is_(None)).distinct()).all():
        anos.add(data.year)
    return sorted(anos, reverse=True)


def resumo_do_ano(ano, hoje, anonimo=True):
    """O que entrou em `ano`: total, mês a mês, por categoria e por interno (uma linha por pessoa). Cada contribuição vem da parcela lançada na ficha.
    `anonimo`: o nome do interno sai só com as iniciais (o padrão dos relatórios) ou completo."""
    parcelas = _parcelas(date(ano, 1, 1), date(ano, 12, 31))
    meses = [{"numero": m, "nome": MESES[m - 1].capitalize(), "lancamentos": 0, "valor": 0.0} for m in range(1, 13)]
    categorias, pessoas = {}, {}
    for p, i in parcelas:
        mes = meses[p.data.month - 1]
        mes["lancamentos"] += 1
        mes["valor"] += _valor(p)
        cat = categorias.setdefault(i.categoria, {"categoria": i.categoria, "pessoas": set(), "lancamentos": 0, "valor": 0.0})
        cat["pessoas"].add(i.pessoa_id)
        cat["lancamentos"] += 1
        cat["valor"] += _valor(p)
        quem = pessoas.setdefault(i.pessoa_id, {"pessoa": i.pessoa, "categorias": set(), "lancamentos": 0, "valor": 0.0})
        quem["categorias"].add(i.categoria)
        quem["lancamentos"] += 1
        quem["valor"] += _valor(p)
    internos = [{"quem": relatorios.nome_no_relatorio(x["pessoa"], anonimo), "categoria": " / ".join(sorted(x["categorias"])), "lancamentos": x["lancamentos"], "valor": x["valor"],
                 "_ordem": relatorios._chave_de_ordem(x["pessoa"].nome)} for x in pessoas.values()]
    internos.sort(key=lambda x: x["_ordem"])
    por_categoria = sorted(({"categoria": c["categoria"], "pessoas": len(c["pessoas"]), "lancamentos": c["lancamentos"], "valor": c["valor"]} for c in categorias.values()),
                           key=lambda c: (-c["valor"], c["categoria"]))
    return {"ano": ano, "ate": min(hoje, date(ano, 12, 31)) if ano == hoje.year else date(ano, 12, 31), "total": sum(m["valor"] for m in meses),
            "lancamentos": len(parcelas), "pessoas": len(pessoas), "sem_valor": sum(1 for p, _ in parcelas if p.valor is None),
            "meses": meses, "categorias": por_categoria, "internos": internos}


def aviso_do_ano(resumo):
    """Texto de alerta para a tela (nunca vai para o documento), ou '' quando está tudo certo."""
    n = resumo["sem_valor"]
    if not n:
        return ""
    return (f"{n} contribuição{'ões' if n != 1 else ''} lançada{'s' if n != 1 else ''} sem valor informado não {'entram' if n != 1 else 'entra'} nas somas. "
            "Corrija o valor na aba Financeiro da ficha de cada interno.")


def _tabela(colunas, linhas, total):
    """Tabela com a última linha (o total) em negrito."""
    return Tabela(colunas=colunas, linhas=[*linhas, total], negrito_linhas=(len(linhas),))


def documento_do_ano(ano, hoje, emissor=None, anonimo=True):
    """O relatório de contribuições recebidas em `ano` (Documento, documentos.py): o total, o mês a mês, por categoria e por interno."""
    r = resumo_do_ano(ano, hoje, anonimo)
    periodo = f"de 01/01/{ano} a {fmt_data(r['ate'])}"
    blocos = [Titulo("RELATÓRIO DE CONTRIBUIÇÕES RECEBIDAS", tamanho=15),
              Paragrafo([N(f"Ano de {ano}")], "centro", depois=14, tamanho=12)]
    if not r["lancamentos"]:
        blocos.append(Paragrafo([Texto(f"Não há contribuições lançadas {periodo}.", italico=True)], "centro", antes=10))
    else:
        plural = "lançamentos" if r["lancamentos"] != 1 else "lançamento"
        pessoas = f"{r['pessoas']} interno{'s' if r['pessoas'] != 1 else ''}"
        blocos += [
            Paragrafo([f"Informamos que, {periodo}, a Comunidade Terapêutica Casa de Acolhida Restauração recebeu ", N(fmt_reais(r["total"])),
                       f" em contribuições, em {r['lancamentos']} {plural} de {pessoas}."], "justificado", depois=12),
            Paragrafo([N("Mês a mês")], antes=6, depois=6, unido_ao_proximo=True),
            _tabela([Coluna("Mês", LARGURA - 5600), Coluna("Lançamentos", 2000, "centro"), Coluna("Valor recebido", 3600, "direita")],
                    [[m["nome"], m["lancamentos"], fmt_reais(m["valor"])] for m in r["meses"]],
                    ["Total do ano", r["lancamentos"], fmt_reais(r["total"])]),
            Paragrafo([N("Por categoria")], antes=18, depois=6, unido_ao_proximo=True),
            _tabela([Coluna("Categoria", LARGURA - 6400), Coluna("Internos", 1500, "centro"), Coluna("Lançamentos", 1900, "centro"), Coluna("Valor recebido", 3000, "direita")],
                    [[c["categoria"], c["pessoas"], c["lancamentos"], fmt_reais(c["valor"])] for c in r["categorias"]],
                    ["Total", r["pessoas"], r["lancamentos"], fmt_reais(r["total"])]),
            Paragrafo([N("Por interno")], antes=18, depois=6, unido_ao_proximo=True),
            _tabela([Coluna("Nº", 600, "centro"), Coluna("Interno", LARGURA - 600 - 2400 - 1500 - 2000), Coluna("Categoria", 2400), Coluna("Lançamentos", 1500, "centro"),
                     Coluna("Valor recebido", 2000, "direita")],
                    [[n, x["quem"], x["categoria"], x["lancamentos"], fmt_reais(x["valor"])] for n, x in enumerate(r["internos"], 1)],
                    ["", f"Total ({pessoas})", "", r["lancamentos"], fmt_reais(r["total"])]),
        ]
        if r["sem_valor"]:
            blocos.append(Paragrafo([Texto(f"{r['sem_valor']} lançamento{'s' if r['sem_valor'] != 1 else ''} sem valor informado não entra{'m' if r['sem_valor'] != 1 else ''} nas somas.", italico=True)],
                                    antes=10, tamanho=10))
    blocos += fecho(hoje, emissor)
    return Documento(nome_arquivo=f"Contribuições {ano} - {hoje:%d-%m-%Y}", titulo=f"Relatório de contribuições – {ano}", blocos=blocos)
