"""
Relatórios do sistema, em Word e no navegador (veja documentos.py):

  * internos ativos por convênio (Caps AD, Prefeitura Tarumã e os convênios que forem cadastrados) — o nome sai só
    com as iniciais;
  * quantos internos passaram pela casa no ano — número geral, com colunas opcionais por convênio e, se a pessoa pedir, o detalhamento das internações
    realizadas em cada mês escolhido (quem foi internado, em qual convênio, quando e como está), antes do mesmo resumo de sempre.

Este módulo decide o que entra em cada relatório; a aparência (timbre, tabelas, assinatura) é do documentos.py.
"""

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

import catalogo
from documentos import N, Coluna, Documento, Paragrafo, Tabela, Texto, Titulo, fecho
from modelos import STATUS_INTERNACAO, Internacao, Pessoa, db
from prontuario import MESES, fmt_data
from validacao import fmt_cpf

# partes de nome que não viram inicial ("Maria da Silva" -> "M. S.")
LIGACOES = {"da", "de", "do", "das", "dos", "e", "di", "du", "del", "von", "van"}
SEM_DADO = "—"


def hoje_no_brasil():
    """Data de hoje em Brasília (UTC-3, sem horário de verão desde 2019), mesmo que o servidor rode em UTC."""
    return datetime.now(timezone(timedelta(hours=-3))).date()


# ------------------------------------------------------------ internos ativos por convênio
def iniciais(nome):
    """'João Álvaro da Silva' -> 'J. Á. S.' (ligações como 'da' e 'de' não contam; números e símbolos são ignorados)."""
    partes = (nome or "").split()
    letras = []
    for posicao, parte in enumerate(partes):
        if posicao > 0 and parte.lower() in LIGACOES:
            continue
        primeira = next((c for c in parte if c.isalpha()), "")
        if primeira:
            letras.append(primeira.upper() + ".")
    return " ".join(letras) or SEM_DADO


def endereco_completo(pessoa):
    """'Rua X, 123 – Centro – Assis/SP' (sem as partes que faltam)."""
    rua = ", ".join(p for p in (pessoa.endereco, pessoa.numero) if p)
    cidade = "/".join(p for p in (pessoa.cidade, (pessoa.estado or "").upper()) if p)
    return " – ".join(p for p in (rua, pessoa.bairro, cidade) if p) or SEM_DADO


def _chave_de_ordem(nome):
    """Ordem alfabética sem ligar para acento nem maiúscula."""
    sem_acento = unicodedata.normalize("NFKD", nome or "")
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).casefold()


def convenio_do_relatorio(slug):
    """O convênio (catalogo.ConvenioDef) do endereço do relatório, ou None se não existir ou não tiver relatório."""
    convenio = catalogo.atual().por_slug(slug)
    return convenio if convenio and convenio.gratuito else None


def internos_ativos(slug):
    """Internos ativos do convênio, em ordem alfabética do nome: lista de dicionários para a tela e o Word."""
    internacoes = db.session.execute(
        db.select(Internacao).join(Pessoa).filter(Internacao.status == "ativo", Internacao.convenio == convenio_do_relatorio(slug).nome)
    ).scalars().all()
    internacoes.sort(key=lambda i: _chave_de_ordem(i.pessoa.nome))
    return [{
        "iniciais": iniciais(i.pessoa.nome),
        "cpf": fmt_cpf(i.pessoa.cpf) if i.pessoa.cpf else SEM_DADO,
        "endereco": endereco_completo(i.pessoa),
        "internacao": fmt_data(i.inicio) or SEM_DADO,
    } for i in internacoes]


