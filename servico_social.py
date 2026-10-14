"""
Acolhimento social: o que a assistente social registra na triagem, direto no sistema em vez de à mão. Reúne, num registro
só por triagem/internação (modelos.RelatorioSocial):

  1. a FICHA, o modelo do escritório ("Ficha de acolhimento e classificação de risco e vulnerabilidade do residente")
     mais as perguntas de voluntariedade, documentos e benefícios, situação jurídica e rede de apoio;
  2. o RELATÓRIO SOCIAL, um campo livre: a descrição da situação e a análise dela;
  3. a CLASSIFICAÇÃO de risco e vulnerabilidade (baixo, médio ou alto em cada domínio e a geral);
  4. o PARECER: favorável, favorável com ressalvas ou não condizente com o tratamento da casa. Finalizar um parecer
     'não condizente' marca a triagem como "Rejeitado na triagem" (e pede o motivo).

O modelo está descrito UMA vez, em SECOES (seções e perguntas). Dele saem:
  * o formulário da tela (templates/servico_social_form.html);
  * o documento para imprimir ou baixar em Word (blocos de documentos.py), com as respostas no lugar das linhas em
    branco — e as linhas em branco de sempre onde ainda não há resposta; e a folha-resumo (blocos_resumo), só com a
    classificação e a conclusão, que é o que sai no prontuário de quem não é do Serviço Social;
  * a leitura e a validação do que foi digitado (ler_formulario, validar_finalizacao).

As respostas ficam numa linha por internação (coluna `dados` em JSON, só o que foi preenchido). O que o sistema já sabe
não é digitado de novo: nome, mãe, idade, profissão, escolaridade, telefones e o responsável vêm do cadastro, e o que diz
respeito às passagens anteriores pela casa vem delas (PADROES). Numa readmissão, as respostas que não mudam de uma
vez para a outra (campo.reaproveitar) vêm do acolhimento anterior, para conferir e atualizar. Quem vê e escreve é
controlado em cadastros.pode_servico_social (é sigiloso).
"""

from dataclasses import dataclass, replace
from datetime import date

from documentos import N, Paragrafo, Pauta
from prontuario import calcular_idade, fmt_data, ler_data, previsao_termino
from validacao import fmt_cep, fmt_cpf, fmt_rg

LIMITE_TEXTO, LIMITE_LONGO = 200, 5000
EM_BRANCO = "_" * 24
DATA_EM_BRANCO = "____/____/________"

NIVEIS = ("Baixo", "Médio", "Alto")
PARECERES = ("Favorável à admissão", "Favorável, com ressalvas", "Não condizente com o tratamento da casa")
NAO_CONDIZENTE = PARECERES[2]
# Os motivos vêm do que o Manual de Orientação exige de quem entra e do que a RDC 29/2011 veda (art. 16: admitir quem
# precisa de serviço de saúde que a casa não oferece); "Outro" cobre o resto.
MOTIVOS_DA_REJEICAO = ("Sem desejo firme de tratamento", "Comprometimento psíquico grave",
                       "Precisa de acompanhamento médico-hospitalar complexo", "Fora do perfil da casa (sexo ou idade)", "Outro")
DOMINIOS = (("risco_vida", "Risco à vida (suicídio e violência)"), ("risco_saude", "Saúde"),
            ("risco_vinculos", "Vínculos familiares e rede de apoio"), ("risco_moradia_renda", "Moradia e renda"),
            ("risco_juridico", "Situação jurídica"))
RISCO_GERAL = "risco_geral"


@dataclass(frozen=True)
class Campo:
    chave: str
    rotulo: str
    tipo: str = "texto"        # texto | data | longo | escolha | sim_nao
    opcoes: tuple = ()         # escolha: as alternativas
    colunas: str = "c3"        # largura no formulário (c1..c6, a grade de 6 colunas)
    linhas: int = 3            # longo: linhas em branco na impressão e altura do campo
    linha: str = ""            # campos seguidos com o mesmo `linha` saem juntos na mesma linha do papel
    padrao: str = ""           # de onde vem o valor inicial no cadastro (nome de uma função de PADROES)
    so_se: tuple = ()          # (campo, valor): só vale (e só aparece) quando aquele campo tem aquele valor
    reaproveitar: bool = False  # numa readmissão, a resposta do acolhimento anterior vem como ponto de partida
    antigo: str = ""           # chave com que esta resposta foi gravada antes (modelo anterior da ficha)


