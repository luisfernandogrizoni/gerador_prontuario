"""
Documentos em branco que acompanham a triagem e a internação, escritos com o motor de documentos (documentos.py):

  * Pedido de exames        entregue à família quando a internação é marcada;
  * Enxoval                 a lista do que o acolhido leva, também entregue quando a internação é marcada;
  * Capa do envelope        a capa (em paisagem, sem timbre) do envelope do prontuário em papel;
  * Ficha multiprofissional ficha de saúde (anamnese) e folhas de evolução, preenchidas à mão pela equipe.

O texto vem dos modelos usados no escritório, com os erros de digitação corrigidos. Cada função devolve uma lista de
blocos que começa com um `Pagina(...)`, para poder ser colocada depois de qualquer outro documento (impressos.py).
O que o sistema já sabe do acolhido (nome, início, convênio, cidade) sai preenchido; o resto fica em branco.
"""

from documentos import Celula, Coluna, Colunas, Formulario, Imagem, N, Pagina, Paragrafo, Pauta, Tabela, Texto, Titulo

SIM_NAO = "(    ) sim    (    ) não"
ALTURA_DA_LINHA = 19            # pontos entre uma linha de escrever e a próxima


def _nome(nome):
    """Linha pequena com o nome do acolhido, no alto de cada folha (uma folha solta não se perde de quem é)."""
    return Paragrafo([N("Acolhido(a): "), nome or "_" * 40], "direita", tamanho=9, depois=4)


# ======================================================================== pedido de exames
def pedido_de_exames(nome):
    exames = ["HIV;", "Sífilis;", "Hepatite B e C;", "Anti HBs e HBsAG;", "AntiHCV;", "VDRL;", "Hemograma Completo e Plaquetas."]
    return [Pagina(),
            Titulo("Pedido de exames", tamanho=14, antes=14, depois=16),
            Paragrafo([N("Acolhido(a): "), nome or "_" * 40], antes=0, depois=14),
            Paragrafo(["Encaminho a fazer os seguintes exames médicos para seu ingresso na Casa de Acolhida Restauração."],
                      "justificado", entrelinha=1.5),
            Paragrafo([N("TESTE RÁPIDO PARA:")], antes=22, depois=8),
            *[Paragrafo([N(exame)], recuo=720, suspenso=360, numero="•", entrelinha=1.5) for exame in exames]]


# ======================================================================== enxoval
ENXOVAL = [
    "02 lençóis de solteiro", "02 fronhas", "01 travesseiro", "02 cobertores", "02 toalhas de banho",
    "02 toalhas de rosto (opcional)", "03 calças jeans", "02 calças para trabalho", "05 camisetas para uso diário",
    "03 camisetas para trabalho", "01 jaqueta de frio", "01 blusa de frio", "02 bermudas", "02 shorts para futebol",
    "05 cuecas", "05 pares de meias", "01 par de botinas", "01 par de chinelos", "01 par de sapatos fechado",
    "01 par de tênis", "01 boné ou chapéu",
]
HIGIENE = [
    "06 aparelhos de barbear descartáveis", "01 creme de barbear", "01 escova de dente", "05 cremes dentais", "10 sabonetes",
    "02 desodorantes roll-on, aerosol ou pomada", "01 pente ou escova para cabelo", "02 shampoos", "01 condicionador",
    "01 creme hidratante", "01 cortador de unha", "01 bucha para banho", "01 repelente creme grande",
]
LIMPEZA = [
    "02 buchas para lavar roupa", "02 caixas de sabão em pó", "05 pedras de sabão", "01 litro de amaciante", "02 panos de chão",
    "01 vassoura", "01 rodo", "01 balde pequeno", "02 pacotes de prendedor de roupa",
]
ESTUDO = ["01 terço", "01 caderno", "02 canetas (azul/vermelha)", "02 lápis", "01 borracha", "01 Bíblia Ave Maria"]
ENTREGAR_NO_ESCRITORIO = ["Documentos pessoais (RG, CPF e Cartão SUS)", "Medicação com receita (caso esteja medicado)"]


