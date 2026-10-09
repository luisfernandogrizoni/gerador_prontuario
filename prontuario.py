"""
Geração do prontuário (Word e página do navegador) a partir dos dados do formulário.

Tudo o que é regra do documento mora aqui: formatação de datas, CPF e R$,
cálculo de idade e previsão de término, classificação do convênio e o texto
de cada página do prontuário. O texto é escrito em blocos (documentos.py),
que viram o arquivo .docx e a página para ver/imprimir no navegador — com o
mesmo timbre dos demais documentos e sem arquivo de modelo guardado em pasta.

Este módulo não sabe nada de Flask nem de banco: recebe um dicionário
no formato do formulário e devolve o documento. Por isso dá para usar
tanto ao enviar o formulário quanto ao baixar de novo pela lista.
"""

from datetime import date

from documentos import Assinaturas, Celula, Coluna, Documento, Formulario, N, Paragrafo, Pauta, S, Tabela, para_docx
from validacao import fmt_cpf, fmt_rg

MESES_DURACAO = 9  # período de tratamento citado na Declaração de Punho

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

# Linhas da tabela "Relação de Documentos" (chave do formulário -> rótulo)
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
# Como o convênio aparece nas telas (o valor guardado no banco e o Word continuam "CAPS AD")
NOME_NA_TELA = {"CAPS AD": "Caps AD"}
# Cor de cada categoria nas telas (classe CSS): Social vai do azul acinzentado mais escuro (contribui menos)
# ao mais claro (contribui mais); Particular é azul bebê.
TIPO_DA_CATEGORIA = {"Caps AD": "caps", "Prefeitura Tarumã": "taruma", "Social": "social",
                     "Social I": "social-1", "Social II": "social-2", "Particular": "particular"}


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
         Caps AD, Prefeitura Tarumã, Social, Social I, Social II ou Particular
    (quem paga valor é "Particular" só na faixa mais alta; as faixas menores são Social).
    Sem convênio definido: "A definir". O documento Word segue com o texto completo
    de classificar() ("Particular — Social Parcial II")."""
    if convenio in CONVENIOS_GRATUITOS:
        return NOME_NA_TELA.get(convenio, convenio)
    if convenio not in CONVENIOS:
        return CONVENIO_A_DEFINIR
    categoria = categoria_particular(valor)
    return NOME_CURTO.get(categoria, categoria)


def tipo_da_categoria(categoria):
    """Classe de cor da categoria (caps, taruma, social, social-1, social-2, particular) ou "outro"."""
    return TIPO_DA_CATEGORIA.get(categoria, "outro")


def categoria_vaga(convenio, valor):
    """Categoria em que a pessoa ocupa vaga (a mesma categoria efetiva). Sem convênio
    definido não ocupa vaga de nenhuma categoria -> None."""
    return categoria_efetiva(convenio, valor) if convenio in CONVENIOS else None


def marca(escolhido, opcao):
    """( X ) na opção escolhida, (   ) nas outras."""
    return " X " if escolhido == opcao else "   "


# ------------------------------------------------------- formulário -> variáveis do documento
def montar_contexto(f):
    """Transforma os dados do formulário nas variáveis que o documento usa."""
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
    }


# ------------------------------------------------------- o documento
# As páginas do prontuário, na ordem: capa, ficha de controle, contrato terapêutico, termo de contribuição e
# relação de documentos, termos de compromisso e declaração de próprio punho. Cada uma começa em página nova.
LINHA = 14              # espaço de uma linha em branco de 12 pt, em pontos
LINHA_E_MEIA = 21       # idem, com entrelinha 1,5

# ficha de controle: a grade fina de 16 colunas e a altura mínima de cada linha, em twips (como no modelo antigo)
GRADE_FICHA = [1359, 361, 290, 537, 769, 1123, 735, 164, 850, 322, 109, 1004, 119, 325, 750, 1153]
ALTURAS_FICHA = [376, 376, 376, 89, 285, 376, 376, 393, 614, 376, 376, 376, 376, 376, 376]


def _ficha_de_controle(c):
    r = lambda texto, span=1: Celula(texto, span, negrito=True)      # rótulo
    v = lambda texto, span=1: Celula(texto, span)                    # valor
    estado_civil = "        ".join(f"({marca(c['estado_civil'], opcao)}) {opcao}"
                                   for opcao in ("Casado", "Solteiro", "Divorciado", "Outros")) + f" {c['estado_civil_outro']}"
    return Formulario(GRADE_FICHA, [
        [r("Nome", 2), v(c["nome"], 14)],
        [r("Endereço", 2), v(c["endereco"], 12), r("Num"), v(c["numero"])],
        [r("Bairro", 2), v(c["bairro"], 5), r("Cidade", 3), v(c["cidade"], 6)],
        [r("Contato ", 2), v(c["contato1"], 3), r("Contato"), v(c["contato2"], 5), r("Contato ", 2), v(c["contato3"], 3)],
        [r("Data de Nascimento", 4), v(c["nascimento_fmt"], 8), r("Idade", 3), v(c["idade"])],
        [r("RG"), v(c["rg"], 6), r("CPF", 2), v(c["cpf"], 7)],
        [r("Cartão SUS", 3), v(c["cartao_sus"], 13)],
        [r("Estado Civil", 2), v(estado_civil, 14)],
        [r("Cônjuge", 2), v(c["conjuge"], 14)],
        [r("Escolaridade", 2), v(c["escolaridade"], 6), r("Religião", 3), v(c["religiao"], 5)],
        [r("Profissão", 2), v(c["profissao"], 14)],
        [r("Mãe", 2), v(c["mae"], 14)],
        [r("Responsável", 2), v(c["resp_nome"], 14)],
        [r("Parentesco", 2), v(c["parentesco"], 14)],
        [r("RG"), v(c["resp_rg"], 6), r("CPF", 2), v(c["resp_cpf"], 7)],
    ], ALTURAS_FICHA)


def _item(numero, partes, recuo, tamanho=None, antes=0, depois=0):
    """Item de lista numerada: número pendurado à esquerda e texto justificado."""
    return Paragrafo(partes if isinstance(partes, list) else [partes], "justificado", antes=antes, depois=depois,
                     recuo=recuo, suspenso=360, numero=f"{numero}.", tamanho=tamanho)


def _blocos_do_prontuario(c):
    """O prontuário inteiro, como lista de blocos (documentos.py). `c` é o contexto de montar_contexto()."""
    centro, justificado = "centro", "justificado"
    data = f"Assis, {c['data_extenso']}."
    linha_55 = "_" * 55
    resp_e_nome = (f"Eu, {c['resp_nome']}, CPF: {c['resp_cpf']}, RG: {c['resp_rg']}, responsável pela internação de {c['nome']}, "
                   f"CPF: {c['cpf']}, RG: {c['rg']}.")

    capa = [Paragrafo([N("Prontuário")], centro, antes=205, tamanho=28, fonte="Times New Roman"),
            Paragrafo([c["nome"]], centro, tamanho=24, fonte="Calibri")]

    ficha = [Paragrafo([S("FICHA DE CONTROLE")], centro, entrelinha=1.5, quebra_antes=True, antes=LINHA),
             Paragrafo([S("1º CONTATO")], centro, entrelinha=1.5),
             _ficha_de_controle(c),
             Paragrafo([S(f"Início: {c['inicio_fmt']}")], entrelinha=1.5, recuo=227, antes=LINHA_E_MEIA),
             Paragrafo([S(f"Término: {c['termino_fmt']}")], entrelinha=1.5, recuo=227),
             Paragrafo([S("Motivo: " + " ".join(f"({marca(c['motivo'], m)}) {m}" for m in ("Conclusão", "Desistência", "Desligamento")))],
                       entrelinha=1.5, recuo=227)]

    contrato = [
        Paragrafo([S("CONTRATO TERAPÊUTICO ")], centro, tamanho=11, entrelinha=1.5, quebra_antes=True),
        Paragrafo([f"Eu, {c['resp_nome']}, CPF {c['resp_cpf']}, RG: {c['resp_rg']}, Responsável pela internação de {c['nome']}, CPF: {c['cpf']}, "
                   f"RG: {c['rg']}, Venho de comum acordo com a Coordenação e a Direção Administrativa desta Comunidade Terapêutica "
                   "estabelecer o seguinte CONTRATO TERAPÊUTICO."], justificado, tamanho=11, depois=3),
        _item(1, "A Casa de Recuperação se responsabiliza em oferecer ao paciente um tratamento humanitário respeitando sua individualidade "
                 "segundo orientação e normas das Organizações competentes, preceitos éticos, assistência médica emergencial e "
                 "interdisciplinar para o mesmo...", 780, 11, antes=LINHA),
        _item(2, "Tal tratamento só será possível com a participação efetiva dos familiares que serão solicitados a comparecer às reuniões do "
                 "Amor Exigente, Pastoral da Sobriedade e atividades complementares.", 780, 11),
        _item(3, ["Interno deverá cumprir rigorosamente as normas e regulamentos da comunidade terapêutica, em relação a ",
                  N("disciplina, espiritualidade e laborterapia, para que o tratamento de fato ocorra"), ". Evitando assim, o seu desligamento."], 780, 11),
        _item(4, "Todo e qualquer objeto destinado ao paciente deverá ser entregue a supervisão que o encaminhará ao paciente;", 780, 11),
        _item(5, "Os familiares ou responsáveis deverão se responsabilizar pelo paciente após o tratamento.", 780, 11),
        _item(6, "O pagamento da primeira parcela deverá ser realizado no ato da internação.", 780, 11),
        _item(7, "Em caso de desistência ou exclusão antes do término do primeiro mês, o valor pago no ato da internação, não será devolvido. "
                 f"O tratamento será mantido até {c['tratamento_ate_fmt']}.", 780, 11),
        Paragrafo([N("Compete ao Responsável e familiares:")], justificado, tamanho=11, recuo=420, antes=LINHA),
        _item(1, [N("Prover o paciente de roupas e objetos de uso pessoal e medicamentos (quando a internação não for por convênio) "
                    "quando necessário;")], 720, 11, antes=LINHA),
        _item(2, [N("Manifestar à Coordenação as dúvidas que tenha com relação ao tratamento;")], 720, 11),
        _item(3, [N("Comparecer à Casa de Recuperação quando solicitado e quando do retorno de saída do paciente;")], 720, 11),
        _item(4, [N("Participar de Grupos de ajuda GAD, AMOR EXIGENTE, NA, AA, CEREA, PASTORAL DA SOBRIEDADE, ou outros...")], 720, 11),
        _item(5, [N("Responsabilizar-se por danos ao patrimônio provocado pelo interno.")], 720, 11),
        Paragrafo(["Nossa entidade é filantrópica e todo trabalho realizado pelo paciente é ", N("labor terapêutico"), ", portanto ", N("não"),
                   " terá nenhum direito trabalhista sobre o mesmo;"], justificado, tamanho=11, primeira_linha=360, antes=LINHA),
        Paragrafo(["A entidade pela sua própria condição, ", N("não"), " se responsabilizará por qualquer ato voluntário do paciente caso venha "
                   "acidentar-se gerando lesão física de qualquer natureza, permanente ou temporária;"],
                  justificado, tamanho=11, primeira_linha=360),
        Paragrafo([data], centro, tamanho=11, antes=LINHA),
        Paragrafo(["De Acordo: "], justificado, tamanho=11, primeira_linha=360, antes=LINHA + 7, unido_ao_proximo=True),
        Paragrafo([linha_55], centro, tamanho=11, unido_ao_proximo=True),
        Paragrafo(["Paciente"], centro, tamanho=11, unido_ao_proximo=True),
        Paragrafo([linha_55], centro, tamanho=11, antes=LINHA + 7, unido_ao_proximo=True),
        Paragrafo(["Responsável"], centro, tamanho=11),
    ]

    documentos_entregues = [[rotulo, c["docs"][chave]] for chave, rotulo in DOCUMENTOS.items()]
    documentos_entregues.append([f"Outro: {c['doc_outro']}", c["docs"]["outro"]])
    termo = [
        Paragrafo([S("TERMO DE CONTRIBUIÇÃO VOLUNTÁRIA")], centro, tamanho=11, quebra_antes=True),
        Paragrafo([f"Nome do Candidato: {c['nome']}"], justificado, antes=LINHA, depois=3),
        Paragrafo([f"Nome do Responsável: {c['resp_nome']}"], entrelinha=1.5),
        Paragrafo([f"Contribuição Voluntária:  {c['contribuicao']}"], entrelinha=1.5, antes=LINHA_E_MEIA),
        Paragrafo(["Convênio: ", N(c["convenio_txt"])], entrelinha=1.5),
        Paragrafo(["Solicitamos que o valor da parcela de entrada seja providenciado para o ", N("Dia da Internação, "),
                   "para que possamos dar andamento ao processo."], justificado, antes=LINHA_E_MEIA),
        Paragrafo(["Obs: Em caso de desistência ou desligamento, a contribuição ", N("não"),
                   " será devolvida, constituindo doação para a instituição."], justificado, antes=LINHA),
        Paragrafo([S("RELAÇÃO DE DOCUMENTOS")], centro, tamanho=11, antes=2 * LINHA),
        Paragrafo([f"Eu, {c['resp_nome']}, declaro que entreguei os documentos relacionados abaixo, para ficar no prontuário da Casa de "
                   "Acolhida durante o período de internação "], justificado),
        Tabela(colunas=[Coluna("Documento ", 3892), Coluna("Apresentou", 1550)], linhas=documentos_entregues, tamanho=12,
               sombreado=False, cor_borda="000000", altura_cabecalho=492, antes=LINHA + 7),
        Paragrafo([data], centro, antes=LINHA + 7),
        Assinaturas(["Associação Restauração", "Responsável"], comprimento=32, tamanho_rotulo=10, antes=LINHA_E_MEIA),
    ]

    compromisso = [
        Paragrafo([S("TERMOS DE COMPROMISSO")], centro, tamanho=11, quebra_antes=True),
        Paragrafo([resp_e_nome], justificado, antes=LINHA_E_MEIA + 2 * LINHA, depois=3),
        _item(1, [N("Comprometo-me"), " a comparecer na CASA DE ACOLHIDA RESTAURAÇÃO/SEDE DO ESCRITÓRIO, para buscar o residente supracitado, "
                  "no prazo de vinte e quatro horas após seu pedido de desistência ou seu desligamento. Caso contrário estou ciente e de acordo "
                  "que o mesmo será liberado da instituição. Portando o valor da passagem (residentes de fora) e documentação entregue na "
                  "internação."], 720, antes=LINHA, depois=3),
        _item(2, [N("Declaro"), " ter recebido uma cópia do “Manual de Orientação para Famílias e Residentes”, referente ao compromisso de "
                  "direitos e deveres, de internos e família, durante o período de internação do candidato, estando ciente que para a "
                  "realização do tratamento adequado é necessário que realize o tripé do tratamento Disciplina, Espiritualidade e "
                  "Laborterapia."], 720, antes=2 * LINHA),
        Paragrafo(["De Acordo: "], justificado, primeira_linha=360, antes=4 * LINHA, unido_ao_proximo=True),
        Paragrafo(["Assinatura: " + "_" * 60], centro, antes=LINHA, unido_ao_proximo=True),
        Paragrafo(["Responsável"], centro, unido_ao_proximo=True),
        Paragrafo(["Assinatura: " + "_" * 60], centro, antes=2 * LINHA, unido_ao_proximo=True),
        Paragrafo(["Paciente"], centro, unido_ao_proximo=True),
        Paragrafo(["Assinatura: " + "_" * 60], centro, antes=2 * LINHA, unido_ao_proximo=True),
        Paragrafo(["Assistente Social"], centro, unido_ao_proximo=True),
        Paragrafo([data], centro, antes=LINHA_E_MEIA + 2 * LINHA),
    ]

    punho = [
        Paragrafo([N("Declaração Punho")], centro, tamanho=18, quebra_antes=True, antes=LINHA),
        Paragrafo([N("O residente deverá copiar e assinar")], centro),
        Paragrafo([f"Eu, {c['nome']}, declaro que é de minha livre e espontânea vontade aderir ao Programa Terapêutico oferecido pela Casa de "
                   "Acolhida Restauração, declaro também que estou ciente do período de tratamento que é de 9 (nove) meses baseado no tripé "
                   "Disciplina, Espiritualidade e Laborterapia e me comprometo a cumpri-los."], justificado, antes=3 * LINHA),
        Pauta(linhas=16, altura=19, antes=2 * LINHA),
        Paragrafo(["Residente: " + "_" * 32 + " "], centro, antes=2 * LINHA, unido_ao_proximo=True),
        Paragrafo([data], centro, antes=LINHA),
    ]
    return capa + ficha + contrato + termo + compromisso + punho


def montar_documento(dados):
    """dados (formato do formulário) -> Documento (documentos.py), que vira Word ou página do navegador."""
    contexto = montar_contexto(dados)
    nome = f"Prontuário - {contexto['nome'] or 'sem nome'}"
    return Documento(nome_arquivo=nome, titulo=nome, blocos=_blocos_do_prontuario(contexto), fonte="Arial", tamanho=12,
                     margem_lateral=720)


def gerar_docx(dados):
    """dados (formato do formulário) -> (BytesIO com o .docx, nome do arquivo)."""
    documento = montar_documento(dados)
    return para_docx(documento), documento.nome_arquivo + ".docx"