@dataclass(frozen=True)
class Secao:
    titulo: str
    campos: tuple
    subtitulo: str = ""
    nova_pagina: bool = False


C = Campo
SECOES = (
    Secao("Identificação individual", (
        C("data_acolhimento", "Data do acolhimento", "data", colunas="c2", padrao="data_da_triagem"),
        C("sexo", "Sexo", "escolha", ("Masculino", "Feminino"), "c2", linha="a", reaproveitar=True),
        C("genero", "Gênero", colunas="c2", linha="a", reaproveitar=True),
        C("opcao_sexual", "Opção sexual", colunas="c2", linha="a", reaproveitar=True),
        C("raca_cor", "Qual raça / cor você se considera?", "escolha",
          ("Negra/Preta", "Indígena", "Branca", "Amarela/Oriental", "Parda/Mestiça", "Não respondeu"), "c6", reaproveitar=True),
        C("moradia", "Qual a situação atual de moradia", colunas="c6"),
        C("encaminhado_por", "Encaminhado por", colunas="c3"),
        C("chegada", "Chegada", "escolha", ("Resgate", "Abordagem", "Família", "Voluntário"), "c3"),
        # as quatro seguintes já vêm preenchidas com o que o sistema sabe das passagens anteriores pela casa (editáveis:
        # internações em outros lugares a assistente social acrescenta)
        C("numero_internacoes", "Número de internações", colunas="c2", linha="b", padrao="n_anteriores"),
        C("ultima_internacao", "Última internação", "data", colunas="c2", linha="b", padrao="ultima_internacao"),
        C("desligamento_data", "Data do desligamento", "data", colunas="c2", linha="c", padrao="desligamento_data"),
        C("desligamento_local", "Local", colunas="c4", linha="c"),
        C("desligamento_motivo", "Motivo", "longo", colunas="c6", linhas=5, padrao="desligamento_motivo"),
    )),
    Secao("Responsável pelo acompanhamento do residente", subtitulo="Sócio econômico — identificação social", nova_pagina=True, campos=(
        C("resp_endereco", "Endereço", colunas="c4", padrao="endereco"),
        C("resp_numero", "Número", colunas="c1", linha="e", padrao="numero"),
        C("resp_bairro", "Bairro", colunas="c3", linha="e", padrao="bairro"),
        C("resp_cep", "CEP", colunas="c2", padrao="cep"),
        C("resp_cidade", "Cidade", colunas="c3", linha="f", padrao="cidade"),
        C("resp_uf", "UF", colunas="c1", linha="f", padrao="estado"),
        C("resp_contato", "Contato", colunas="c2", linha="f"),
        C("resp_email", "E-mail", colunas="c3"),
        C("resp_profissao", "Profissão", colunas="c3"),
        C("moram_na_residencia", "Quantas pessoas moram na residência?", colunas="c3"),
        C("mantenedor", "Quem é o principal mantenedor da família?", colunas="c3"),
        C("contribui_renda", "Quem mais contribui com a renda?", colunas="c3"),
        C("renda_familiar", "Qual a renda familiar total?", colunas="c3"),
        C("colaboracao", "A família colabora voluntariamente com o acolhido de que maneira?", "longo", colunas="c6", linhas=3),
        C("dia_do_acolhido", "Descreva o dia do acolhido", "longo", colunas="c6", linhas=4),
        C("alimentacao", "Como é a sua alimentação?", "longo", colunas="c6", linhas=2),
        C("exercicio", "Realiza exercício físico?", "longo", colunas="c6", linhas=2),
        C("restricao_exercicio", "Possui alguma restrição médica que o impeça de praticar exercícios físicos?", "sim_nao", colunas="c6"),
    )),
    Secao("Histórico comportamental", (
        C("esporte", "Já praticou ou pratica algum tipo de esporte (lutas, artes marciais, futebol etc.)?", "longo", colunas="c6", linhas=2),
        C("suicidio", "Já tentou suicídio? Explique onde e como ocorreu. Utilizou o suicídio como ameaça aos familiares?", "longo", colunas="c6", linhas=3),
        C("rebeliao", "Já passou por rebelião ou situações conflituosas em clínica de recuperação, comunidade ou em outros locais de tratamento?",
          "longo", colunas="c6", linhas=3),
    )),
    Secao("Histórico profissional / ocupacional", (
        C("empresas", "Quais empresas o residente já trabalhou? Cite as três últimas, se houver.", "longo", colunas="c6", linhas=3),
        C("empresa_atual", "Qual a empresa em que o residente está trabalhando atualmente e qual o cargo ocupado? "
                           "O residente necessitará de atestados e laudos no início do tratamento?", "longo", colunas="c6", linhas=3),
        C("demissoes", "Quantas vezes o residente já foi demitido por motivos relacionados à dependência química e alcoólica? "
                       "Cite os três últimos casos, se houver, com breves relatos.", "longo", colunas="c6", linhas=3),
    )),
    Secao("Investigação de espiritualidade", (
        C("crencas", "Quais as crenças do residente?", "longo", colunas="c6", linhas=3, reaproveitar=True),
        C("crencas_familiares", "Qual a crença dos familiares?", "longo", colunas="c6", linhas=3, reaproveitar=True),
        C("tratamento_com_crenca", "O residente já fez algum tipo de tratamento que teve envolvimento com suas crenças? Se sim, qual?",
          "longo", colunas="c6", linhas=3),
    )),
    Secao("Histórico familiar", (
        C("familiares", "Comente sobre os familiares de primeiro e segundo grau do residente.", "longo", colunas="c6", linhas=3, reaproveitar=True),
        C("filho_adotivo", "O residente é filho adotivo?", "longo", colunas="c6", linhas=2, reaproveitar=True),
        C("irmaos", "O residente tem irmãos? Quantos? Qual a idade? Comente um pouco sobre a relação com eles.", "longo", colunas="c6", linhas=3,
          reaproveitar=True),
        C("pensou_em_internar", "Quando o familiar começou a pensar em internar o residente? A partir de qual atitude?", "longo", colunas="c6", linhas=3),
        C("grupos_de_apoio", "O familiar já frequentou grupos de apoio? Por quanto tempo? Qual?", "longo", colunas="c6", linhas=3),
        C("convivio", "Como é o convívio familiar em geral? Já houve agressões verbais e físicas?", "longo", colunas="c6", linhas=3),
        C("dependencia_na_familia", "Existe histórico de dependência química na família?", "longo", colunas="c6", linhas=3, reaproveitar=True),
    )),
    Secao("Investigação sobre perdas", (
        C("maior_perda", "Qual foi a maior perda sentimental que o residente teve?", "longo", colunas="c6", linhas=3),
        C("razoes_do_uso", "Quais são as principais razões para o residente fazer uso de drogas e/ou álcool?", "longo", colunas="c6", linhas=3),
    )),
    # --- o que o modelo do escritório não perguntava e uma triagem precisa registrar
    Secao("Voluntariedade e motivação", (
        C("desejo_de_tratamento", "O acolhido quer o tratamento?", "escolha",
          ("Sim, por decisão própria", "Aceita, por insistência da família", "Não quer", "Está em dúvida"), "c6"),
        C("motivacao", "O que ele espera do tratamento? Registre com as palavras dele.", "longo", colunas="c6", linhas=3),
        C("orientado_das_regras", "O acolhido e o responsável foram orientados sobre as regras da casa (Manual de Orientação) e estão de acordo?",
          "sim_nao", colunas="c6"),
    )),
    Secao("Documentos e benefícios", (
        C("beneficios", "Recebe algum benefício? (Bolsa Família, BPC/LOAS, aposentadoria, auxílio, outro)", "longo", colunas="c6", linhas=2),
        C("cadunico", "Está inscrito no CadÚnico?", "sim_nao", colunas="c6"),
        C("documentos_a_regularizar", "Quais documentos faltam ou precisam ser regularizados?", "longo", colunas="c6", linhas=2),
    )),
    Secao("Situação jurídica", (
        C("pendencias_justica", "Tem processo, medida judicial ou pendência com a justiça?", "sim_nao", colunas="c6"),
    )),
    Secao("Rede de apoio e serviços", (
        C("pessoas_de_apoio", "Quem apoia o acolhido? (família, amigos, igreja, grupo)", "longo", colunas="c6", linhas=3),
        C("servicos_de_referencia", "Que serviços já o acompanham? (CAPS, CRAS, UBS, outros) Onde?", "longo", colunas="c6", linhas=3),
    )),
    # --- a conclusão da assistente social
    Secao("Relatório social", (
        C("relatorio", "Descrição da situação e análise da assistente social", "longo", colunas="c6", linhas=14, antigo="observacoes"),
    )),
    Secao("Classificação de risco e vulnerabilidade", (
        *(C(chave, rotulo, "escolha", NIVEIS, "c6") for chave, rotulo in DOMINIOS),
        C(RISCO_GERAL, "Classificação geral", "escolha", NIVEIS, "c6"),
    )),
    Secao("Parecer social", (
        C("parecer", "Parecer", "escolha", PARECERES, "c6"),
        C("motivo_rejeicao", "Motivo principal da rejeição", "escolha", MOTIVOS_DA_REJEICAO, "c6", so_se=("parecer", NAO_CONDIZENTE)),
        C("parecer_texto", "Conclusão e justificativa do parecer", "longo", colunas="c6", linhas=8),
    )),
)
CAMPOS = [campo for secao in SECOES for campo in secao.campos]
POR_CHAVE = {campo.chave: campo for campo in CAMPOS}
# como cada seção aparece na tela (ícone do base.html e cor do cartão); no papel ela não tem nada disso
VISUAL = {"Identificação individual": ("usuario", "azul"), "Responsável pelo acompanhamento do residente": ("usuarios", "roxo"),
          "Histórico comportamental": ("relogio", "amarelo"), "Histórico profissional / ocupacional": ("prancheta", "turquesa"),
          "Investigação de espiritualidade": ("coracao", "rosa"), "Histórico familiar": ("casa", "verde"),
          "Investigação sobre perdas": ("alerta", "neutro"), "Voluntariedade e motivação": ("ok", "verde"),
          "Documentos e benefícios": ("documento", "azul"), "Situação jurídica": ("bandeira", "amarelo"),
          "Rede de apoio e serviços": ("usuarios", "turquesa"), "Relatório social": ("documento", "rosa"),
          "Classificação de risco e vulnerabilidade": ("alerta", "amarelo"), "Parecer social": ("ok", "rosa")}


