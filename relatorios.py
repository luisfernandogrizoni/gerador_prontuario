"""
Relatórios do sistema, em Word e no navegador (veja documentos.py):

  * internos ativos por convênio (Caps AD, Prefeitura Tarumã e os convênios que forem cadastrados) — o nome sai só
    com as iniciais;
  * quantos internos passaram pela casa no ano — número geral, com colunas opcionais por convênio.

Este módulo decide o que entra em cada relatório; a aparência (timbre, tabelas, assinatura) é do documentos.py.
"""

import unicodedata
from datetime import date, datetime, timedelta, timezone

import catalogo
from documentos import N, Coluna, Documento, Paragrafo, Tabela, Texto, Titulo, fecho
from modelos import STATUS_INTERNACAO, Internacao, Pessoa, db
from prontuario import fmt_data
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


def documento_anual(hoje, colunas=(), emissor=None):
    """`colunas`: convênios (catalogo.ConvenioDef) que ganham uma coluna ao lado do total geral."""
    r = resumo_anual(hoje)
    ano, total = r["ano"], r["total"]
    verbo, substantivo = ("passaram", "internos") if total != 1 else ("passou", "interno")
    rotulos = [f"Total de internos que passaram pela casa em {ano}", f"Ingressaram em {ano}",
               f"Já estavam internados antes de 01/01/{ano}", f"Permanecem internados em {hoje.strftime('%d/%m/%Y')}",
               f"Saíram durante {ano}"]
    campos = ["total", "ingressaram", "ja_estavam", "permanecem", "sairam"]
    resumos = [r] + [resumo_anual(hoje, c.nome) for c in colunas]
    blocos = [Titulo("RELATÓRIO DE INTERNOS", tamanho=15),
              Paragrafo([N(f"Passaram pela casa em {ano}")], "centro", depois=14, tamanho=12),
              Paragrafo([f"Informamos que, de 01/01/{ano} a {hoje.strftime('%d/%m/%Y')}, {verbo} pela Comunidade Terapêutica Casa de "
                         f"Acolhida Restauração ", N(f"{total} {substantivo}"), "."], "justificado", depois=12),
              Tabela(colunas=_colunas_da_tabela_anual(colunas),
                     linhas=[[rotulo, *[x[campo] for x in resumos]] for rotulo, campo in zip(rotulos, campos)],
                     negrito_linhas=(0,))]
    blocos += fecho(hoje, emissor)
    return Documento(nome_arquivo=f"Relatório de internos {ano} - {hoje:%d-%m-%Y}", titulo=f"Relatório de internos – {ano}", blocos=blocos)


# ------------------------------------------------------------ o que a página de relatórios mostra
def painel():
    """Um bloco por convênio, com a lista de quem entra no relatório."""
    blocos = []
    for c in catalogo.atual().com_relatorio:
        itens = internos_ativos(c.slug)
        if c.ativo or itens:                      # convênio desativado só aparece enquanto ainda tem gente internada
            blocos.append({"slug": c.slug, "nome": c.nome_tela, "tipo": c.cor, "itens": itens})
    return blocos
