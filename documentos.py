"""
Motor dos documentos do sistema: prontuário, declarações e relatórios.

Cada documento é descrito UMA vez, como uma lista de blocos (título, parágrafo, tabela, formulário, assinatura…),
e este módulo o transforma em duas coisas:

  * um arquivo Word (.docx), com o timbre montado aqui mesmo — não há arquivo de modelo guardado em pasta;
  * uma página HTML (templates/documento.html) para ver e imprimir no navegador, com o mesmo timbre.

O texto do timbre mora em CABECALHO e RODAPE (abaixo) e as duas logos em static/timbre/: é o único lugar a mexer
quando o endereço, o CNPJ ou a logo mudarem. O texto de cada documento mora no módulo dele (prontuario.py,
declaracoes.py, relatorios.py).

Uma página nova começa onde um parágrafo tem `quebra_antes`; no Word isso é uma quebra de página e no navegador
cada página vira uma folha A4 com o seu timbre.
"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import ClassVar

from docx import Document as DocxDocument
from docx.enum.table import WD_ALIGN_VERTICAL, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor, Twips

PASTA_TIMBRE = Path(__file__).parent / "static" / "timbre"
LOGO_TOPO = PASTA_TIMBRE / "logo-topo.jpg"
LOGO_RODAPE = PASTA_TIMBRE / "logo-rodape.jpg"

# quem emite (e assina) as declarações e os relatórios
EMISSOR_NOME = "Luís Fernando Grizoni Elias"
EMISSOR_CARGO = "Assistente Administrativo"
CIDADE = "Assis"

# ----------------------------------------------------------------- timbre
# Cada linha é uma lista de trechos (texto, estilo); estilo: "b" negrito, "vermelho", "link", "serifa".
CABECALHO = [
    [("Comunidade Terapêutica", "b")],
    [("Casa de Acolhida Restauração", "b")],
    [("Por uma só vida já valeu a pena!", "b vermelho")],
    [("Rodovia Raposo Tavares, km 435 – Assis – SP, Caixa Postal: 818", "")],
]
RODAPE = [
    [("Associação Restauração - ", "b serifa"), ("Nossa Missão é Amar", "b vermelho")],
    [("Escritório: Rua Sebastião da Silva Leite 1145 – Centro – Assis – São Paulo.", "")],
    [("Telefone: (18) 3323-4778 (18) 99618-1905 CEP 19814-371", "")],
    [("CNPJ 03.508.198/0001-07", "")],
    [("UTILIDADE PÚBLICA MUNICIPAL: Lei nº 3960/2000", "")],
    [("UTILIDADE PÚBLICA ESTADUAL: Lei nº 17531/2022", "")],
    [("www.restauração.org.br", "link"), ("    ", ""), ("restauração@restauração.org.br", "link")],
]
TAMANHO_CABECALHO, TAMANHO_RODAPE = 10, 9

# página A4 (em twips: 1 cm = 567). Em cima e embaixo a margem é a do prontuário; dos lados cada documento escolhe.
LARGURA_PAGINA = 11906
MARGEM_VERTICAL, MARGEM_LATERAL_PADRAO, DISTANCIA_TIMBRE = 720, 1134, 708


# ----------------------------------------------------------------- blocos
@dataclass
class Texto:
    """Um trecho de parágrafo com formatação própria."""
    texto: str
    negrito: bool = False
    italico: bool = False
    sublinhado: bool = False


def N(texto):
    """Atalho: trecho em negrito."""
    return Texto(texto, negrito=True)


def S(texto):
    """Atalho: trecho sublinhado."""
    return Texto(texto, sublinhado=True)


@dataclass
class Titulo:
    tipo: ClassVar[str] = "titulo"
    texto: str
    tamanho: float = 15
    antes: float = 6
    depois: float = 2


@dataclass
class Paragrafo:
    tipo: ClassVar[str] = "paragrafo"
    partes: list                       # str ou Texto
    alinhamento: str = "esquerda"      # esquerda | centro | direita | justificado
    antes: float = 0                   # pontos
    depois: float = 0
    primeira_linha: int = 0            # recuo da primeira linha, em twips
    entrelinha: float = 1.0
    tamanho: float | None = None       # None = tamanho do documento
    unido_ao_proximo: bool = False
    recuo: int = 0                     # recuo da esquerda, em twips
    suspenso: int = 0                  # recuo "pendurado" (usado nos itens numerados), em twips
    numero: str = ""                   # "1." — marca do item de uma lista numerada
    quebra_antes: bool = False         # começa uma página nova
    fonte: str | None = None           # None = fonte do documento

    def trechos(self):
        return [p if isinstance(p, Texto) else Texto(p) for p in self.partes]


@dataclass
class Coluna:
    titulo: str
    largura: int                       # twips
    alinhamento: str = "esquerda"


@dataclass
class Tabela:
    tipo: ClassVar[str] = "tabela"
    colunas: list
    linhas: list                       # lista de listas de texto
    negrito_linhas: tuple = ()         # posições (a partir de 0) das linhas em negrito
    antes: float = 0
    tamanho: float = 10
    cabecalho: bool = True             # a primeira linha da tabela é o título das colunas
    sombreado: bool = True             # título das colunas com fundo cinza
    cor_borda: str = "808080"
    altura_cabecalho: int = 0          # altura mínima da linha do título, em twips
    sem_bordas: bool = False

    def largura_total(self):
        return sum(c.largura for c in self.colunas)

    def porcentagens(self):
        total = self.largura_total()
        return [round(c.largura * 100 / total, 2) for c in self.colunas]


@dataclass
class Celula:
    texto: str = ""
    span: int = 1                      # quantas colunas da grade a célula ocupa
    negrito: bool = False


@dataclass
class Formulario:
    """Tabela de formulário: grade de colunas fina e células que ocupam várias colunas (a ficha de controle)."""
    tipo: ClassVar[str] = "formulario"
    grade: list                        # largura de cada coluna da grade, em twips
    linhas: list                       # lista de listas de Celula (a soma dos spans de cada linha é len(grade))
    alturas: list                      # altura mínima de cada linha, em twips
    tamanho: float = 12
    antes: float = 0

    def largura_total(self):
        return sum(self.grade)


@dataclass
class Pauta:
    """Linhas horizontais para escrever à mão."""
    tipo: ClassVar[str] = "pauta"
    linhas: int
    altura: float = 19                 # pontos entre uma linha e outra
    antes: float = 0


@dataclass
class Assinaturas:
    """Linhas de assinatura lado a lado, cada uma com o seu rótulo embaixo."""
    tipo: ClassVar[str] = "assinaturas"
    rotulos: list
    comprimento: int = 32              # tamanho de cada traço, em sublinhados
    tamanho_rotulo: float = 10
    antes: float = 0


@dataclass
class Assinatura:
    """Linha de assinatura com nome, cargo e o papel de quem assina."""
    tipo: ClassVar[str] = "assinatura"
    nome: str = EMISSOR_NOME
    cargo: str = EMISSOR_CARGO
    papel: str = "Responsável pela emissão"
    antes: float = 40


@dataclass
class Documento:
    nome_arquivo: str                  # sem a extensão
    titulo: str                        # aparece na aba do navegador e nas propriedades do Word
    blocos: list
    fonte: str = "Arial"
    tamanho: float = 11
    voltar: str = ""                   # endereço da página de onde o documento foi aberto
    margem_lateral: int = MARGEM_LATERAL_PADRAO

    @property
    def largura_util(self):
        return LARGURA_PAGINA - 2 * self.margem_lateral

    def paginas(self):
        """Os blocos separados em páginas: uma nova a cada bloco com quebra_antes."""
        paginas = []
        for bloco in self.blocos:
            if getattr(bloco, "quebra_antes", False) or not paginas:
                paginas.append([])
            paginas[-1].append(bloco)
        return paginas


ALINHAMENTO_DOCX = {"esquerda": WD_ALIGN_PARAGRAPH.LEFT, "centro": WD_ALIGN_PARAGRAPH.CENTER,
                    "direita": WD_ALIGN_PARAGRAPH.RIGHT, "justificado": WD_ALIGN_PARAGRAPH.JUSTIFY}


def data_por_extenso(d):
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
             "outubro", "novembro", "dezembro"]
    return f"{d.day:02d} de {meses[d.month - 1]} de {d.year}"


def fecho(hoje):
    """'Assis, 09 de outubro de 2026.' alinhado à direita, seguido da assinatura de quem emite."""
    return [Paragrafo([f"{CIDADE}, {data_por_extenso(hoje)}."], "direita", antes=26, unido_ao_proximo=True), Assinatura()]


# ============================================================ gerador do Word
def _fonte(run, nome, tamanho, negrito=False, italico=False, cor=None, sublinhado=False):
    run.bold, run.italic, run.underline = negrito, italico, sublinhado
    run.font.size = Pt(tamanho)
    run.font.name = nome
    if cor:
        run.font.color.rgb = RGBColor.from_string(cor)
    fontes = run._element.get_or_add_rPr().get_or_add_rFonts()
    for atributo in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fontes.set(qn(atributo), nome)


def _filho(elemento, nome, **atributos):
    novo = OxmlElement(nome)
    for chave, valor in atributos.items():
        novo.set(qn("w:" + chave), str(valor))
    elemento.append(novo)
    return novo


# ordem em que o Word exige os elementos de propriedades de tabela (fora dela, ele pode recusar o arquivo)
ORDEM_TBLPR = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize", "tblStyleColBandSize", "tblW", "jc",
               "tblCellSpacing", "tblInd", "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook"]


def _propriedade_de_tabela(props, nome, **atributos):
    """Coloca o elemento em w:tblPr na posição certa e devolve-o (substitui um igual que já exista)."""
    for velho in props.findall(qn("w:" + nome)):
        props.remove(velho)
    novo = OxmlElement("w:" + nome)
    for chave, valor in atributos.items():
        novo.set(qn("w:" + chave), str(valor))
    seguintes = ORDEM_TBLPR[ORDEM_TBLPR.index(nome) + 1:]
    posterior = next((f for f in props if f.tag in {qn("w:" + n) for n in seguintes}), None)
    if posterior is not None:
        posterior.addprevious(novo)
    else:
        props.append(novo)
    return novo


def _configurar_tabela(tabela, largura, bordas=None, margens=(50, 90, 50, 90)):
    """Largura fixa, bordas (lados -> cor) e margens internas das células (topo, esquerda, base, direita)."""
    props = tabela._tbl.tblPr
    tabela.alignment = WD_TABLE_ALIGNMENT.CENTER
    tabela.autofit = False
    _propriedade_de_tabela(props, "tblW", w=largura, type="dxa")
    quadro = _propriedade_de_tabela(props, "tblBorders")
    for lado in ("top", "left", "bottom", "right", "insideH", "insideV"):
        cor = (bordas or {}).get(lado)
        if cor:
            _filho(quadro, "w:" + lado, val="single", sz=4, space=0, color=cor)
        else:
            _filho(quadro, "w:" + lado, val="nil")
    _propriedade_de_tabela(props, "tblLayout", type="fixed")
    cantos = _propriedade_de_tabela(props, "tblCellMar")
    for lado, valor in zip(("top", "left", "bottom", "right"), margens):
        _filho(cantos, "w:" + lado, w=valor, type="dxa")


def _grade(tabela, larguras):
    """Largura de cada coluna na grade da tabela e em cada célula (o Word usa as duas)."""
    for coluna, largura in zip(tabela.columns, larguras):
        coluna.width = Twips(largura)
    for linha in tabela.rows:
        for celula, largura in zip(linha.cells, larguras):
            celula.width = Twips(largura)


def _linhas_do_timbre(celula, linhas, tamanho):
    """Escreve as linhas do timbre (centralizadas) numa célula do cabeçalho ou do rodapé."""
    primeiro = True
    for linha in linhas:
        p = celula.paragraphs[0] if primeiro else celula.add_paragraph()
        primeiro = False
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(0)
        for texto, estilo in linha:
            estilos = estilo.split()
            _fonte(p.add_run(texto), "Times New Roman" if "serifa" in estilos else "Arial", tamanho, negrito="b" in estilos,
                   cor="FF0000" if "vermelho" in estilos else "0563C1" if "link" in estilos else None, sublinhado="link" in estilos)


def _faixa_do_timbre(parte, logo, largura_logo_cm, linhas, tamanho, largura_util):
    """Cabeçalho/rodapé: logo à esquerda, texto centralizado na página (a terceira coluna só equilibra o espaço)."""
    parte.is_linked_to_previous = False
    lateral = int(largura_logo_cm * 567) + 120
    tabela = parte.add_table(rows=1, cols=3, width=Twips(largura_util))
    _configurar_tabela(tabela, largura_util, margens=(0, 0, 0, 0))
    _grade(tabela, (lateral, largura_util - 2 * lateral, lateral))
    esquerda, centro, direita = tabela.rows[0].cells
    for celula in (esquerda, centro, direita):
        celula.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = esquerda.paragraphs[0]
    p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(0)
    p.add_run().add_picture(str(logo), width=Twips(int(largura_logo_cm * 567)))
    _linhas_do_timbre(centro, linhas, tamanho)
    # o Word exige um parágrafo depois da tabela: o que já existia vira esse fecho, pequeno
    fecho_ = parte.paragraphs[0]
    fecho_._p.addprevious(tabela._tbl)
    fecho_.paragraph_format.space_before = fecho_.paragraph_format.space_after = Pt(0)
    _fonte(fecho_.add_run(""), "Arial", 2)
    fecho_.paragraph_format.line_spacing = Pt(2)


def _base_docx(doc):
    """Documento em branco, A4, já com o timbre e a fonte do documento como padrão."""
    d = DocxDocument()
    secao = d.sections[0]
    secao.page_width, secao.page_height = Mm(210), Mm(297)
    secao.top_margin = secao.bottom_margin = Twips(MARGEM_VERTICAL)
    secao.left_margin = secao.right_margin = Twips(doc.margem_lateral)
    secao.header_distance = secao.footer_distance = Twips(DISTANCIA_TIMBRE)
    normal = d.styles["Normal"]
    normal.font.name, normal.font.size = doc.fonte, Pt(doc.tamanho)
    fontes = normal.element.get_or_add_rPr().get_or_add_rFonts()
    for atributo in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fontes.set(qn(atributo), doc.fonte)
    _faixa_do_timbre(secao.header, LOGO_TOPO, 2.3, CABECALHO, TAMANHO_CABECALHO, doc.largura_util)
    _faixa_do_timbre(secao.footer, LOGO_RODAPE, 2.5, RODAPE, TAMANHO_RODAPE, doc.largura_util)
    return d


def _paragrafo_docx(d, doc, bloco):
    p = d.add_paragraph()
    p.alignment = ALINHAMENTO_DOCX[bloco.alinhamento]
    formato = p.paragraph_format
    formato.space_before, formato.space_after = Pt(bloco.antes), Pt(bloco.depois)
    formato.line_spacing = bloco.entrelinha
    formato.keep_with_next = bloco.unido_ao_proximo
    if bloco.quebra_antes:
        formato.page_break_before = True
    if bloco.recuo:
        formato.left_indent = Twips(bloco.recuo)
    if bloco.suspenso:
        formato.first_line_indent = Twips(-bloco.suspenso)
        formato.tab_stops.add_tab_stop(Twips(bloco.recuo))
    elif bloco.primeira_linha:
        formato.first_line_indent = Twips(bloco.primeira_linha)
    fonte, tamanho = bloco.fonte or doc.fonte, bloco.tamanho or doc.tamanho
    if bloco.numero:
        _fonte(p.add_run(bloco.numero + "\t"), fonte, tamanho)
    for t in bloco.trechos():
        _fonte(p.add_run(t.texto), fonte, tamanho, t.negrito, t.italico, sublinhado=t.sublinhado)
    return p


def _tabela_docx(d, doc, bloco):
    tabela = d.add_table(rows=1, cols=len(bloco.colunas))
    bordas = None if bloco.sem_bordas else {lado: bloco.cor_borda for lado in ("top", "left", "bottom", "right", "insideH", "insideV")}
    _configurar_tabela(tabela, bloco.largura_total(), bordas)
    _grade(tabela, [c.largura for c in bloco.colunas])

    def escrever(valores, primeira, cabecalho=False, negrito=False):
        celulas = tabela.rows[0].cells if primeira else tabela.add_row().cells
        linha = tabela.rows[-1]
        propriedades = linha._tr.get_or_add_trPr()
        _filho(propriedades, "w:cantSplit")                 # a linha não se parte entre duas páginas
        if cabecalho:
            _filho(propriedades, "w:tblHeader")             # o cabeçalho se repete em cada página
            if bloco.altura_cabecalho:
                linha.height, linha.height_rule = Twips(bloco.altura_cabecalho), WD_ROW_HEIGHT_RULE.AT_LEAST
        for coluna, (celula, valor) in enumerate(zip(celulas, valores)):
            celula.width = Twips(bloco.colunas[coluna].largura)
            celula.vertical_alignment = WD_ALIGN_VERTICAL.CENTER if bloco.altura_cabecalho and cabecalho else None
            p = celula.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if cabecalho else ALINHAMENTO_DOCX[bloco.colunas[coluna].alinhamento]
            _fonte(p.add_run(str(valor)), doc.fonte, bloco.tamanho, negrito=cabecalho or negrito)
            if cabecalho and bloco.sombreado:
                _filho(celula._tc.get_or_add_tcPr(), "w:shd", val="clear", color="auto", fill="D9D9D9")

    primeira = True
    if bloco.cabecalho:
        escrever([c.titulo for c in bloco.colunas], True, cabecalho=True)
        primeira = False
    for posicao, valores in enumerate(bloco.linhas):
        escrever(valores, primeira, negrito=posicao in bloco.negrito_linhas)
        primeira = False


def _formulario_docx(d, doc, bloco):
    tabela = d.add_table(rows=len(bloco.linhas), cols=len(bloco.grade))
    _configurar_tabela(tabela, bloco.largura_total(), {lado: "000000" for lado in ("top", "left", "bottom", "right", "insideH", "insideV")},
                       margens=(0, 108, 0, 108))
    _grade(tabela, bloco.grade)                              # antes de mesclar: a célula mesclada soma as larguras
    for r, (linha, altura) in enumerate(zip(bloco.linhas, bloco.alturas)):
        tabela.rows[r].height, tabela.rows[r].height_rule = Twips(altura), WD_ROW_HEIGHT_RULE.AT_LEAST
        _filho(tabela.rows[r]._tr.get_or_add_trPr(), "w:cantSplit")
        coluna = 0
        for celula in linha:
            inicio = tabela.cell(r, coluna)
            alvo = inicio.merge(tabela.cell(r, coluna + celula.span - 1)) if celula.span > 1 else inicio
            p = alvo.paragraphs[0]
            p.paragraph_format.space_after = Pt(3)
            if celula.texto:
                _fonte(p.add_run(celula.texto), doc.fonte, bloco.tamanho, negrito=celula.negrito)
            coluna += celula.span


def _pauta_docx(d, doc, bloco):
    tabela = d.add_table(rows=bloco.linhas, cols=1)
    _configurar_tabela(tabela, doc.largura_util, {"bottom": "000000", "insideH": "000000"}, margens=(0, 0, 0, 0))
    _grade(tabela, [doc.largura_util])
    for linha in tabela.rows:
        linha.height, linha.height_rule = Twips(int(bloco.altura * 20)), WD_ROW_HEIGHT_RULE.EXACTLY
        p = linha.cells[0].paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        _fonte(p.add_run(""), doc.fonte, 6)


def _assinaturas_docx(d, doc, bloco):
    n = len(bloco.rotulos)
    larguras = [doc.largura_util // n] * n
    tabela = d.add_table(rows=2, cols=n)
    _configurar_tabela(tabela, sum(larguras), None, margens=(0, 0, 0, 0))
    _grade(tabela, larguras)
    for coluna, rotulo in enumerate(bloco.rotulos):
        for linha, (texto, tamanho) in enumerate((("_" * bloco.comprimento, doc.tamanho), (rotulo, bloco.tamanho_rotulo))):
            p = tabela.cell(linha, coluna).paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(0)
            _fonte(p.add_run(texto), doc.fonte, tamanho)


def _assinatura_docx(d, doc, bloco):
    texto = lambda conteudo, antes=0, **fonte: _paragrafo_docx(d, doc, Paragrafo([Texto(conteudo, **fonte)], "centro", antes=antes, unido_ao_proximo=True))
    texto("_" * 44, antes=bloco.antes)
    texto(bloco.nome, negrito=True)
    texto(bloco.cargo)
    texto(bloco.papel, italico=True).paragraph_format.keep_with_next = False


def para_docx(doc):
    """Documento -> BytesIO com o arquivo .docx pronto para enviar."""
    d = _base_docx(doc)
    for bloco in doc.blocos:
        if bloco.tipo == "titulo":
            _paragrafo_docx(d, doc, Paragrafo([Texto(bloco.texto, negrito=True)], "centro", antes=bloco.antes,
                                              depois=bloco.depois, tamanho=bloco.tamanho))
        elif bloco.tipo == "paragrafo":
            _paragrafo_docx(d, doc, bloco)
        elif bloco.tipo in ("tabela", "formulario", "pauta", "assinaturas"):
            if bloco.antes:                                  # o espaço antes de uma tabela é um parágrafo vazio
                _paragrafo_docx(d, doc, Paragrafo([""], antes=bloco.antes, tamanho=1))
            {"tabela": _tabela_docx, "formulario": _formulario_docx, "pauta": _pauta_docx,
             "assinaturas": _assinaturas_docx}[bloco.tipo](d, doc, bloco)
        elif bloco.tipo == "assinatura":
            _assinatura_docx(d, doc, bloco)
    propriedades = d.core_properties
    propriedades.title, propriedades.author, propriedades.last_modified_by = doc.titulo, "Sistema de Prontuários", "Sistema de Prontuários"
    propriedades.comments = propriedades.subject = propriedades.keywords = ""
    arquivo = BytesIO()
    d.save(arquivo)
    arquivo.seek(0)
    return arquivo