def secoes_para(internacao):
    """As seções para esta internação: quem já foi internado não tem como ser 'não condizente' (isso é da triagem)."""
    if internacao.e_triagem:
        return SECOES
    sem_rejeicao = lambda c: replace(c, opcoes=tuple(o for o in c.opcoes if o != NAO_CONDIZENTE)) if c.chave == "parecer" else c
    return tuple(replace(s, campos=tuple(sem_rejeicao(c) for c in s.campos)) for s in SECOES)


def campos_para(internacao):
    return [campo for secao in secoes_para(internacao) for campo in secao.campos]


# ============================================================ o que o cadastro já sabe
def _data_da_triagem(i):
    return i.data_triagem.isoformat() if i.data_triagem else ""


def _passagens_anteriores(i):
    """As outras internações desta pessoa que chegaram a acontecer, a mais recente primeiro."""
    return sorted((o for o in i.pessoa.internacoes if o.id != i.id and o.inicio), key=lambda o: (o.inicio, o.id), reverse=True)


def _da_ultima(i, campo):
    anteriores = _passagens_anteriores(i)
    valor = getattr(anteriores[0], campo) if anteriores else None
    return valor.isoformat() if isinstance(valor, date) else (valor or "")


PADROES = {
    "data_da_triagem": _data_da_triagem,
    "hoje": lambda i: date.today().isoformat(),
    "endereco": lambda i: i.pessoa.endereco, "numero": lambda i: i.pessoa.numero, "bairro": lambda i: i.pessoa.bairro,
    "cep": lambda i: fmt_cep(i.pessoa.cep), "cidade": lambda i: i.pessoa.cidade, "estado": lambda i: i.pessoa.estado,
    # o histórico de internações nesta casa (quem esteve fora daqui a assistente social acrescenta)
    "n_anteriores": lambda i: str(len(_passagens_anteriores(i))) if _passagens_anteriores(i) else "",
    "ultima_internacao": lambda i: _da_ultima(i, "inicio"),
    "desligamento_data": lambda i: _da_ultima(i, "termino"),
    "desligamento_motivo": lambda i: _da_ultima(i, "motivo"),
}