def documento_convenio(slug, hoje, emissor=None):
    convenio = convenio_do_relatorio(slug).nome
    itens = internos_ativos(slug)
    blocos = [Titulo("RELATÓRIO DE INTERNOS ATIVOS", tamanho=15),
              Paragrafo([N(f"Convênio: {convenio}")], "centro", depois=14, tamanho=12),
              Paragrafo([f"Relação dos acolhidos que se encontram em tratamento nesta Comunidade Terapêutica, participantes "
                         f"do convênio com {convenio}, em {hoje.strftime('%d/%m/%Y')}."], "justificado", depois=10)]
    if itens:
        blocos.append(Tabela(
            colunas=[Coluna("Nº", 480, "centro"), Coluna("Iniciais", 1150, "centro"), Coluna("CPF", 1700, "centro"),
                     Coluna("Endereço", 4258), Coluna("Data de internação", 2050, "centro")],
            linhas=[[n, i["iniciais"], i["cpf"], i["endereco"], i["internacao"]] for n, i in enumerate(itens, 1)]))
        blocos.append(Paragrafo([N(f"Total de internos ativos: {len(itens)}")], antes=10))
    else:
        blocos.append(Paragrafo([Texto("Não há internos ativos neste convênio na data do relatório.", italico=True)], "centro", antes=10))
    blocos += fecho(hoje, emissor)
    return Documento(nome_arquivo=f"Relatório {convenio} - {hoje:%d-%m-%Y}", titulo=f"Relatório de internos ativos – {convenio}",
                     blocos=blocos)


# ------------------------------------------------------------ quantos passaram pela casa no ano
def resumo_anual(hoje, convenio=None):
    """
    Pessoas que estiveram internadas em algum momento do ano de `hoje` (de 1º de janeiro até hoje).

    Conta pessoas, não internações: quem saiu e voltou no mesmo ano conta uma vez. Registros sem a data necessária
    para saber se estavam na casa no ano não entram e são avisados em `sem_data`.

    `convenio` (nome guardado) faz a mesma conta só com os registros daquele convênio: é a coluna do convênio no
    relatório. Quem passou por mais de um convênio no ano aparece em cada um deles.
    """
    ano, inicio_do_ano = hoje.year, date(hoje.year, 1, 1)
    consulta = db.select(Internacao).filter(Internacao.status.in_(STATUS_INTERNACAO))
    if convenio is not None:
        consulta = consulta.filter(Internacao.convenio == convenio)
    registros = db.session.execute(consulta).scalars().all()
    por_pessoa, sem_data = {}, 0
    for r in registros:
        if r.inicio is None:                                  # sem data de internação: não dá para saber
            sem_data += 1
            continue
        if r.inicio > hoje:                                   # data no futuro (erro de digitação): ainda não passou
            continue
        if r.status == "inativo" and r.termino is None and r.inicio < inicio_do_ano:
            sem_data += 1                                     # saiu em data desconhecida: pode ter sido antes do ano
            continue
        if r.status == "inativo" and r.termino is not None and r.termino < inicio_do_ano:
            continue                                          # saiu antes do ano começar
        por_pessoa.setdefault(r.pessoa_id, []).append(r)
    total = len(por_pessoa)
    ingressaram = permanecem = 0
    for registros_da_pessoa in por_pessoa.values():
        primeiro = min(registros_da_pessoa, key=lambda r: r.inicio)
        ingressaram += primeiro.inicio >= inicio_do_ano
        permanecem += any(r.status == "ativo" for r in registros_da_pessoa)
    return {"ano": ano, "total": total, "ingressaram": ingressaram, "ja_estavam": total - ingressaram,
            "permanecem": permanecem, "sairam": total - permanecem, "sem_data": sem_data}


def aviso_do_resumo(resumo):
    """Texto de alerta para a tela (nunca vai para o documento), ou '' quando está tudo certo."""
    n = resumo["sem_data"]
    if not n:
        return ""
    return (f"{n} registro{'s' if n != 1 else ''} sem data de internação ou de saída não "
            f"{'entraram' if n != 1 else 'entrou'} na contagem. Corrija nas fichas (veja os avisos da tela inicial).")


def colunas_disponiveis(hoje):
    """Convênios que podem virar coluna do relatório anual: os ativos e os desativados que tiveram internos no ano.
    Um convênio novo, cadastrado em Cadastros > Convênios, entra aqui sozinho."""
    return [c for c in catalogo.atual().com_relatorio if c.ativo or resumo_anual(hoje, c.nome)["total"]]


LARGURA_DA_TABELA = 9638        # largura útil da folha, em twips (7338 + 2300 na tabela de uma coluna só)


def _colunas_da_tabela_anual(convenios):
    """Descrição + geral (+ uma coluna para cada convênio). Sem convênios, a tabela é a de sempre."""
    if not convenios:
        return [Coluna("Descrição", 7338), Coluna("Internos", 2300, "centro")]
    k = 1 + len(convenios)
    numerica = 1450 if k <= 3 else 1250 if k <= 5 else 1050
    return [Coluna("Descrição", LARGURA_DA_TABELA - k * numerica), Coluna("Internos (geral)", numerica, "centro"),
            *[Coluna(c.nome_tela, numerica, "centro") for c in convenios]]


