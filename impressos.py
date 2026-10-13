"""
Os impressos de cada acolhido, reunidos num documento só (um arquivo Word, ou uma página para ver e imprimir):

    Antes da internação (triagem com a internação marcada)    Na internação
      exames       Pedido de exames                              prontuario         o prontuário
      enxoval      Enxoval                                       manual             Manual de orientação (para a família)
                                                                 multiprofissional  Ficha multiprofissional de saúde
                                                                 capa               Capa do envelope
                                                                 relatorio-social   Relatório do Serviço Social

Quem escolhe o que entra é a barra acima do documento (?itens=exames,enxoval). Sem escolha, vale o conjunto de cada
situação: a triagem leva exames e enxoval; a internação leva o prontuário, o manual, a ficha multiprofissional e a capa
do envelope, e o relatório do Serviço Social quando ele já foi escrito (em branco ele só serviria para preencher à mão).
"""

import re
from datetime import date

import catalogo
import fichas
import manual_de_orientacao
import servico_social
from documentos import Documento, Pagina
from prontuario import calcular_idade, fmt_data, montar_documento

ROTULOS = {
    "exames": "Pedido de exames",
    "enxoval": "Enxoval",
    "prontuario": "Prontuário",
    "manual": "Manual de orientação",
    "multiprofissional": "Ficha multiprofissional de saúde",
    "capa": "Capa do envelope",
    "relatorio-social": "Relatório do Serviço Social",
}
GRUPOS = (("Antes da internação", ("exames", "enxoval")),
          ("Na internação", ("prontuario", "manual", "multiprofissional", "capa", "relatorio-social")))
ORDEM = tuple(chave for _, chaves in GRUPOS for chave in chaves)
DA_TRIAGEM = ("exames", "enxoval")


def itens_padrao(internacao):
    """O conjunto de cada situação (veja o alto do arquivo)."""
    if internacao.e_triagem:
        return DA_TRIAGEM
    base = ("prontuario", "manual", "multiprofissional", "capa")
    return base + (("relatorio-social",) if servico_social.preenchido(internacao.relatorio_social) else ())


def ler_itens(texto, internacao):
    """?itens=a,b -> só os que existem, na ordem de impressão; sem nenhum válido, o conjunto padrão."""
    pedidos = {p.strip() for p in (texto or "").split(",")}
    escolhidos = tuple(chave for chave in ORDEM if chave in pedidos)
    return escolhidos or itens_padrao(internacao)


def _convenio_sus(internacao):
    """Capa do envelope: 'Convênio SUS' é Sim nos convênios gratuitos (Caps AD, Prefeitura...) e Não no Particular."""
    cadastro = catalogo.atual()
    if cadastro.e_gratuito(internacao.convenio):
        return True
    return False if cadastro.existe(internacao.convenio) else None


def _blocos(chave, internacao, hoje):
    pessoa = internacao.pessoa
    if chave == "exames":
        return fichas.pedido_de_exames(pessoa.nome)
    if chave == "enxoval":
        return fichas.enxoval(pessoa.nome)
    if chave == "prontuario":
        return [Pagina(), *montar_documento(internacao.dados_completos()).blocos]
    if chave == "manual":
        return manual_de_orientacao.blocos()
    if chave == "multiprofissional":
        idade = calcular_idade(pessoa.nascimento, hoje)
        return fichas.ficha_multiprofissional(pessoa.nome, f"{idade} anos" if idade is not None else "")
    if chave == "capa":
        return fichas.capa_do_envelope(pessoa.nome, fmt_data(internacao.inicio), _convenio_sus(internacao), pessoa.cidade)
    return [Pagina(), *servico_social.blocos(internacao, internacao.relatorio_social, hoje)]      # relatorio-social


def _nome_do_arquivo(texto):
    return re.sub(r'[\\/:*?"<>|]+', " ", texto).strip()


def documento(internacao, itens, hoje=None):
    """O Documento (documentos.py) com os `itens` pedidos, um depois do outro, cada um em página nova."""
    hoje = hoje or date.today()
    blocos = [bloco for chave in itens for bloco in _blocos(chave, internacao, hoje)]
    rotulo = (ROTULOS[itens[0]] if len(itens) == 1
              else " e ".join(ROTULOS[c].lower() if i else ROTULOS[c] for i, c in enumerate(itens)) if len(itens) == 2
              else "Impressos da internação")
    titulo = f"{rotulo} - {internacao.pessoa.nome}"
    return Documento(nome_arquivo=_nome_do_arquivo(titulo), titulo=titulo, blocos=blocos, fonte="Arial", tamanho=12, margem_lateral=720)


def barra(internacao, itens, endereco):
    """O que a barra acima do documento mostra: os impressos em grupos, cada um ligado ou desligado.
    `endereco(itens)` devolve o endereço de quem clicar. Nunca deixa ficar sem nenhum."""
    grupos = []
    for titulo, chaves in GRUPOS:
        marcas = []
        for chave in chaves:
            ativa = chave in itens
            novos = [c for c in ORDEM if (c in itens) != (c == chave)]
            marcas.append({"nome": ROTULOS[chave], "ativa": ativa,
                           "url": endereco(novos) if novos else endereco(list(itens)),
                           "aviso": "em branco" if chave == "relatorio-social" and not servico_social.preenchido(internacao.relatorio_social) else ""})
        grupos.append({"titulo": titulo, "itens": marcas})
    return grupos