def anterior(internacao):
    """O acolhimento anterior mais recente desta pessoa que tem alguma resposta (None se não há): de onde vêm as respostas
    que não mudam numa readmissão."""
    for outro in sorted((o for o in internacao.pessoa.internacoes if o.id != internacao.id), key=lambda o: o.id, reverse=True):
        if preenchido(outro.relatorio_social):
            return outro.relatorio_social
    return None


def identificacao(internacao, hoje=None):
    """Os dados do cadastro que o relatório mostra sem pedir de novo: ([(rótulo, valor)] do acolhido, idem do responsável)."""
    p, hoje = internacao.pessoa, hoje or date.today()
    idade = calcular_idade(p.nascimento, hoje)
    previsao = previsao_termino(internacao.inicio, internacao.tratamento_ate) if internacao.inicio else None
    acolhido = [("Nome", p.nome), ("Nome da mãe", p.mae), ("Idade", f"{idade} anos" if idade is not None else ""),
                ("Profissão", p.profissao), ("Escolaridade", p.escolaridade), ("Telefone", p.contato3),
                ("Previsão de saída", fmt_data(previsao))]
    responsavel = [("Nome", internacao.resp_nome), ("Grau de parentesco", internacao.parentesco),
                   ("CPF", fmt_cpf(internacao.resp_cpf) if internacao.resp_cpf else ""),
                   ("RG", fmt_rg(internacao.resp_rg) if internacao.resp_rg else ""),
                   ("Telefone", " · ".join(t for t in (p.contato1, p.contato2) if t))]
    return acolhido, responsavel


