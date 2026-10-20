"""
Ficha multiprofissional de saúde, escrita direto no sistema (o modelo do escritório: "Ficha Multiprofissional de Saúde"). Quem escreve é a
enfermagem (a enfermeira, com COREN válido: cadastros.pode_assinar_saude); quem lê é ela, o administrador e quem recebeu a permissão de ler os
relatórios sigilosos. A ficha só abre depois que a pessoa foi internada. Tem três partes:

  1. a ANAMNESE (modelos.FichaSaude): história fisiológica e patológica, investigação sobre os sistemas e sobre a dependência química. Uma por
     internação, com o desenho do acolhimento social: rascunho que se edita à vontade; finalizar guarda data, hora e a assinatura da enfermeira
     (nome, cargo e COREN), e depois ela ainda pode alterar, cada alteração virando uma versão no histórico (versoes.py). As perguntas estão descritas UMA vez, em SECOES (as mesmas classes do
     acolhimento social: servico_social.Campo e Secao); delas saem o formulário, a leitura e a validação do que foi digitado e o documento;
  2. os REGISTROS DE ENFERMAGEM (modelos.RegistroEnfermagem): sinais vitais, glicemia capilar, perdas e evolução de enfermagem, um registro por
     vez, com o horário em que foi medido. Só se acrescenta: o que estava errado se corrige com um registro novo;
  3. a EVOLUÇÃO MULTIPROFISSIONAL (modelos.EvolucaoSaude): anotação de cada profissional da equipe (médica, enfermagem, nutrição, psicologia,
     assistência social), do coordenador operacional e de outros profissionais, cada uma com a categoria e a assinatura de quem escreveu. Só se
     acrescenta, como os registros.

A impressão usa o mesmo desenho da ficha em branco (fichas.ficha_multiprofissional): com respostas onde há e as linhas em branco de sempre onde
ainda não há; a evolução multiprofissional não tem linhas em branco, ela só sai com as anotações escritas.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import servico_social
from servico_social import Campo, Secao

C = Campo
NAO_SEI = "especifique e em tratamento"
SISTEMAS = (("neuro", "Neurológico"), ("resp", "Respiratório"), ("cardio", "Cardiocirculatório"), ("gastro", "Gastrointestinal"),
            ("renal", "Renal"), ("endocrino", "Endócrino"), ("urinario", "Urinário"), ("reprodutor", "Reprodutor"))
SUBSTANCIAS = (("alcool", "Álcool"), ("maconha", "Maconha/Haxixe"), ("cocaina", "Cocaína"), ("crack", "Crack"),
               ("inalantes", "Inalantes/ cola/ solvente/ tíner"), ("anfetaminas", "Anfetaminas / remédios para emagrecer"),
               ("opioides", "Heroína/ Morfina/ metadona"), ("ecstasy", "Ecstasy / MDMA"), ("benzo", "Benzodiazepínico / Diazepam"), ("lsd", "LSD"))
SIM_NAO = ("Sim", "Não")
PERIODOS = ("Nos últimos 6 meses", "No último mês")
TRATAMENTOS = (("trat_reducao", "Redução de danos / abstinência (Alcoólicos Anônimos e Narcóticos Anônimos, inclusive)"),
               ("trat_ct", "Internação em comunidade terapêutica"), ("trat_caps", "CAPS / CAPS-AD"), ("trat_outros", "Outros"))
# o que precisa estar respondido para finalizar (a ficha pode ter outras perguntas em branco, como no papel): as medidas e o que é risco à saúde
OBRIGATORIOS = (("altura", "a altura"), ("peso", "o peso"), ("alergia", "se tem alergia"), ("hiv", "o HIV / AIDS"), ("tuberculose", "a tuberculose"))

SECOES = (
    Secao("Medidas", (
        C("altura", "Altura (m)", "numero", colunas="c2"),
        C("peso", "Peso (kg)", "numero", colunas="c2"),
    )),
    Secao("História fisiológica e patológica do acolhido", (
        C("doencas_referidas", "Alguma vez algum médico ou um profissional de saúde lhe disse que você tinha algumas doenças?", "longo", colunas="c6", linhas=2),
        C("fratura", "Já sofreu alguma fratura?", "sim_nao", colunas="c6"),
        C("cirurgia", "Já realizou alguma cirurgia?", "sim_nao", colunas="c6"),
        C("alergia", "Possui alergia a algum alimento ou medicamento?", "sim_nao", colunas="c6"),
        C("medicamentos", "Lista de medicamentos utilizados com posologia e horário:", "longo", colunas="c6", linhas=3),
        C("exames_previos", "Exames prévios realizados, data e resultados:", "longo", colunas="c6", linhas=3),
        C("tatuagem", "Tem tatuagem, cicatrizes ou piercing? Aponte a data da última realizada.", "longo", colunas="c6", linhas=2),
    )),
    Secao("Investigação sobre diversos sistemas", tuple(
        campo for chave, nome in SISTEMAS for campo in (
            C(f"sis_{chave}_doenca", f"Sistema {nome}: doença relacionada", colunas="c3"),
            C(f"sis_{chave}_medicacao", f"Sistema {nome}: faz uso de medicação?", "sim_nao", colunas="c3", detalhe_rotulo="qual"))
    )),
    Secao("Outras comorbidades e doenças transmissíveis", (
        C("comorbidade_qual", "Outras comorbidades ou doença transmissível: qual?", colunas="c6"),
        C("comorbidade", "Tem outra comorbidade ou doença transmissível?", "sim_nao", colunas="c6", detalhe_rotulo=NAO_SEI),
        C("hiv", "HIV / AIDS", "sim_nao", colunas="c6", detalhe_rotulo=NAO_SEI),
        C("tuberculose", "Tuberculose", "sim_nao", colunas="c6", detalhe_rotulo=NAO_SEI),
        C("inflamatorias", "Doenças inflamatórias", "sim_nao", colunas="c6", detalhe_rotulo=NAO_SEI),
        C("outras_investigacoes", "Outras investigações", "longo", colunas="c6", linhas=2),
        C("deficiencia", "Portador de deficiência física?", "sim_nao", colunas="c6"),
    )),
    Secao("Investigação sobre a dependência química", (
        *(campo for chave, nome in SUBSTANCIAS for campo in (
            C(f"sub_{chave}_diario", f"{nome}: uso diário", "escolha", SIM_NAO, "c2"),
            C(f"sub_{chave}_periodo", f"{nome}: usou", "escolha", PERIODOS, "c4"))),
        C("sub_outros", "Outras substâncias", colunas="c6"),
        C("abstinencia", "Apresenta sintomas de abstinência?", "longo", colunas="c6", linhas=2),
        C("cessar_sozinho", "Tentou cessar o uso por conta própria? Como foi?", "longo", colunas="c6", linhas=2),
        C("inicio_uso", "Com qual idade o paciente começou a usar drogas e/ou álcool? Como se deu a descoberta do uso/vício e o padrão atual?",
          "longo", colunas="c6", linhas=3),
        C("tratamento_anterior", "Possui histórico de tratamento anterior?", "sim_nao", colunas="c6"),
        *(C(chave, rotulo, "sim_nao", colunas="c6", detalhe_rotulo="obs") for chave, rotulo in TRATAMENTOS),
        C("clinicas_desejar", "O que estas clínicas de recuperação ou locais de tratamento deixaram a desejar do ponto de vista do familiar?",
          "longo", colunas="c6", linhas=3),
    )),
)
CAMPOS = [campo for secao in SECOES for campo in secao.campos]
POR_CHAVE = {campo.chave: campo for campo in CAMPOS}
# como cada seção aparece na tela (ícone do base.html e cor do cartão)
VISUAL = {"Medidas": ("prancheta", "azul"), "História fisiológica e patológica do acolhido": ("coracao", "rosa"),
          "Investigação sobre diversos sistemas": ("alerta", "amarelo"), "Outras comorbidades e doenças transmissíveis": ("alerta", "roxo"),
          "Investigação sobre a dependência química": ("documento", "turquesa")}

# faixas aceitas, só para pegar erro de digitação (não é avaliação clínica)
ALTURA = (0.5, 2.5)
PESO = (20.0, 350.0)
LIMITES = {"pulso": (20, 240, "Pulso"), "fr": (4, 80, "Frequência respiratória"), "bcf": (60, 220, "BCF"), "glicemia": (10, 900, "Glicemia capilar")}
TEMPERATURA = (30.0, 43.0)
PA_SISTOLICA, PA_DIASTOLICA = (50, 260), (30, 160)
LIMITE_TEXTO = 3000

# ---- a evolução multiprofissional: chave -> (como aparece, a ficha em que sai impressa)
CATEGORIAS_DE_EVOLUCAO = {
    "medica": ("Médica", "multi"), "enfermagem": ("Enfermagem", "multi"), "nutricao": ("Nutrição", "multi"), "psicologia": ("Psicologia", "multi"),
    "assistencia_social": ("Assistência social", "multi"), "coordenacao": ("Coordenador operacional", "coordenacao"),
    "outros": ("Outros profissionais", "outros"),
}
# a função do funcionário (cadastros.PROFISSOES) -> a categoria em que ele escreve
CATEGORIA_DA_PROFISSAO = {"medico": "medica", "enfermeiro": "enfermagem", "nutricionista": "nutricao", "psicologo": "psicologia",
                          "assistente_social": "assistencia_social", "coordenacao": "coordenacao", "outro": "outros"}


def categoria_do(funcionario_profissao):
    """Em que categoria escreve quem tem esta função (o administrador, sem função, escreve como 'outros')."""
    return CATEGORIA_DA_PROFISSAO.get(funcionario_profissao, "outros")


@dataclass
class Conteudo:
    """O que a ficha de saúde tem de uma internação, para a impressão: a anamnese (valores de cada campo e a ficha gravada, se houver), os registros
    de enfermagem e as evoluções, cada um já na ordem em que saem."""
    v: dict = field(default_factory=dict)
    ficha: object = None
    registros: list = field(default_factory=list)
    evolucoes: list = field(default_factory=list)


def estado(ficha):
    """Em que pé está a anamnese: '' (não iniciada), 'rascunho' ou 'finalizado'."""
    return servico_social.estado(ficha)


def valores(internacao, ficha=None):
    """O que aparece em cada campo da anamnese (o digitado; o resto, em branco)."""
    return servico_social.valores(internacao, ficha, CAMPOS)


def valores_do_formulario(form):
    return servico_social.valores_do_formulario(form, CAMPOS)


def conteudo(internacao):
    ficha = internacao.ficha_saude
    return Conteudo(v=valores(internacao, ficha), ficha=ficha, registros=list(internacao.registros_enfermagem), evolucoes=list(internacao.evolucoes_saude))


def resumo(internacao):
    """O que a ficha do acolhido mostra a quem só precisa saber se a ficha de saúde foi feita: o estado, quando e quantos registros há."""
    ficha = internacao.ficha_saude
    situacao = estado(ficha)
    return {"estado": situacao, "em": (ficha.finalizado_em if situacao == "finalizado" else ficha.atualizado_em) if situacao else None,
            "registros": len(internacao.registros_enfermagem), "evolucoes": len(internacao.evolucoes_saude)}


# ============================================================ o que foi digitado na anamnese
def _decimal(texto):
    try:
        return float(str(texto).strip().replace(",", "."))
    except ValueError:
        return None


def _formatar(numero, casas, enxuto=False):
    """1.8 -> '1,80'; com `enxuto`, sem os zeros que sobram (72.0 -> '72', 72.5 -> '72,5')."""
    texto = f"{numero:.{casas}f}".replace(".", ",")
    return texto.rstrip("0").rstrip(",") if enxuto and "," in texto else texto


def altura_em_metros(texto):
    """'1,75', '1.75' ou '175' (centímetros) -> 1.75; None se não for uma altura."""
    valor = _decimal(texto)
    if valor is not None and 50 <= valor <= 250:                  # digitou em centímetros
        valor /= 100
    return valor if valor is not None and ALTURA[0] <= valor <= ALTURA[1] else None


def ler_formulario(form):
    """Formulário -> (dados, erros), como servico_social.ler_formulario; a altura e o peso são conferidos e guardados do jeito que se lê
    ('1,75' e '72,5')."""
    dados, erros = servico_social.ler_formulario(form, CAMPOS)
    if "altura" in dados:
        metros = altura_em_metros(dados["altura"])
        if metros is None:
            erros["altura"] = "Informe a altura em metros, entre 0,50 e 2,50 (ex.: 1,75)."
            dados.pop("altura")
        else:
            dados["altura"] = _formatar(metros, 2)
    if "peso" in dados:
        quilos = _decimal(dados["peso"])
        if quilos is None or not PESO[0] <= quilos <= PESO[1]:
            erros["peso"] = "Informe o peso em quilos, entre 20 e 350 (ex.: 72,5)."
            dados.pop("peso")
        else:
            dados["peso"] = _formatar(quilos, 1, enxuto=True)
    return dados, erros


def validar_finalizacao(dados):
    """O mínimo para finalizar: a altura, o peso e as respostas sobre alergia, HIV/AIDS e tuberculose. Devolve {campo: mensagem}."""
    erros = {}
    for chave, o_que in OBRIGATORIOS:
        if not dados.get(chave):
            erros[chave] = f"Informe {o_que} para finalizar." if POR_CHAVE[chave].tipo == "numero" else f"Responda sim ou não para finalizar ({o_que})."
    return erros


# ============================================================ registro de enfermagem
def _inteiro(texto):
    try:
        return int(str(texto).strip())
    except ValueError:
        return None


def ler_registro(form, agora=None):
    """Formulário do registro de enfermagem -> (colunas de modelos.RegistroEnfermagem, erros). Nada é obrigatório sozinho, mas o registro
    precisa ter ao menos um dado (um sinal vital, a glicemia, o peso, uma perda ou a evolução). O horário não pode ser no futuro."""
    agora = agora or datetime.now()
    dados, erros = {}, {}
    bruto = (form.get("quando") or "").strip()
    try:
        quando = datetime.fromisoformat(bruto) if bruto else agora.replace(second=0, microsecond=0)
    except ValueError:
        quando = None
        erros["quando"] = "Data e hora inválidas."
    if quando is not None and quando > agora + timedelta(minutes=5):
        erros["quando"] = "O horário não pode ser no futuro."
    dados["quando"] = quando
    pa = (form.get("pa") or "").strip().lower().replace(" ", "")
    if pa:
        partes = pa.replace("x", "/").split("/")
        sistolica, diastolica = (_inteiro(partes[0]), _inteiro(partes[1])) if len(partes) == 2 else (None, None)
        if sistolica is None or diastolica is None or not PA_SISTOLICA[0] <= sistolica <= PA_SISTOLICA[1] \
                or not PA_DIASTOLICA[0] <= diastolica <= PA_DIASTOLICA[1] or sistolica <= diastolica:
            erros["pa"] = "Pressão arterial no formato 120/80."
        else:
            dados["pa"] = f"{sistolica}/{diastolica}"
    for chave, (minimo, maximo, rotulo) in LIMITES.items():
        texto = (form.get(chave) or "").strip()
        if texto:
            valor = _inteiro(texto)
            if valor is None or not minimo <= valor <= maximo:
                erros[chave] = f"{rotulo}: um número inteiro entre {minimo} e {maximo}."
            else:
                dados[chave] = valor
    for chave, faixa, rotulo, casas in (("temperatura", TEMPERATURA, "Temperatura", 1), ("peso", PESO, "Peso", 1)):
        texto = (form.get(chave) or "").strip()
        if texto:
            valor = _decimal(texto)
            if valor is None or not faixa[0] <= valor <= faixa[1]:
                erros[chave] = f"{rotulo}: entre {_formatar(faixa[0], 0)} e {_formatar(faixa[1], 0)}, com vírgula se precisar (ex.: 36,5)."
            else:
                dados[chave] = round(valor, casas)
    for chave, limite in (("volume_urinario", 60), ("evacuacao", 60), ("evolucao", LIMITE_TEXTO)):
        texto = (form.get(chave) or "").strip()
        if len(texto) > limite:
            erros[chave] = f"Escreva até {limite} caracteres (tem {len(texto)})."
        elif texto:
            dados[chave] = texto
    if not erros and not any(dados.get(c) not in (None, "") for c in
                             ("pa", "pulso", "temperatura", "fr", "bcf", "glicemia", "peso", "volume_urinario", "evacuacao", "evolucao")):
        erros["_"] = "Preencha ao menos um dado do registro."
    return dados, erros


def ler_evolucao(texto, categoria, permitidas):
    """Texto e categoria da evolução -> (texto limpo, erro ou None). `permitidas`: as categorias em que quem escreve pode escrever."""
    texto = (texto or "").strip()
    if categoria not in permitidas:
        return "", "Escolha a categoria da anotação."
    if not texto:
        return "", "Escreva a anotação."
    if len(texto) > LIMITE_TEXTO:
        return "", f"A anotação pode ter até {LIMITE_TEXTO} caracteres (tem {len(texto)})."
    return texto, None