def documento_anual(hoje, colunas=(), emissor=None, meses=()):
    """`colunas`: convênios (catalogo.ConvenioDef) que ganham uma coluna ao lado do total geral. `meses`: [(ano, mês)] cujas internações são detalhadas
    antes do resumo (veja ler_meses); sem eles o documento é o resumo de sempre."""
    r = resumo_anual(hoje)
    ano, total = r["ano"], r["total"]
    verbo, substantivo = ("passaram", "internos") if total != 1 else ("passou", "interno")
    rotulos = [f"Total de internos que passaram pela casa em {ano}", f"Ingressaram em {ano}",
               f"Já estavam internados antes de 01/01/{ano}", f"Permanecem internados em {hoje.strftime('%d/%m/%Y')}",
               f"Saíram durante {ano}"]
    campos = ["total", "ingressaram", "ja_estavam", "permanecem", "sairam"]
    resumos = [r] + [resumo_anual(hoje, c.nome) for c in colunas]
    detalhes = blocos_dos_meses(meses, hoje)
    blocos = [Titulo("RELATÓRIO DE INTERNOS", tamanho=15),
              *detalhes,
              Paragrafo([N(f"Passaram pela casa em {ano}")], "centro", antes=24 if detalhes else 0, depois=14, tamanho=12),
              Paragrafo([f"Informamos que, de 01/01/{ano} a {hoje.strftime('%d/%m/%Y')}, {verbo} pela Comunidade Terapêutica Casa de "
                         f"Acolhida Restauração ", N(f"{total} {substantivo}"), "."], "justificado", depois=12),
              Tabela(colunas=_colunas_da_tabela_anual(colunas),
                     linhas=[[rotulo, *[x[campo] for x in resumos]] for rotulo, campo in zip(rotulos, campos)],
                     negrito_linhas=(0,))]
    blocos += fecho(hoje, emissor)
    return Documento(nome_arquivo=f"Relatório de internos {ano} - {hoje:%d-%m-%Y}", titulo=f"Relatório de internos – {ano}", blocos=blocos)


# ------------------------------------------------------------ internações realizadas em cada mês (o detalhamento opcional)
LIMITE_DE_MESES = 120
SITUACAO_SEM_SAIDA = "Saída sem data registrada"


def meses_disponiveis(hoje, marcados=()):
    """Os anos e meses em que a casa internou alguém (até hoje), do ano mais novo para o mais antigo, para escolher o que detalhar:
    [{"ano": 2026, "meses": [{"chave": "2026-08", "nome": "ago", "total": 11, "marcado": True}, ...]}]. O mês é o da data de internação
    (só conta quem foi internado: a triagem e a desistência não entram). `marcados`: conjunto de (ano, mês) já escolhidos."""
    datas = db.session.execute(db.select(Internacao.inicio).filter(Internacao.status.in_(STATUS_INTERNACAO), Internacao.inicio.is_not(None),
                                                                   Internacao.inicio <= hoje)).scalars().all()
    por_mes = {}
    for d in datas:
        por_mes[(d.year, d.month)] = por_mes.get((d.year, d.month), 0) + 1
    if not por_mes:
        return []
    return [{"ano": ano, "meses": [{"chave": f"{ano}-{mes:02d}", "nome": MESES[mes - 1][:3], "total": por_mes.get((ano, mes), 0), "marcado": (ano, mes) in marcados}
                                   for mes in range(1, (hoje.month if ano == hoje.year else 12) + 1)]}
            for ano in range(hoje.year, min(a for a, _ in por_mes) - 1, -1)]


def ler_meses(textos, hoje):
    """Os meses pedidos em ?mes=2026-08&mes=2026-09: só os que existem e não são futuros, sem repetir, do mais antigo para o mais novo."""
    pedidos = set()
    for texto in textos[:2 * LIMITE_DE_MESES]:
        m = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", (texto or "").strip())
        if m and 2000 <= int(m[1]) and (int(m[1]), int(m[2])) <= (hoje.year, hoje.month):
            pedidos.add((int(m[1]), int(m[2])))
    return sorted(pedidos)[:LIMITE_DE_MESES]


