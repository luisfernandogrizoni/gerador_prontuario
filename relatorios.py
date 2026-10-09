"""
Relatórios do sistema, em Word e no navegador (veja documentos.py):

  * internos ativos por convênio (Caps AD e Prefeitura Tarumã) — o nome sai só com as iniciais;
  * quantos internos passaram pela casa no ano — número geral, sem separar por convênio.

Este módulo decide o que entra em cada relatório; a aparência (timbre, tabelas, assinatura) é do documentos.py.
"""

import unicodedata
from datetime import date, datetime, timedelta, timezone

from documentos import N, Coluna, Documento, Paragrafo, Tabela, Texto, Titulo, fecho
from modelos import STATUS_INTERNACAO, Internacao, Pessoa, db
from prontuario import NOME_NA_TELA, TIPO_DA_CATEGORIA, fmt_data
from validacao import fmt_cpf

# endereço da URL -> convênio como está guardado no banco
CONVENIOS = {"caps-ad": "CAPS AD", "taruma": "Prefeitura Tarumã"}

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


def internos_ativos(slug):
    """Internos ativos do convênio, em ordem alfabética do nome: lista de dicionários para a tela e o Word."""
    internacoes = db.session.execute(
        db.select(Internacao).join(Pessoa).filter(Internacao.status == "ativo", Internacao.convenio == CONVENIOS[slug])
    ).scalars().all()
    internacoes.sort(key=lambda i: _chave_de_ordem(i.pessoa.nome))
    return [{
        "iniciais": iniciais(i.pessoa.nome),
        "cpf": fmt_cpf(i.pessoa.cpf) if i.pessoa.cpf else SEM_DADO,
        "endereco": endereco_completo(i.pessoa),
        "internacao": fmt_data(i.inicio) or SEM_DADO,
    } for i in internacoes]


def documento_convenio(slug, hoje):
    convenio = CONVENIOS[slug]
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
    blocos += fecho(hoje)
    return Documento(nome_arquivo=f"Relatório {convenio} - {hoje:%d-%m-%Y}", titulo=f"Relatório de internos ativos – {convenio}",
                     blocos=blocos)


# ------------------------------------------------------------ quantos passaram pela casa no ano
def resumo_anual(hoje):
    """
    Pessoas que estiveram internadas em algum momento do ano de `hoje` (de 1º de janeiro até hoje).

    Conta pessoas, não internações: quem saiu e voltou no mesmo ano conta uma vez. Registros sem a data necessária
    para saber se estavam na casa no ano não entram e são avisados em `sem_data`.
    """
    ano, inicio_do_ano = hoje.year, date(hoje.year, 1, 1)
    registros = db.session.execute(db.select(Internacao).filter(Internacao.status.in_(STATUS_INTERNACAO))).scalars().all()
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


def documento_anual(hoje):
    r = resumo_anual(hoje)
    ano, total = r["ano"], r["total"]
    verbo, substantivo = ("passaram", "internos") if total != 1 else ("passou", "interno")
    blocos = [Titulo("RELATÓRIO DE INTERNOS", tamanho=15),
              Paragrafo([N(f"Passaram pela casa em {ano}")], "centro", depois=14, tamanho=12),
              Paragrafo([f"Informamos que, de 01/01/{ano} a {hoje.strftime('%d/%m/%Y')}, {verbo} pela Comunidade Terapêutica Casa de "
                         f"Acolhida Restauração ", N(f"{total} {substantivo}"), "."], "justificado", depois=12),
              Tabela(colunas=[Coluna("Descrição", 7338), Coluna("Internos", 2300, "centro")],
                     linhas=[[f"Total de internos que passaram pela casa em {ano}", total],
                             [f"Ingressaram em {ano}", r["ingressaram"]],
                             [f"Já estavam internados antes de 01/01/{ano}", r["ja_estavam"]],
                             [f"Permanecem internados em {hoje.strftime('%d/%m/%Y')}", r["permanecem"]],
                             [f"Saíram durante {ano}", r["sairam"]]],
                     negrito_linhas=(0,))]
    blocos += fecho(hoje)
    return Documento(nome_arquivo=f"Relatório de internos {ano} - {hoje:%d-%m-%Y}", titulo=f"Relatório de internos – {ano}", blocos=blocos)


# ------------------------------------------------------------ o que a página de relatórios mostra
def painel():
    """Um bloco por convênio, com a lista de quem entra no relatório."""
    blocos = []
    for slug, convenio in CONVENIOS.items():
        nome = NOME_NA_TELA.get(convenio, convenio)
        blocos.append({"slug": slug, "nome": nome, "tipo": TIPO_DA_CATEGORIA.get(nome, "outro"), "itens": internos_ativos(slug)})
    return blocos