def enxoval(nome=""):
    item = lambda texto: Paragrafo([texto], tamanho=11)
    secao = lambda titulo: Paragrafo([Texto(titulo, negrito=True, sublinhado=True)], tamanho=11, antes=12, depois=4, unido_ao_proximo=True)
    esquerda = [item(t) for t in ENXOVAL] + [secao("MATERIAL DE HIGIENE PESSOAL")] + [item(t) for t in HIGIENE]
    direita = ([secao("MATERIAL DE LIMPEZA")] + [item(t) for t in LIMPEZA]
               + [secao("MATERIAL DE ESTUDO")] + [item(t) for t in ESTUDO])
    direita[0].antes = 0
    return [Pagina(),
            Titulo("ENXOVAL", tamanho=14, antes=8, depois=10),
            Colunas([esquerda, direita], espaco=720),
            Tabela(colunas=[Coluna("ENTREGAR NO ESCRITÓRIO NO PRÉ DA INTERNAÇÃO", 6200)],
                   linhas=[[t] for t in ENTREGAR_NO_ESCRITORIO], tamanho=11, sombreado=False, cor_borda="000000", antes=16)]


# ======================================================================== capa do envelope
def capa_do_envelope(nome, inicio_fmt, convenio_sus, cidade):
    """Capa em paisagem, sem timbre, só com a logo. `convenio_sus`: True (Sim), False (Não) ou None (em branco).
    O motivo e o término ficam em branco: são marcados na baixa, à mão."""
    grande = lambda partes, **kw: Paragrafo(partes, **{"tamanho": 26, "fonte": "Arial", **kw})
    tamanho_do_nome = 26 if len(nome) <= 30 else 22 if len(nome) <= 38 else 18
    x = lambda marcado: "X" if marcado else " "
    return [Pagina(paisagem=True, timbre=False),
            Imagem("timbre/logo-topo.jpg", 28),
            grande([Texto(f"Nome: {nome}", negrito=True, sublinhado=True)], alinhamento="centro", tamanho=tamanho_do_nome, antes=6, depois=18),
            grande([N(f"Motivo: ( {x(False)} ) Conclusão     ( {x(False)} ) Desistência     ( {x(False)} ) Exclusão")], alinhamento="centro", antes=26, depois=36),
            grande([N(f"Início: {inicio_fmt}          Término:")], depois=12),
            grande([N(f"Convênio SUS: ( {x(convenio_sus is True)} ) Sim     ( {x(convenio_sus is False)} ) Não")], depois=12),
            grande([N(f"CIDADE: {cidade}")], fonte="Calibri")]


# ======================================================================== ficha multiprofissional de saúde
SISTEMAS = ["Neurológico", "Respiratório", "Cardiocirculatório", "Gastrointestinal", "Renal", "Endócrino", "Urinário", "Reprodutor"]
SUBSTANCIAS = ["Álcool", "Maconha/Haxixe", "Cocaína", "Crack", "Inalantes/ cola/ solvente/ tíner",
               "Anfetaminas / remédios para emagrecer", "Heroína/ Morfina/ metadona", "Ecstasy / MDMA",
               "Benzodiazepínico / Diazepam", "LSD"]
PROFISSOES = "(   ) MÉDICA     (   ) ENFERMAGEM     (   ) NUTRIÇÃO     (   ) PSICOLOGIA     (   ) ASSISTÊNCIA SOCIAL"
LINHAS_NA_FOLHA = 28            # linhas de escrever que cabem numa página inteira, com o timbre e a linha do nome


def _pergunta(texto, linhas=1, sim_nao=None):
    """Pergunta + (sim/não, se `sim_nao` for um texto) + linhas para responder à mão."""
    blocos = [Paragrafo([texto], antes=9, unido_ao_proximo=True)]
    if sim_nao:
        blocos.append(Paragrafo([sim_nao], unido_ao_proximo=True))
    blocos.append(Pauta(linhas=linhas, altura=ALTURA_DA_LINHA, antes=2))
    return blocos


def _secao(titulo):
    return Paragrafo([Texto(titulo, negrito=True, italico=True)], "centro", antes=16, depois=2, unido_ao_proximo=True)


