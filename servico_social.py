"""
Relatório do Serviço Social: a "Ficha de acolhimento e classificação de risco e vulnerabilidade do residente", que a
assistente social escreve direto no sistema em vez de preencher à mão.

O modelo do escritório está descrito UMA vez, em SECOES (seções e perguntas). Dele saem:
  * o formulário da tela (templates/servico_social_form.html);
  * o documento para imprimir ou baixar em Word (blocos de documentos.py), com as respostas no lugar das linhas em
    branco — e as linhas em branco de sempre onde ainda não há resposta;
  * a leitura e a validação do que foi digitado (ler_formulario).

As respostas ficam numa linha por internação (modelos.RelatorioSocial, coluna `dados` em JSON, só o que foi
preenchido). Os dados que o sistema já tem (nome, mãe, idade, profissão, escolaridade, telefones e o responsável)
não são digitados de novo: aparecem no formulário e no documento direto do cadastro.
"""

from dataclasses import dataclass
from datetime import date

from documentos import N, Paragrafo, Pauta
from prontuario import calcular_idade, fmt_data, ler_data, previsao_termino
from validacao import fmt_cep, fmt_cpf, fmt_rg

LIMITE_TEXTO, LIMITE_LONGO = 200, 5000
EM_BRANCO = "_" * 24
DATA_EM_BRANCO = "____/____/________"


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
        C("sexo", "Sexo", "escolha", ("Masculino", "Feminino"), "c2", linha="a"),
        C("genero", "Gênero", colunas="c2", linha="a"),
        C("opcao_sexual", "Opção sexual", colunas="c2", linha="a"),
        C("raca_cor", "Qual raça / cor você se considera?", "escolha",
          ("Negra/Preta", "Indígena", "Branca", "Amarela/Oriental", "Parda/Mestiça", "Não respondeu"), "c6"),
        C("moradia", "Qual a situação atual de moradia", colunas="c6"),
        C("encaminhado_por", "Encaminhado por", colunas="c3"),
        C("chegada", "Chegada", "escolha", ("Resgate", "Abordagem", "Família", "Voluntário"), "c3"),
        C("numero_internacoes", "Número de internações", colunas="c2", linha="b"),
        C("ultima_internacao", "Última internação", "data", colunas="c2", linha="b"),
        C("desligamento_data", "Data do desligamento", "data", colunas="c2", linha="c"),
        C("desligamento_local", "Local", colunas="c4", linha="c"),
        C("desligamento_motivo", "Motivo", "longo", colunas="c6", linhas=5),
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
        C("crencas", "Quais as crenças do residente?", "longo", colunas="c6", linhas=3),
        C("crencas_familiares", "Qual a crença dos familiares?", "longo", colunas="c6", linhas=3),
        C("tratamento_com_crenca", "O residente já fez algum tipo de tratamento que teve envolvimento com suas crenças? Se sim, qual?",
          "longo", colunas="c6", linhas=3),
    )),
    Secao("Histórico familiar", (
        C("familiares", "Comente sobre os familiares de primeiro e segundo grau do residente.", "longo", colunas="c6", linhas=3),
        C("filho_adotivo", "O residente é filho adotivo?", "longo", colunas="c6", linhas=2),
        C("irmaos", "O residente tem irmãos? Quantos? Qual a idade? Comente um pouco sobre a relação com eles.", "longo", colunas="c6", linhas=3),
        C("pensou_em_internar", "Quando o familiar começou a pensar em internar o residente? A partir de qual atitude?", "longo", colunas="c6", linhas=3),
        C("grupos_de_apoio", "O familiar já frequentou grupos de apoio? Por quanto tempo? Qual?", "longo", colunas="c6", linhas=3),
        C("convivio", "Como é o convívio familiar em geral? Já houve agressões verbais e físicas?", "longo", colunas="c6", linhas=3),
        C("dependencia_na_familia", "Existe histórico de dependência química na família?", "longo", colunas="c6", linhas=3),
    )),
    Secao("Investigação sobre perdas", (
        C("maior_perda", "Qual foi a maior perda sentimental que o residente teve?", "longo", colunas="c6", linhas=3),
        C("razoes_do_uso", "Quais são as principais razões para o residente fazer uso de drogas e/ou álcool?", "longo", colunas="c6", linhas=3),
        C("observacoes", "Observações complementares", "longo", colunas="c6", linhas=3),
        C("data_do_relatorio", "Data", "data", colunas="c2"),
    )),
)
CAMPOS = [campo for secao in SECOES for campo in secao.campos]


# ============================================================ o que o cadastro já sabe
def _data_da_triagem(i):
    return i.data_triagem.isoformat() if i.data_triagem else ""


PADROES = {
    "data_da_triagem": _data_da_triagem,
    "hoje": lambda i: date.today().isoformat(),
    "endereco": lambda i: i.pessoa.endereco, "numero": lambda i: i.pessoa.numero, "bairro": lambda i: i.pessoa.bairro,
    "cep": lambda i: fmt_cep(i.pessoa.cep), "cidade": lambda i: i.pessoa.cidade, "estado": lambda i: i.pessoa.estado,
}


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
    """O que aparece em cada campo: o digitado; onde ainda não há nada, o que vem do cadastro (campo.padrao).
    `campos`: outro conjunto de perguntas (o relatório de rejeição usa as mesmas peças)."""
    salvo = (relatorio.dados if relatorio is not None else None) or {}
    resultado = {}
    for campo in campos or CAMPOS:
        if campo.tipo == "sim_nao":
            resultado[campo.chave] = salvo.get(campo.chave, "")
            resultado[campo.chave + "_detalhe"] = salvo.get(campo.chave + "_detalhe", "")
        elif campo.chave in salvo:
            resultado[campo.chave] = salvo[campo.chave]
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


# ============================================================ o que foi digitado
def ler_formulario(form, campos=None):
    """Formulário -> (dados, erros). `dados` guarda só o que foi preenchido; valores fora do esperado viram erro."""
    dados, erros = {}, {}
    for campo in campos or CAMPOS:
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
    return dados, erros


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


def _fecho(v):
    data = fmt_data(ler_data(v.get("data_do_relatorio", ""))) or DATA_EM_BRANCO
    return [Paragrafo([f"Data: {data}"], antes=26),
            Paragrafo(["_" * 38], "centro", antes=24, unido_ao_proximo=True),
            Paragrafo(["Assistente Social"], "centro", unido_ao_proximo=True),
            Paragrafo(["Carimbo/Assinatura"], "centro")]


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
            if pendentes and pendentes[-1].linha != campo.linha:
                saida.append(_campos_da_linha(pendentes, v))
                pendentes = []
            if campo.linha:
                pendentes.append(campo)
            else:
                saida += blocos_do_campo(campo, v)
        if pendentes:
            saida.append(_campos_da_linha(pendentes, v))
    return saida + _fecho(v)
