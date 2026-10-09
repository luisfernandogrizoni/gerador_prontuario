"""
Geração do prontuário (.docx) a partir dos dados do formulário.

Tudo o que é regra do documento mora aqui: formatação de datas, CPF e R$,
cálculo de idade e previsão de término, classificação do convênio e o
preenchimento do modelo com docxtpl (Jinja2 dentro do Word).

Este módulo não sabe nada de Flask nem de banco: recebe um dicionário
no formato do formulário e devolve o arquivo. Por isso dá para usar
tanto ao enviar o formulário quanto ao baixar de novo pela lista.
"""

from datetime import date
from io import BytesIO
from pathlib import Path

from docxtpl import DocxTemplate

from validacao import fmt_cpf, fmt_rg

BASE = Path(__file__).parent
MODELO = BASE / "modelo" / "prontuario_modelo.docx"
MESES_DURACAO = 9  # período de tratamento citado na Declaração de Punho

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

# Linhas da tabela "Relação de Documentos" (chave usada no modelo -> rótulo)
DOCUMENTOS = {
    "rg": "RG Original/Cópia",
    "cnh": "CNH Original",
    "cin": "CIN Original/Cópia",
    "sus": "Cartão SUS",
    "ctps": "Carteira de Trabalho",
}

# Convênios em que a contribuição voluntária é sempre R$ 0,00
CONVENIOS_GRATUITOS = ["CAPS AD", "Prefeitura Tarumã"]
CONVENIOS = CONVENIOS_GRATUITOS + ["Particular"]
# Só triagens (em admissão / lista de espera) podem ficar sem convênio definido
CONVENIO_A_DEFINIR = "A definir"

# Categoria do particular pelo valor: a primeira faixa em que valor > limite.
# Ordem do maior para o menor limite — por isso a primeira que bate é a certa.
FAIXAS_PARTICULAR = [
    (1500.00, "Particular"),
    (700.00, "Social Parcial II"),
    (400.00, "Social Parcial I"),
    (0.00, "Social Total"),
]
CATEGORIA_VALOR_ZERO = "Social"  # particular com valor = 0,00
# Nome curto das categorias nas telas (o Word usa o nome completo): Social Total e valor 0,00 são "Social"
NOME_CURTO = {"Social Total": "Social", CATEGORIA_VALOR_ZERO: "Social",
              "Social Parcial I": "Social I", "Social Parcial II": "Social II"}


# ---------------------------------------------------------------- utilidades
def ler_data(texto):
    """'2026-10-05' (formato do <input type=date>) -> date, ou None."""
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def fmt_data(d):
    return d.strftime("%d/%m/%Y") if d else ""


def data_por_extenso(d):
    return f"{d.day:02d} de {MESES[d.month - 1]} de {d.year}"


def somar_meses(d, meses):
    """Soma meses a uma data; se o dia não existir no mês final, usa o último dia."""
    ano = d.year + (d.month - 1 + meses) // 12
    mes = (d.month - 1 + meses) % 12 + 1
    for dia in (d.day, 30, 29, 28):
        try:
            return date(ano, mes, dia)
        except ValueError:
            continue


def calcular_idade(nascimento, referencia):
    """Idade em anos completos na data de referência, ou None sem nascimento."""
    if not nascimento:
        return None
    anos = referencia.year - nascimento.year
    if (referencia.month, referencia.day) < (nascimento.month, nascimento.day):
        anos -= 1
    return anos


def previsao_termino(inicio, tratamento_ate):
    """Data informada no formulário ou, se vazia, início + 9 meses."""
    if tratamento_ate:
        return tratamento_ate
    return somar_meses(inicio, MESES_DURACAO) if inicio else None


def ler_valor(texto):
    """'1200.5' (formato do <input type=number>) -> 1200.5; vazio/inválido -> 0.0."""
    try:
        return float(texto) if texto else 0.0
    except ValueError:
        return 0.0


def fmt_reais(valor):
    """1200.5 -> 'R$ 1.200,50'."""
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def classificar(convenio, valor):
    """
    Regra da contribuição:
      - CAPS AD / Prefeitura Tarumã -> valor 0,00 (categoria = o próprio convênio)
      - Particular -> categoria pela faixa de valor (FAIXAS_PARTICULAR);
                      valor = 0,00 -> CATEGORIA_VALOR_ZERO
      - qualquer outro (ex.: registro importado sem convênio) -> "A definir"
    Devolve (valor_final, texto_da_linha_convenio).
    """
    if convenio in CONVENIOS_GRATUITOS:
        return 0.0, convenio
    if convenio not in CONVENIOS:
        return valor, CONVENIO_A_DEFINIR
    categoria = categoria_particular(valor)
    if categoria == convenio:  # evita "Particular — Particular"
        return valor, convenio
    return valor, f"{convenio} — {categoria}"