def valores(internacao, relatorio=None, campos=None):
    """O que aparece em cada campo: o digitado; onde ainda não há nada, o que o sistema já sabe (campo.padrao) e, numa
    readmissão (ainda sem acolhimento próprio), as respostas que não mudam do acolhimento anterior (campo.reaproveitar)."""
    salvo = (relatorio.dados if relatorio is not None else None) or {}
    anterior_ = anterior(internacao) if relatorio is None and any(c.reaproveitar for c in campos or CAMPOS) else None
    antes = (anterior_.dados if anterior_ is not None else None) or {}
    resultado = {}
    for campo in campos or CAMPOS:
        if campo.tipo == "sim_nao":
            resultado[campo.chave] = salvo.get(campo.chave, "")
            resultado[campo.chave + "_detalhe"] = salvo.get(campo.chave + "_detalhe", "")
        elif campo.chave in salvo:
            resultado[campo.chave] = salvo[campo.chave]
        elif campo.antigo and campo.antigo in salvo:
            resultado[campo.chave] = salvo[campo.antigo]
        elif campo.reaproveitar and campo.chave in antes:
            resultado[campo.chave] = antes[campo.chave]
        else:
            resultado[campo.chave] = PADROES[campo.padrao](internacao) if campo.padrao else ""
    return resultado


def valores_do_formulario(form, campos=None):
    """O que está na tela quando o formulário volta com erro: o que foi digitado, do jeito que foi digitado."""
    resultado = {}
    for campo in campos or CAMPOS:
        resultado[campo.chave] = (form.get(campo.chave) or "").strip()
        if campo.tipo == "sim_nao":
            resultado[campo.chave + "_detalhe"] = (form.get(campo.chave + "_detalhe") or "").strip()
    return resultado


def preenchido(relatorio):
    """Já tem alguma resposta digitada?"""
    return relatorio is not None and any(str(v).strip() for v in (relatorio.dados or {}).values())


