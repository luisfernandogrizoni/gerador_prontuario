"""
Os impressos de cada acolhido, reunidos num documento só (um arquivo Word, ou as folhas que o preview da aba Imprimir da ficha mostra):

    Triagem               Na internação                                   Serviço Social
      exames   Pedido       prontuario         o prontuário                resumo-social      Resumo do acolhimento social
      enxoval  Enxoval      manual             Manual de orientação        relatorio-social   Relatório do Serviço Social
                            multiprofissional  Ficha multiprofissional                        (ficha, relatório e parecer)
                            capa               Capa do envelope            relatorio-alta     Relatório de alta (só de quem recebeu baixa)

Quem escolhe o que entra são as caixinhas da aba Imprimir da ficha (?itens=exames,enxoval). Sem escolha, vale o conjunto de cada
situação: a triagem leva exames e enxoval; a internação leva o prontuário, o manual, a ficha multiprofissional e a capa
do envelope, mais o Serviço Social quando o acolhimento social já foi finalizado (em rascunho ele só serviria para
preencher à mão).

A capa do envelope traz o término quando ele já está no sistema e, para quem já foi internado antes, as datas das passagens anteriores
(Internacao.passagens_anteriores); quem só tem uma internação leva a capa de sempre, com o término em branco para escrever na baixa.

O acolhimento social é sigiloso (cadastros.pode_servico_social): quem é do Serviço Social ou administrador leva o
relatório completo; os outros levam só a folha-resumo (classificação e conclusão) e não vêem o relatório nem na lista da aba Imprimir.

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
import relatorio_alta
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
    "relatorio-alta": "Relatório de alta",
}
GRUPOS = (("Triagem", ("exames", "enxoval")),
          ("Na internação", ("prontuario", "manual", "multiprofissional", "capa")),
          ("Serviço Social", ("resumo-social", "relatorio-social", "relatorio-alta")))
ORDEM = tuple(chave for _, chaves in GRUPOS for chave in chaves)
DA_TRIAGEM = ("exames", "enxoval")
SIGILOSOS = ("relatorio-social", "relatorio-alta")          # só quem é do Serviço Social (ou administrador) e quem lê os sigilosos vê


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


def _linha_da_passagem(i):
    """Uma passagem anterior na tabela da capa: ('1ª', início, término, motivo). Data que falta (registro importado de uma pasta antiga) sai como '—'."""
    return (f"{i.numero_da_passagem}ª", fmt_data(i.inicio) or "—", fmt_data(i.termino) or "—", i.motivo)


def passagem_da_capa(internacao):
    """A capa é do ENVELOPE da pessoa, e o envelope é um só: sai sempre com a internação mais recente (início, término e convênio dela), com as outras
    passagens listadas, qualquer que seja a passagem aberta quando se pede o impresso. Quem ainda não teve internação de verdade (só triagem) leva o próprio registro."""
    return (internacao.pessoa.passagens or [internacao])[-1]


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
        recente = passagem_da_capa(internacao)
        return fichas.capa_do_envelope(pessoa.nome, fmt_data(recente.inicio), _convenio_sus(recente), pessoa.cidade,
                                       termino_fmt=fmt_data(recente.termino), anteriores=[_linha_da_passagem(i) for i in recente.passagens_anteriores],
                                       motivo=recente.motivo if recente.status == "inativo" else "")
    if chave == "resumo-social":
        return [Pagina(), *servico_social.blocos_resumo(internacao, internacao.relatorio_social, hoje)]
    if chave == "relatorio-alta":
        return [Pagina(), *relatorio_alta.blocos(internacao, internacao.relatorio_alta, hoje)]
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
    """O que a lista da aba Imprimir diz do item quando ele ainda não está pronto: 'em branco' ou 'rascunho'. Da ficha multiprofissional só para quem a lê."""
    if chave == "multiprofissional":
        situacao = ficha_saude.estado(internacao.ficha_saude) if saude else "finalizado"
        return "" if situacao == "finalizado" else (situacao or "em branco")
    if chave == "relatorio-alta":
        situacao = relatorio_alta.estado(internacao.relatorio_alta)
        return "" if situacao == "finalizado" else (situacao or "em branco")
    if chave == "capa":              # pedida de uma passagem que não é a mais recente: a lista avisa de qual ela sai
        recente = passagem_da_capa(internacao)
        return "" if recente.id == internacao.id else f"da passagem {recente.numero_da_passagem}, a mais recente" if recente.numero_da_passagem else "da passagem mais recente"
    if chave not in ("resumo-social", "relatorio-social"):
        return ""
    situacao = servico_social.estado(internacao.relatorio_social)
    if situacao == "finalizado":
        return ""
    return situacao or "em branco"


def disponiveis(internacao, completo=False, saude=False, pedidos=()):
    """Os impressos desta passagem, na ordem de impressão: [{chave, rotulo, aviso}] (a lista da aba Imprimir). A triagem leva o pedido de exames e o enxoval; a internação, o prontuário,
    o manual, a ficha multiprofissional e a capa do envelope; o Serviço Social entra assim que o acolhimento foi começado (em rascunho ele serve para preencher à mão: o aviso diz) ou quando
    foi `pedidos` (um "Salvar e imprimir" do acolhimento): o relatório completo para quem pode vê-lo, a folha-resumo para os outros; o relatório de alta, para quem já recebeu baixa e pode vê-lo.
    `completo`: quem pede pode ver o relatório do Serviço Social; `saude`: pode ler a ficha de saúde (o aviso de "em branco" ou "rascunho")."""
    chaves = list(DA_TRIAGEM) if internacao.e_triagem else ["prontuario", "manual", "multiprofissional", "capa"]
    social = "relatorio-social" if completo else "resumo-social"
    if servico_social.estado(internacao.relatorio_social) or social in pedidos:
        chaves.append(social)
    if internacao.status == "inativo" and completo:
        chaves.append("relatorio-alta")
    return [{"chave": c, "rotulo": ROTULOS[c], "aviso": _aviso_do_item(c, internacao, saude)} for c in ORDEM if c in chaves]