def categoria_particular(valor):
    """Categoria do particular pela faixa de valor (valor 0,00 -> CATEGORIA_VALOR_ZERO)."""
    for limite, nome in FAIXAS_PARTICULAR:
        if valor > limite:
            return nome
    return CATEGORIA_VALOR_ZERO


def categoria_efetiva(convenio, valor):
    """A categoria que a pessoa realmente é para a casa, como aparece nas telas:
         CAPS AD, Prefeitura Tarumã, Social, Social I, Social II ou Particular
    (quem paga valor é "Particular" só na faixa mais alta; as faixas menores são Social).
    Sem convênio definido: "A definir". O documento Word segue com o texto completo
    de classificar() ("Particular — Social Parcial II")."""
    if convenio in CONVENIOS_GRATUITOS:
        return convenio
    if convenio not in CONVENIOS:
        return CONVENIO_A_DEFINIR
    categoria = categoria_particular(valor)
    return NOME_CURTO.get(categoria, categoria)


def categoria_vaga(convenio, valor):
    """Categoria em que a pessoa ocupa vaga (a mesma categoria efetiva). Sem convênio
    definido não ocupa vaga de nenhuma categoria -> None."""
    return categoria_efetiva(convenio, valor) if convenio in CONVENIOS else None


def marca(escolhido, opcao):
    """Usada no modelo: ( X ) na opção escolhida, (   ) nas outras."""
    return " X " if escolhido == opcao else "   "


# ------------------------------------------------------- formulário -> modelo
def montar_contexto(f):
    """Transforma os dados do formulário nas variáveis que o modelo usa."""
    hoje = date.today()
    inicio = ler_data(f.get("inicio"))
    termino = ler_data(f.get("termino"))
    nascimento = ler_data(f.get("nascimento"))
    data_doc = ler_data(f.get("data_documento")) or hoje

    tratamento_ate = previsao_termino(inicio, ler_data(f.get("tratamento_ate")))

    valor, convenio_txt = classificar(f.get("convenio", ""),
                                      ler_valor(f.get("contribuicao_valor", "").strip()))
    contribuicao = fmt_reais(valor)
    condicoes = f.get("contribuicao_condicoes", "").strip()
    if condicoes and valor > 0:
        contribuicao = f"{contribuicao} — {condicoes}"

    docs = {chave: f.get(f"doc_{chave}", "") for chave in DOCUMENTOS}
    doc_outro = f.get("doc_outro", "").strip()
    docs["outro"] = "Sim" if doc_outro else ""

    idade = calcular_idade(nascimento, inicio or hoje)

    texto = lambda campo: f.get(campo, "").strip()

    return {
        # acolhido
        "nome": texto("nome"),
        "endereco": texto("endereco"),
        "numero": texto("numero"),
        "bairro": texto("bairro"),
        "cidade": "/".join(p for p in (texto("cidade"), texto("estado")) if p),
        "contato1": texto("contato1"),
        "contato2": texto("contato2"),
        "contato3": texto("contato3"),
        "nascimento_fmt": fmt_data(nascimento),
        "idade": f"{idade} anos" if idade is not None else "",
        "rg": fmt_rg(texto("rg")),
        "cpf": fmt_cpf(texto("cpf")),
        "cartao_sus": texto("cartao_sus"),
        "estado_civil": texto("estado_civil"),
        "estado_civil_outro": f": {texto('estado_civil_outro')}"
                              if texto("estado_civil") == "Outros" and texto("estado_civil_outro") else "",
        "conjuge": texto("conjuge"),
        "escolaridade": texto("escolaridade"),
        "religiao": texto("religiao"),
        "profissao": texto("profissao"),
        "mae": texto("mae"),
        # responsável
        "resp_nome": texto("resp_nome"),
        "parentesco": texto("parentesco"),
        "resp_rg": fmt_rg(texto("resp_rg")),
        "resp_cpf": fmt_cpf(texto("resp_cpf")),
        # internação
        "inicio_fmt": fmt_data(inicio),
        "termino_fmt": fmt_data(termino),
        "motivo": texto("motivo"),
        "tratamento_ate_fmt": fmt_data(tratamento_ate),
        "data_extenso": data_por_extenso(data_doc),
        # contribuição e documentos
        "contribuicao": contribuicao,
        "convenio_txt": convenio_txt,
        "docs": docs,
        "doc_outro": doc_outro,
        # função usada dentro do modelo
        "marca": marca,
    }


def gerar_docx(dados):
    """dados (formato do formulário) -> (BytesIO com o .docx, nome do arquivo)."""
    contexto = montar_contexto(dados)
    modelo = DocxTemplate(MODELO)
    modelo.render(contexto, autoescape=True)  # autoescape: "&", "<" etc. não quebram o .docx
    arquivo = BytesIO()
    modelo.save(arquivo)
    arquivo.seek(0)
    return arquivo, f"Prontuário - {contexto['nome'] or 'sem nome'}.docx"
