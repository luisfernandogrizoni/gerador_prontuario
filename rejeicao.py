"""
Rejeição na triagem: quando a triagem conclui que a pessoa não é condizente com o tratamento da casa, ela é marcada
como "Rejeitado na triagem" (situação da lista de triagens) e a assistente social escreve, no sistema, o relatório do
porquê. O relatório pode ser impresso ou baixado em Word, como os demais impressos (impressos.py).

Usa as mesmas peças do relatório do Serviço Social (servico_social.py): as perguntas são descritas uma vez, em CAMPOS, e
dali saem o formulário da tela, a leitura do que foi digitado e o documento. As respostas ficam em JSON em
modelos.RejeicaoTriagem. Os motivos da lista vêm do que o Manual de Orientação exige de quem entra; "Outro" cobre o resto.
"""

from datetime import date

from documentos import N, Paragrafo
from prontuario import calcular_idade, fmt_data
import servico_social
from servico_social import Campo, Secao, blocos_do_campo

MOTIVOS = ("Sem desejo firme de tratamento", "Comprometimento psíquico grave", "Precisa de acompanhamento médico-hospitalar complexo",
           "Fora do perfil da casa (sexo ou idade)", "Outro")

CAMPOS = (
    Campo("data_da_rejeicao", "Data da rejeição", "data", colunas="c2", padrao="hoje"),
    Campo("motivo", "Motivo principal", "escolha", MOTIVOS, "c6"),
    Campo("relatorio", "Relatório: por que ele não é condizente com o nosso tipo de tratamento", "longo", colunas="c6", linhas=14),
)
SECOES = (Secao("Rejeição na triagem", CAMPOS),)


def ler_formulario(form):
    """Formulário -> (dados, erros), como em servico_social.ler_formulario."""
    return servico_social.ler_formulario(form, CAMPOS)


def valores(internacao, relatorio=None):
    return servico_social.valores(internacao, relatorio, CAMPOS)


def valores_do_formulario(form):
    return servico_social.valores_do_formulario(form, CAMPOS)


def preenchido(relatorio):
    """Já tem alguma resposta digitada?"""
    return servico_social.preenchido(relatorio)


def identificacao(internacao, hoje=None):
    """Os dados do cadastro que o relatório mostra sem pedir de novo: [(rótulo, valor)]."""
    p, hoje = internacao.pessoa, hoje or date.today()
    idade = calcular_idade(p.nascimento, hoje)
    return [("Nome", p.nome), ("Nome da mãe", p.mae), ("Idade", f"{idade} anos" if idade is not None else ""),
            ("Cidade", "/".join(x for x in (p.cidade, p.estado) if x)), ("Responsável", internacao.resp_nome),
            ("Data da triagem", fmt_data(internacao.data_triagem))]


def blocos(internacao, rejeicao=None, hoje=None):
    """O relatório como lista de blocos de documentos.py (começa em página nova, como qualquer documento do conjunto)."""
    v = valores(internacao, rejeicao)
    saida = [Paragrafo([N("RELATÓRIO DE REJEIÇÃO NA TRIAGEM")], "centro", tamanho=13, quebra_antes=True, depois=10)]
    for rotulo, valor in identificacao(internacao, hoje):
        saida.append(Paragrafo([rotulo + ": ", N(valor) if valor else "_" * 24], antes=4))
    for campo in CAMPOS:
        saida += blocos_do_campo(campo, v)
    saida += [Paragrafo(["_" * 38], "centro", antes=36, unido_ao_proximo=True),
              Paragrafo(["Assistente Social"], "centro", unido_ao_proximo=True),
              Paragrafo(["Carimbo/Assinatura"], "centro")]
    return saida