def _anamnese(nome):
    sim_nao_especifique = f"{SIM_NAO}.  Se sim, especifique:"
    pagina1 = [Pagina(), _nome(nome),
               Paragrafo([N("FICHA MULTIPROFISSIONAL DE SAÚDE")], "centro", tamanho=13, antes=2),
               Paragrafo([Texto("HISTÓRIA FISIOLÓGICA E PATOLÓGICA DO ACOLHIDO", negrito=True, italico=True)], "centro", antes=2, depois=8),
               Paragrafo(["Altura (m): " + "_" * 18], depois=6),
               Paragrafo(["Peso (kg): " + "_" * 19]),
               *_pergunta("Alguma vez algum médico ou um profissional de saúde lhe disse que você tinha algumas doenças?", 2),
               *_pergunta("Já sofreu alguma fratura?", 1, sim_nao_especifique),
               *_pergunta("Já realizou alguma cirurgia?", 1, sim_nao_especifique),
               *_pergunta("Possui alergia a algum alimento ou medicamento?", 1, sim_nao_especifique),
               *_pergunta("Lista de medicamentos utilizados com posologia e horário:", 3),
               *_pergunta("Exames prévios realizados, data e resultados:", 3),
               *_pergunta("Tem tatuagem, cicatrizes ou piercing? Aponte a data da última realizada.", 2)]
    sistemas = [_secao("INVESTIGAÇÃO SOBRE DIVERSOS SISTEMAS")]
    for sistema in SISTEMAS:
        sistemas += [Paragrafo([N(f"Sistema {sistema}")], antes=7, unido_ao_proximo=True),
                     Paragrafo(["Doença relacionada: " + "_" * 56], antes=3, unido_ao_proximo=True),
                     Paragrafo(["(    ) sim    (    ) não.  Se sim, faz uso de medicação: " + "_" * 30], antes=3)]
    comorbidades = [Paragrafo([N("Outras comorbidades ou doença transmissível")], antes=10, unido_ao_proximo=True),
                    Paragrafo(["Qual: " + "_" * 86], antes=3, unido_ao_proximo=True),
                    Paragrafo([f"{SIM_NAO}.  Se sim, especifique e em tratamento:"], antes=3, unido_ao_proximo=True),
                    Pauta(linhas=1, altura=ALTURA_DA_LINHA, antes=2)]
    for doenca in ("HIV / AIDS", "Tuberculose"):
        comorbidades += [Paragrafo([N(f"{doenca}:")], antes=7, unido_ao_proximo=True),
                         Paragrafo([f"{SIM_NAO}.  Se sim, especifique e em tratamento:"], antes=2, unido_ao_proximo=True),
                         Pauta(linhas=1, altura=ALTURA_DA_LINHA, antes=2)]
    comorbidades += [Paragrafo([N("Doenças inflamatórias: "), f"{SIM_NAO}.  Se sim, especifique e em tratamento:"], antes=9, unido_ao_proximo=True),
                     Pauta(linhas=1, altura=ALTURA_DA_LINHA, antes=2),
                     Paragrafo([N("Outras investigações:")], antes=9, unido_ao_proximo=True),
                     *_pergunta("Portador de deficiência física?", 1, sim_nao_especifique)]
    dependencia = [_secao("INVESTIGAÇÃO SOBRE A DEPENDÊNCIA QUÍMICA"),
                   Paragrafo(["Quais substâncias de uso psicoativo:"], antes=6, depois=2, unido_ao_proximo=True)]
    for substancia in SUBSTANCIAS:
        dependencia += [Paragrafo([f"(   ) {substancia}  -  uso diário:  (   ) sim   (   ) não"], antes=4, unido_ao_proximo=True),
                        Paragrafo(["      (   ) nos últimos 6 meses     (   ) no último mês"], unido_ao_proximo=True)]
    dependencia += [Paragrafo(["(   ) Outros: " + "_" * 72], antes=4),
                    *_pergunta("Apresenta sintomas de abstinência?", 2),
                    *_pergunta("Tentou cessar o uso por conta própria? Como foi?", 2),
                    *_pergunta("Com qual idade o paciente começou a usar drogas e/ou álcool? Como se deu a descoberta do uso/vício e o padrão atual?", 3),
                    Paragrafo(["Possui histórico de tratamento anterior?"], antes=9, unido_ao_proximo=True),
                    Paragrafo([f"{SIM_NAO}.  Se sim, especifique:"], unido_ao_proximo=True)]
    for tipo in ("Redução de danos / abstinência (Alcoólicos Anônimos e Narcóticos Anônimos, inclusive)",
                 "Internação em comunidade terapêutica", "CAPS / CAPS-AD"):
        dependencia += [Paragrafo([f"(   ) {tipo}"], antes=6, unido_ao_proximo=True), Paragrafo(["Obs: " + "_" * 82], antes=3)]
    dependencia += [Paragrafo(["(   ) Outros / obs: " + "_" * 66], antes=6),
                    *_pergunta("O que estas clínicas de recuperação ou locais de tratamento deixaram a desejar do ponto de vista do familiar?", 3),
                    Paragrafo(["_" * 42], "centro", antes=26, unido_ao_proximo=True),
                    Paragrafo(["Responsável pela Anamnese"], "centro", unido_ao_proximo=True),
                    Paragrafo(["Carimbo e Assinatura"], "centro")]
    return pagina1 + sistemas + comorbidades + dependencia