def _limites_do_mes(ano, mes):
    return date(ano, mes, 1), date(ano + (mes == 12), mes % 12 + 1, 1)


def _situacao(internacao):
    if internacao.status == "ativo":
        return "Em tratamento"
    return f"Saiu em {fmt_data(internacao.termino)}" if internacao.termino else SITUACAO_SEM_SAIDA


def internacoes_do_mes(ano, mes, hoje):
    """As internações realizadas no mês (data de internação dentro dele), da mais antiga para a mais nova: iniciais, convênio, data e situação de agora."""
    primeiro, proximo = _limites_do_mes(ano, mes)
    registros = db.session.execute(db.select(Internacao).join(Pessoa).filter(
        Internacao.status.in_(STATUS_INTERNACAO), Internacao.inicio >= primeiro, Internacao.inicio < proximo, Internacao.inicio <= hoje)).scalars().all()
    registros.sort(key=lambda i: (i.inicio, _chave_de_ordem(i.pessoa.nome)))
    cadastro = catalogo.atual()
    return [{"iniciais": iniciais(i.pessoa.nome), "convenio": cadastro.nome_na_tela(i.convenio) or SEM_DADO, "internacao": fmt_data(i.inicio),
             "situacao": _situacao(i)} for i in registros]


def resumo_do_mes(ano, mes, internacoes):
    """Os números do mês: quantas internações (as `internacoes` do mês), quantas por convênio (as mais numerosas primeiro) e quantas pessoas saíram no mês."""
    primeiro, proximo = _limites_do_mes(ano, mes)
    por_convenio = {}
    for i in internacoes:
        por_convenio[i["convenio"]] = por_convenio.get(i["convenio"], 0) + 1
    saidas = db.session.execute(db.select(db.func.count()).select_from(Internacao).filter(
        Internacao.status == "inativo", Internacao.termino >= primeiro, Internacao.termino < proximo)).scalar()
    return {"total": len(internacoes), "por_convenio": sorted(por_convenio.items(), key=lambda par: (-par[1], par[0])), "saidas": saidas}


def blocos_dos_meses(meses, hoje):
    """O detalhamento no documento: para cada mês, o título com o total, os números do mês e a tabela das internações."""
    if not meses:
        return []
    blocos = [Paragrafo([N("Internações realizadas por mês")], "centro", depois=6, tamanho=12)]
    for ano, mes in meses:
        itens = internacoes_do_mes(ano, mes, hoje)
        r = resumo_do_mes(ano, mes, itens)
        total = r["total"]
        blocos.append(Paragrafo([N(f"{MESES[mes - 1].capitalize()} de {ano} – {total} {'internação' if total == 1 else 'internações'}")],
                                antes=16, depois=3, tamanho=12, unido_ao_proximo=True))
        numeros = []
        if r["por_convenio"]:
            numeros.append("Por convênio: " + " · ".join(f"{nome} {n}" for nome, n in r["por_convenio"]) + ".")
        numeros.append(f"Saíram no mês: {r['saidas']}.")
        blocos.append(Paragrafo([" ".join(numeros)], tamanho=11, depois=6, unido_ao_proximo=bool(itens)))
        if itens:
            blocos.append(Tabela(colunas=[Coluna("Nº", 480, "centro"), Coluna("Iniciais", 1500, "centro"), Coluna("Convênio", 2400), Coluna("Data de internação", 1900, "centro"),
                                          Coluna("Situação", 3358)],
                                 linhas=[[n, i["iniciais"], i["convenio"], i["internacao"], i["situacao"]] for n, i in enumerate(itens, 1)]))
        else:
            blocos.append(Paragrafo([Texto("Nenhuma internação realizada neste mês.", italico=True)], "centro", antes=4))
    return blocos


# ------------------------------------------------------------ o que a página de relatórios mostra
def painel():
    """Um bloco por convênio, com a lista de quem entra no relatório."""
    blocos = []
    for c in catalogo.atual().com_relatorio:
        itens = internos_ativos(c.slug)
        if c.ativo or itens:                      # convênio desativado só aparece enquanto ainda tem gente internada
            blocos.append({"slug": c.slug, "nome": c.nome_tela, "tipo": c.cor, "itens": itens})
    return blocos