def estado(relatorio):
    """Em que pé está o acolhimento social: '' (não iniciado), 'rascunho' ou 'finalizado'."""
    if not preenchido(relatorio):
        return ""
    return "finalizado" if relatorio.situacao == "finalizado" else "rascunho"


def resposta(relatorio, chave):
    return ((relatorio.dados if relatorio is not None else None) or {}).get(chave, "")


def classificacao(relatorio):
    """A classificação geral de risco e vulnerabilidade ('Baixo', 'Médio', 'Alto' ou '')."""
    return resposta(relatorio, RISCO_GERAL)


# ============================================================ o que foi digitado
def ler_formulario(form, campos=None):
    """Formulário -> (dados, erros). `dados` guarda só o que foi preenchido; valores fora do esperado viram erro."""
    dados, erros = {}, {}
    campos = campos or CAMPOS
    for campo in campos:
        bruto = (form.get(campo.chave) or "").strip()
        if campo.tipo == "data":
            if bruto and ler_data(bruto) is None:
                erros[campo.chave] = "Data inválida."
            elif bruto:
                dados[campo.chave] = bruto
        elif campo.tipo == "escolha":
            if bruto and bruto not in campo.opcoes:
                erros[campo.chave] = "Escolha uma das opções."
            elif bruto:
                dados[campo.chave] = bruto
        elif campo.tipo == "sim_nao":
            if bruto and bruto not in ("sim", "nao"):
                erros[campo.chave] = "Escolha sim ou não."
            elif bruto:
                dados[campo.chave] = bruto
            detalhe = (form.get(campo.chave + "_detalhe") or "").strip()[:LIMITE_TEXTO]
            if detalhe:
                dados[campo.chave + "_detalhe"] = detalhe
        elif bruto:
            limite = LIMITE_LONGO if campo.tipo == "longo" else LIMITE_TEXTO
            if len(bruto) > limite:
                erros[campo.chave] = f"Escreva até {limite} caracteres (tem {len(bruto)})."
            dados[campo.chave] = bruto[:limite]
    for campo in campos:                       # o que só vale quando outra resposta é tal não fica gravado fora dela
        if campo.so_se and dados.get(campo.so_se[0]) != campo.so_se[1]:
            dados.pop(campo.chave, None)
            erros.pop(campo.chave, None)
    return dados, erros


def validar_finalizacao(dados, internacao):
    """O mínimo para finalizar (a ficha pode ter perguntas em branco, como no papel; a conclusão não): o relatório, a
    classificação geral e o parecer, com o motivo e a justificativa quando ele pede. Devolve {campo: mensagem}."""
    erros = {}
    if not dados.get("relatorio"):
        erros["relatorio"] = "Escreva o relatório social para finalizar."
    if not dados.get(RISCO_GERAL):
        erros[RISCO_GERAL] = "Marque a classificação geral para finalizar."
    parecer = dados.get("parecer")
    if not parecer:
        erros["parecer"] = "Escolha o parecer para finalizar."
    elif parecer == NAO_CONDIZENTE:
        if not internacao.e_triagem:
            erros["parecer"] = "Quem já foi internado não pode ter parecer 'não condizente': isso é da triagem."
        elif not dados.get("motivo_rejeicao"):
            erros["motivo_rejeicao"] = "Escolha o motivo da rejeição."
    elif internacao.status == "rejeitado":
        erros["parecer"] = ("Esta pessoa está marcada como rejeitada na triagem: o parecer tem de ser 'não condizente'. "
                            "Para seguir com a admissão, mude a situação na lista de triagens antes.")
    if parecer and parecer != PARECERES[0] and not dados.get("parecer_texto"):
        erros["parecer_texto"] = "Explique o parecer: a conclusão e o porquê."
    return erros


# ============================================================ o documento
def _linha(rotulo, valor, vazio=EM_BRANCO):
    """'Rótulo: valor' — o valor em negrito; sem valor, a linha para escrever à mão."""
    return [rotulo + (" " if rotulo.endswith("?") else ": "), N(valor) if valor else vazio]


def _opcoes(campo, escolhido):
    return "   ".join(f"( {'X' if opcao == escolhido else ' '} ) {opcao}" for opcao in campo.opcoes)