def _evolucao(nome, titulo="EVOLUÇÃO MULTIPROFISSIONAL", profissoes=True, data_carimbo="(Data/Carimbo/Assinatura)"):
    """Uma folha de evolução: frente (título e linhas) e verso (só linhas)."""
    cabecalho = [Paragrafo([N(titulo)], "centro", tamanho=14, antes=2, depois=2)]
    if profissoes:
        cabecalho.append(Paragrafo([PROFISSOES], "centro", tamanho=10))
    cabecalho.append(Paragrafo([data_carimbo], "centro", tamanho=9, depois=4))
    linhas_na_frente = LINHAS_NA_FOLHA - (3 if profissoes else 2)
    return [Pagina(), _nome(nome), *cabecalho, Pauta(linhas=linhas_na_frente, altura=ALTURA_DA_LINHA),
            Pagina(), _nome(nome), Pauta(linhas=LINHAS_NA_FOLHA, altura=ALTURA_DA_LINHA, antes=6)]


def _enfermagem(nome, idade):
    """Sistematização da assistência de enfermagem: folha em paisagem (a única da ficha). Ela precisa de toda a altura da
    folha, então não leva o timbre inteiro: só um cabeçalho pequeno, como no modelo."""
    larguras = [950, 600, 600, 700, 600, 600, 1500, 950, 1300, 1500, 850, 1350, 1450, 1500]        # 14 colunas
    grupos = Formulario(grade=larguras, linhas=[[Celula("SINAIS VITAIS", 7, True), Celula("GLICEMIA CAPILAR", 3, True), Celula("PERDAS", 4, True)]],
                        alturas=[300], tamanho=9)
    titulos = ["HORÁRIO", "PA", "P", "TEMP", "FR", "BCF", "NOME LEGÍVEL", "HORÁRIO", "GLICEMIA CAPILAR", "NOME LEGÍVEL", "PESO",
               "VOLUME URINÁRIO (freq)", "EVACUAÇÃO (freq. e quant.)", "NOME LEGÍVEL"]
    linha = [":", "", "", "", "", "", "", ":", "", "", "", "", "", ""]
    return [Pagina(paisagem=True, timbre=False),
            Imagem("timbre/logo-topo.jpg", 15, "centro"),
            Paragrafo([N("Casa de Acolhida Restauração")], "centro", tamanho=14),
            Paragrafo([Texto("Por uma só vida já valeu a pena!", negrito=True)], "centro", tamanho=10),
            Paragrafo(["Rodovia Raposo Tavares, km 435 – Assis – SP"], "centro", tamanho=9, depois=6),
            Paragrafo([N("SISTEMATIZAÇÃO DA ASSISTÊNCIA DE ENFERMAGEM")], "centro", tamanho=12, depois=4),
            Formulario(grade=[9000, 5450], linhas=[[Celula(f"Nome: {nome}", 1), Celula("data:", 1)],
                                                   [Celula(f"Idade: {idade}", 2)]], alturas=[280, 280], tamanho=9),
            grupos,
            Tabela(colunas=[Coluna(t, l, "centro") for t, l in zip(titulos, larguras)], linhas=[linha] * 6, tamanho=8, altura_cabecalho=420,
                   sombreado=False, cor_borda="000000"),
            Tabela(colunas=[Coluna("EVOLUÇÃO DE ENFERMAGEM", 7225), Coluna("EVOLUÇÃO DE ENFERMAGEM", 7225)], linhas=[["", ""]] * 8, tamanho=9,
                   sombreado=False, cor_borda="000000"),
            Paragrafo(["Obrigatório Data/Carimbo/Assinatura"], "centro", tamanho=9, antes=3)]


def ficha_multiprofissional(nome, idade=""):
    """A ficha inteira: anamnese, folhas de evolução, a folha de enfermagem e as anotações da coordenação e de outros profissionais."""
    return (_anamnese(nome)
            + _evolucao(nome)
            + _enfermagem(nome, idade)
            + _evolucao(nome) + _evolucao(nome) + _evolucao(nome)
            + _evolucao(nome, "ANOTAÇÃO COORDENADOR OPERACIONAL", profissoes=False, data_carimbo="(Data/Carimbo e Assinatura)")
            + _evolucao(nome, "ANOTAÇÃO OUTROS PROFISSIONAIS", profissoes=False, data_carimbo="(Data/Carimbo e Assinatura)"))
