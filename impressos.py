"""
Os impressos de cada acolhido, reunidos num documento só (um arquivo Word, ou uma página para ver e imprimir):

    Triagem               Na internação                                   Serviço Social
      exames   Pedido       prontuario         o prontuário                resumo-social      Resumo do acolhimento social
      enxoval  Enxoval      manual             Manual de orientação        relatorio-social   Relatório do Serviço Social
                            multiprofissional  Ficha multiprofissional                        (ficha, relatório e parecer)
                            capa               Capa do envelope

Quem escolhe o que entra é a barra acima do documento (?itens=exames,enxoval). Sem escolha, vale o conjunto de cada
situação: a triagem leva exames e enxoval; a internação leva o prontuário, o manual, a ficha multiprofissional e a capa
do envelope, mais o Serviço Social quando o acolhimento social já foi finalizado (em rascunho ele só serviria para
preencher à mão).

O acolhimento social é sigiloso (cadastros.pode_servico_social): quem é do Serviço Social ou administrador leva o
relatório completo; os outros levam só a folha-resumo (classificação e conclusão) e não vêem o relatório nem na barra.

A ficha multiprofissional de saúde (ficha_saude.py) sai com o que a enfermagem e a equipe escreveram no sistema só para quem pode ler a ficha
(cadastros.pode_ler_saude); os outros levam a ficha em branco, para escrever à mão, sem nada do conteúdo.

Imprimir (ou baixar) exames ou enxoval anota, na triagem, para qual data de internação isso foi feito: enquanto não foi,
a lista de triagens pergunta se é para imprimir ao salvar (modelos.Internacao.exames_impressos_para).
"""

import re
from datetime import date

import catalogo
import ficha_saude
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
    "resumo-social": "Resumo do Serviço Social",
    "relatorio-social": "Relatório do Serviço Social",
}
GRUPOS = (("Triagem", ("exames", "enxoval")),
          ("Na internação", ("prontuario", "manual", "multiprofissional", "capa")),
          ("Serviço Social", ("resumo-social", "relatorio-social")))
ORDEM = tuple(chave for _, chaves in GRUPOS for chave in chaves)
DA_TRIAGEM = ("exames", "enxoval")
SIGILOSOS = ("relatorio-social",)          # só quem é do Serviço Social (ou administrador) vê


def _social(internacao, completo):
    """O que do Serviço Social vai no conjunto: nada enquanto o acolhimento não foi finalizado; depois, o relatório
    completo para quem pode vê-lo e a folha-resumo para os outros."""
    if servico_social.estado(internacao.relatorio_social) != "finalizado":
        return ()
    return ("relatorio-social",) if completo else ("resumo-social",)


def itens_padrao(internacao, completo=False):
    """O conjunto de cada situação (veja o alto do arquivo). `completo` = quem pede pode ver o relatório do Serviço Social."""
    if internacao.status == "rejeitado":              # não vai ser internado: o que interessa é a conclusão da triagem
        return _social(internacao, completo) or DA_TRIAGEM
    if internacao.e_triagem:
        return DA_TRIAGEM
    return ("prontuario", "manual", "multiprofissional", "capa") + _social(internacao, completo)


def ler_itens(texto, internacao, completo=False):
    """?itens=a,b -> só os que existem e que quem pede pode ver, na ordem de impressão; sem nenhum válido, o conjunto padrão."""
    pedidos = {p.strip() for p in (texto or "").split(",")}
    escolhidos = tuple(chave for chave in ORDEM if chave in pedidos and (completo or chave not in SIGILOSOS))
    return escolhidos or itens_padrao(internacao, completo)


def _convenio_sus(internacao):
    """Capa do envelope: 'Convênio SUS' é Sim nos convênios gratuitos (Caps AD, Prefeitura...) e Não no Particular."""
    cadastro = catalogo.atual()
    if cadastro.e_gratuito(internacao.convenio):
        return True
    return False if cadastro.existe(internacao.convenio) else None


def _blocos(chave, internacao, hoje, saude=False):
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
        return fichas.ficha_multiprofissional(pessoa.nome, f"{idade} anos" if idade is not None else "",
                                              ficha_saude.conteudo(internacao) if saude else None)
    if chave == "capa":
        return fichas.capa_do_envelope(pessoa.nome, fmt_data(internacao.inicio), _convenio_sus(internacao), pessoa.cidade)
    if chave == "resumo-social":
        return [Pagina(), *servico_social.blocos_resumo(internacao, internacao.relatorio_social, hoje)]
    return [Pagina(), *servico_social.blocos(internacao, internacao.relatorio_social, hoje)]      # relatorio-social


def _nome_do_arquivo(texto):
    return re.sub(r'[\\/:*?"<>|]+', " ", texto).strip()


def documento(internacao, itens, hoje=None, saude=False):
    """O Documento (documentos.py) com os `itens` pedidos, um depois do outro, cada um em página nova. `saude`: quem pede pode ler a ficha de saúde
    (senão a ficha multiprofissional sai em branco)."""
    hoje = hoje or date.today()
    blocos = [bloco for chave in itens for bloco in _blocos(chave, internacao, hoje, saude)]
    rotulo = (ROTULOS[itens[0]] if len(itens) == 1
              else " e ".join(ROTULOS[c].lower() if i else ROTULOS[c] for i, c in enumerate(itens)) if len(itens) == 2
              else "Impressos da internação")
    titulo = f"{rotulo} - {internacao.pessoa.nome}"
    return Documento(nome_arquivo=_nome_do_arquivo(titulo), titulo=titulo, blocos=blocos, fonte="Arial", tamanho=12, margem_lateral=720)


def _aviso_do_item(chave, internacao, saude=False):
    """O que a barra diz do item quando ele ainda não está pronto: 'em branco' ou 'rascunho'. Da ficha multiprofissional só para quem a lê."""
    if chave == "multiprofissional":
        situacao = ficha_saude.estado(internacao.ficha_saude) if saude else "finalizado"
        return "" if situacao == "finalizado" else (situacao or "em branco")
    if chave not in ("resumo-social", "relatorio-social"):
        return ""
    situacao = servico_social.estado(internacao.relatorio_social)
    if situacao == "finalizado":
        return ""
    return situacao or "em branco"


def barra(internacao, itens, endereco, completo=False, saude=False):
    """O que a barra acima do documento mostra: os impressos em grupos, cada um ligado ou desligado.
    `endereco(itens)` devolve o endereço de quem clicar. Nunca deixa ficar sem nenhum. `completo` = quem vê pode ver o
    relatório do Serviço Social (senão ele nem aparece); `saude`, pode ler a ficha de saúde (o aviso de "em branco" ou "rascunho")."""
    grupos = []
    for titulo, chaves in GRUPOS:
        marcas = []
        for chave in (c for c in chaves if completo or c not in SIGILOSOS):
            ativa = chave in itens
            novos = [c for c in ORDEM if (c in itens) != (c == chave)]
            marcas.append({"nome": ROTULOS[chave], "ativa": ativa,
                           "url": endereco(novos) if novos else endereco(list(itens)),
                           "aviso": _aviso_do_item(chave, internacao, saude)})
        if marcas:
            grupos.append({"titulo": titulo, "itens": marcas})
    return grupos