def blocos_do_campo(campo, v):
    """Blocos de um campo, no jeito do papel: pergunta e resposta (ou linhas em branco)."""
    valor = v.get(campo.chave, "")
    if campo.tipo == "longo":
        resposta = ([Paragrafo([valor], "esquerda", antes=1, depois=2)] if valor else [Pauta(linhas=campo.linhas, altura=18, antes=2)])
        return [Paragrafo([campo.rotulo + (":" if not campo.rotulo.endswith(("?", ".", ":")) else "")], antes=8, unido_ao_proximo=True), *resposta]
    if campo.tipo == "sim_nao":
        detalhe = v.get(campo.chave + "_detalhe", "")
        escolha = "( X ) sim   (   ) não" if valor == "sim" else "(   ) sim   ( X ) não" if valor == "nao" else "(   ) sim   (   ) não"
        return [Paragrafo([campo.rotulo], antes=8, unido_ao_proximo=True),
                Paragrafo([f"{escolha}.  Se sim, especifique: ", N(detalhe)] if detalhe else [f"{escolha}.  Se sim, especifique:"],
                          unido_ao_proximo=not detalhe),
                *([] if detalhe else [Pauta(linhas=1, altura=18, antes=2)])]
    if campo.tipo == "escolha":
        return [Paragrafo([campo.rotulo + ": " + _opcoes(campo, valor)], antes=4)]
    return [Paragrafo(_linha(campo.rotulo, fmt_data(ler_data(valor)) if campo.tipo == "data" else valor,
                             DATA_EM_BRANCO if campo.tipo == "data" else EM_BRANCO), antes=4)]


def _campos_da_linha(campos, v):
    """Campos curtos que o papel põe lado a lado (mesmo `linha`) viram um parágrafo só."""
    partes = []
    for campo in campos:
        if campo.tipo == "escolha":
            partes += [campo.rotulo + ": " + _opcoes(campo, v.get(campo.chave, "")), "    "]
        else:
            valor = fmt_data(ler_data(v.get(campo.chave, ""))) if campo.tipo == "data" else v.get(campo.chave, "")
            partes += [*_linha(campo.rotulo, valor, DATA_EM_BRANCO if campo.tipo == "data" else EM_BRANCO), "    "]
    return Paragrafo(partes[:-1], antes=4)


def _fecho(relatorio):
    """O fecho: quando e por quem foi finalizado no sistema (ou que ainda é rascunho) e a linha da assinatura no papel."""
    if relatorio is not None and relatorio.finalizado and relatorio.finalizado_em:
        em = relatorio.finalizado_em
        situacao = Paragrafo([f"Finalizado no sistema em {em:%d/%m/%Y} às {em:%H:%M} por ", N(relatorio.assinatura or relatorio.finalizado_por)],
                             antes=26)
    else:
        situacao = Paragrafo(["Rascunho: ainda não finalizado no sistema."], antes=26)
    return [situacao,
            Paragrafo(["_" * 38], "centro", antes=24, unido_ao_proximo=True),
            Paragrafo(["Assistente Social"], "centro", unido_ao_proximo=True),
            Paragrafo(["Carimbo/Assinatura"], "centro")]


def _adendos(relatorio):
    """Os adendos, depois da assinatura: cada um com data, hora e autor."""
    if relatorio is None or not relatorio.adendos:
        return []
    saida = [Paragrafo([N("ADENDOS")], "centro", antes=22, unido_ao_proximo=True)]
    for adendo in relatorio.adendos:
        saida += [Paragrafo([N(f"{adendo.criado_em:%d/%m/%Y} às {adendo.criado_em:%H:%M}"), f" — {adendo.criado_por}"], antes=8, unido_ao_proximo=True),
                  Paragrafo([adendo.texto], "esquerda", antes=1, depois=2)]
    return saida


