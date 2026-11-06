"""
O relatório de alta: o texto livre que a assistente social escreve quando a pessoa recebe baixa.

É a versão mais simples possível, de propósito: sem perguntas fixas, só um campo de texto. O documento sai no timbre da casa, com os dados básicos do acolhido
(nome, nascimento, CPF, convênio, período na casa e motivo da saída), o texto e, no fim, a assinatura com o nome e o registro profissional (CRESS) de quem
finalizou.

Segue o mesmo molde do acolhimento social (servico_social.py): sigiloso (escrevem a assistente social e o administrador; lê, sem editar, quem recebeu a permissão de
ler os sigilosos), nasce como rascunho, finaliza e guarda data, hora e assinatura, e depois ainda se altera com o histórico de versões só do administrador
(versoes.py). A baixa de uma internação cobra o relatório no quadro de avisos da assistente social (avisos.py): fica vermelho depois de PRAZO_EM_DIAS dias.
"""

from datetime import date
from types import SimpleNamespace

import servico_social
from documentos import N, Paragrafo, Pauta
from prontuario import calcular_idade, fmt_data
from validacao import fmt_cpf

CHAVE = "texto"
ROTULO = "Relatório de alta"
LIMITE_DO_TEXTO = 20000                 # caracteres
PRAZO_EM_DIAS = 7                        # a baixa passou disto sem o relatório finalizado: o aviso fica vermelho
# versoes.py lê as perguntas de cada relatório por aqui (só há uma)
CAMPOS = [SimpleNamespace(chave=CHAVE, rotulo=ROTULO, tipo="longo")]


def estado(relatorio):
    """Em que pé está o relatório de alta: '' (não iniciado), 'rascunho' ou 'finalizado'."""
    return servico_social.estado(relatorio)


def texto(relatorio):
    return ((relatorio.dados if relatorio is not None else None) or {}).get(CHAVE, "")


def valores(relatorio):
    """O que a tela mostra no campo: o texto gravado (ou nada, se ainda não há relatório)."""
    return {CHAVE: texto(relatorio)}


def ler_formulario(form):
    """O que a assistente social digitou: ({'texto': ...}, erros). Cada Enter vira uma quebra de linha só (o navegador manda CR+LF)."""
    digitado = (form.get(CHAVE) or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    erros = {}
    if len(digitado) > LIMITE_DO_TEXTO:
        erros[CHAVE] = f"O relatório pode ter até {LIMITE_DO_TEXTO} caracteres (tem {len(digitado)})."
    return {CHAVE: digitado}, erros


def validar_finalizacao(dados):
    """Finalizar (e alterar o que já foi finalizado) exige o texto."""
    return {} if (dados.get(CHAVE) or "").strip() else {CHAVE: "Escreva o relatório antes de finalizar."}


def dias_desde_a_baixa(internacao, hoje):
    """Há quantos dias a baixa foi dada no sistema (None nas baixas de antes deste recurso, que não cobram o relatório)."""
    return None if internacao.baixa_em is None else max((hoje - internacao.baixa_em.date()).days, 0)


def dados_basicos(internacao, hoje):
    """[(rótulo, valor)] do documento: o que o cadastro já sabe, sem pedir de novo."""
    p = internacao.pessoa
    idade = calcular_idade(p.nascimento, hoje)
    nascimento = (fmt_data(p.nascimento) + (f" ({idade} anos)" if idade is not None else "")) if p.nascimento else ""
    permanencia = ""
    if internacao.inicio and internacao.termino and internacao.termino >= internacao.inicio:
        dias = (internacao.termino - internacao.inicio).days
        permanencia = f"{dias} dia{'' if dias == 1 else 's'}"
    return [("Nome", p.nome), ("Data de nascimento", nascimento), ("CPF", fmt_cpf(p.cpf) if p.cpf else ""),
            ("Convênio", internacao.convenio), ("Data de internação", fmt_data(internacao.inicio)),
            ("Data de saída", fmt_data(internacao.termino)), ("Tempo de permanência", permanencia), ("Motivo da saída", internacao.motivo)]


def blocos(internacao, relatorio=None, hoje=None):
    """O relatório como lista de blocos de documentos.py (começa em página nova, como qualquer documento do conjunto): título, dados básicos, o texto e a assinatura."""
    hoje = hoje or date.today()
    escrito = texto(relatorio)
    saida = [Paragrafo([N("RELATÓRIO DE ALTA – SERVIÇO SOCIAL")], "centro", tamanho=13, quebra_antes=True, depois=18),
             *(Paragrafo(servico_social.linha_de_dado(rotulo, valor), antes=2, entrelinha=servico_social.ENTRELINHA) for rotulo, valor in dados_basicos(internacao, hoje)),
             servico_social.subtitulo("RELATÓRIO")]
    saida += servico_social.texto_corrido(escrito) if escrito else [Pauta(linhas=22, altura=18, antes=4)]       # sem texto ainda: as linhas para escrever à mão
    return saida + servico_social.fecho_da_assinatura(relatorio)