def _cabecalho_da_secao(numero, secao, do_acolhido, do_responsavel):
    """O título da seção e, nas duas primeiras, os dados que o cadastro já tem (não são digitados de novo)."""
    if numero == 1:
        return [Paragrafo([N(f"1) {secao.titulo}:")], antes=6, depois=2, unido_ao_proximo=True),
                *(Paragrafo(_linha(r, do_acolhido[r]), antes=4) for r in ("Nome", "Nome da mãe", "Idade", "Profissão", "Escolaridade", "Telefone")),
                Paragrafo(_linha("Previsão de saída", do_acolhido["Previsão de saída"], DATA_EM_BRANCO), antes=4)]
    titulo = [Paragrafo([N(secao.titulo.upper())], "centro", antes=10, unido_ao_proximo=True, quebra_antes=secao.nova_pagina)]
    if numero == 2:
        r = do_responsavel
        return titulo + [Paragrafo([N(secao.subtitulo.upper())], "centro", antes=2, unido_ao_proximo=True),
                         Paragrafo([N("2) Identificação social:")], antes=8, depois=2, unido_ao_proximo=True),
                         Paragrafo(_linha("Nome", r["Nome"]), antes=4), Paragrafo(_linha("Grau de parentesco", r["Grau de parentesco"]), antes=4),
                         Paragrafo([*_linha("CPF", r["CPF"]), "     ", *_linha("RG", r["RG"])], antes=4),
                         Paragrafo(_linha("Telefone", r["Telefone"]), antes=4)]
    return titulo


def blocos(internacao, relatorio=None, hoje=None):
    """O relatório como lista de blocos de documentos.py (começa em página nova, como qualquer documento do conjunto)."""
    v = valores(internacao, relatorio)
    acolhido, responsavel = identificacao(internacao, hoje)
    saida = [Paragrafo([N("FICHA DE ACOLHIMENTO E CLASSIFICAÇÃO DE RISCO E VULNERABILIDADE DO RESIDENTE – SERVIÇO SOCIAL")],
                       "centro", tamanho=12, quebra_antes=True, depois=6),
             *blocos_do_campo(CAMPOS[0], v)]                                  # a data do acolhimento abre a ficha, antes das seções
    for numero, secao in enumerate(SECOES, 1):
        saida += _cabecalho_da_secao(numero, secao, dict(acolhido), dict(responsavel))
        pendentes = []                                               # campos curtos seguidos que o papel põe na mesma linha
        for campo in secao.campos:
            if campo is CAMPOS[0]:
                continue
            if campo.so_se and v.get(campo.so_se[0]) not in ("", campo.so_se[1]):      # só vale em outra resposta: fica de fora
                continue
            if pendentes and pendentes[-1].linha != campo.linha:
                saida.append(_campos_da_linha(pendentes, v))
                pendentes = []
            if campo.linha:
                pendentes.append(campo)
            else:
                saida += blocos_do_campo(campo, v)
        if pendentes:
            saida.append(_campos_da_linha(pendentes, v))
    return saida + _fecho(relatorio) + _adendos(relatorio)


def blocos_resumo(internacao, relatorio=None, hoje=None):
    """A folha-resumo: quem é, a classificação de risco e vulnerabilidade e a conclusão do parecer, sem as respostas
    detalhadas nem o relatório. É o que sai no prontuário de quem não é do Serviço Social (começa em página nova)."""
    v = valores(internacao, relatorio)
    acolhido = dict(identificacao(internacao, hoje)[0])
    saida = [Paragrafo([N("RESUMO DO ACOLHIMENTO SOCIAL")], "centro", tamanho=13, quebra_antes=True, depois=10),
             *(Paragrafo(_linha(r, acolhido[r]), antes=4) for r in ("Nome", "Nome da mãe", "Idade")),
             *blocos_do_campo(CAMPOS[0], v),
             Paragrafo([N("CLASSIFICAÇÃO DE RISCO E VULNERABILIDADE")], "centro", antes=16, unido_ao_proximo=True)]
    for chave in [c for c, _ in DOMINIOS] + [RISCO_GERAL]:
        saida += blocos_do_campo(POR_CHAVE[chave], v)
    saida.append(Paragrafo([N("CONCLUSÃO")], "centro", antes=16, unido_ao_proximo=True))
    saida += blocos_do_campo(POR_CHAVE["parecer"], v)
    if v.get("parecer") == NAO_CONDIZENTE:
        saida += blocos_do_campo(POR_CHAVE["motivo_rejeicao"], v)
    return saida + _fecho(relatorio)
