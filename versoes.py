"""
Histórico de versões dos relatórios sigilosos: o acolhimento social (servico_social.py) e a ficha de saúde, a anamnese (ficha_saude.py).

Não há adendos. Depois de finalizado, o relatório continua sendo de quem o escreve (a assistente social, a enfermeira): ele o altera direto, e cada
alteração fica guardada aqui como uma versão completa, com data, hora e quem alterou. A versão 1 é o relatório como foi finalizado (nos que foram
finalizados antes de este histórico existir, ela é guardada na primeira alteração, a partir do que estava gravado). O relatório mostra sempre a versão
de agora, sem marca nenhuma de que foi alterado.

O administrador acompanha pelo histórico (com o conteúdo de cada versão) e pela trilha de auditoria (que registra a alteração, sem o conteúdo).
Os adendos que já existiam vieram para cá como registros do tipo "adendo" (migracoes.py): ficam guardados, só o administrador os vê.
"""

from datetime import datetime
from types import SimpleNamespace

import ficha_saude
import servico_social
from modelos import VersaoRelatorio

SOCIAL, SAUDE = "social", "saude"
TIPOS = {SOCIAL: "Acolhimento social", SAUDE: "Ficha de saúde"}
FINALIZADO, ALTERADO, ADENDO = "finalizado", "alterado", "adendo"
EVENTOS = {FINALIZADO: "Finalizado", ALTERADO: "Alterado", ADENDO: "Adendo (de antes do histórico)"}
LIMITE_DO_ROTULO = 60


def _campos(tipo):
    return servico_social.CAMPOS if tipo == SOCIAL else ficha_saude.CAMPOS


def rotulo_do_campo(tipo, chave):
    """O nome de uma pergunta para o histórico e para a trilha ('Moradia', 'Possui alergia a algum alimento ou medicamento? (especificação)')."""
    base, detalhe = (chave[:-len("_detalhe")], True) if chave.endswith("_detalhe") else (chave, False)
    campo = next((c for c in _campos(tipo) if c.chave == base), None)
    texto = campo.rotulo.rstrip(":?. ") if campo else chave
    if len(texto) > LIMITE_DO_ROTULO:
        texto = texto[:LIMITE_DO_ROTULO - 1].rstrip() + "…"
    return f"{texto} (resposta)" if detalhe else texto


def campos_alterados(tipo, antes, depois):
    """As respostas que mudaram de uma versão para outra (chaves, na ordem das perguntas; o detalhe do sim/não conta à parte)."""
    antes, depois = antes or {}, depois or {}
    ordem = []
    for campo in _campos(tipo):
        ordem.append(campo.chave)
        if campo.tipo == "sim_nao":
            ordem.append(campo.chave + "_detalhe")
    ordem += sorted((set(antes) | set(depois)) - set(ordem))          # respostas de um modelo antigo da ficha
    return [chave for chave in ordem if (antes.get(chave) or "") != (depois.get(chave) or "")]


def _do_tipo(internacao, tipo):
    return sorted((v for v in internacao.versoes_relatorios if v.tipo == tipo), key=lambda v: (v.criado_em, v.id))


def historico(internacao, tipo):
    """O histórico de um relatório, da versão mais antiga para a mais nova: [{id, numero, evento, quando, por, campos, texto}]. `numero` é o da
    versão (o relatório completo daquele momento) e é None nos adendos antigos, que só têm o texto."""
    saida, numero = [], 0
    for v in _do_tipo(internacao, tipo):
        if v.evento != ADENDO:
            numero += 1
        saida.append({"id": v.id, "numero": None if v.evento == ADENDO else numero, "evento": v.evento, "nome_do_evento": EVENTOS.get(v.evento, v.evento),
                      "quando": v.criado_em, "por": v.criado_por, "texto": v.texto,
                      "campos": [rotulo_do_campo(tipo, c) for c in (v.campos or [])]})
    return saida


def quantas(internacao, tipo):
    """Quantas versões (relatórios completos) o histórico tem; os adendos antigos não contam."""
    return sum(1 for v in internacao.versoes_relatorios if v.tipo == tipo and v.evento != ADENDO)


def tem_historico(internacao, tipo):
    return any(v.tipo == tipo for v in internacao.versoes_relatorios)


def versao(internacao, tipo, numero):
    """A versão de número `numero` (VersaoRelatorio), ou None."""
    versoes = [v for v in _do_tipo(internacao, tipo) if v.evento != ADENDO]
    return versoes[numero - 1] if 1 <= numero <= len(versoes) else None


def ultima_alteracao(internacao, tipo):
    """Quando e por quem o relatório foi alterado pela última vez depois de finalizado ({quando, por}), ou None."""
    alteracoes = [v for v in _do_tipo(internacao, tipo) if v.evento == ALTERADO]
    return {"quando": alteracoes[-1].criado_em, "por": alteracoes[-1].criado_por} if alteracoes else None


def registrar(internacao, tipo, evento, dados, campos, por, quando=None, texto=""):
    """Guarda uma versão (ainda sem gravar: quem chama grava junto com o resto)."""
    nova = VersaoRelatorio(tipo=tipo, evento=evento, dados=dict(dados or {}), campos=list(campos or []), texto=texto or "",
                           criado_em=quando or datetime.now(), criado_por=(por or "")[:200])
    internacao.versoes_relatorios.append(nova)
    return nova


def garantir_original(internacao, tipo, relatorio):
    """Antes de alterar um relatório já finalizado: se o histórico ainda não tem o relatório como foi finalizado (foi finalizado antes de o histórico
    existir), guarda agora o que está gravado, com a data e a assinatura da finalização."""
    if any(v.tipo == tipo and v.evento == FINALIZADO for v in internacao.versoes_relatorios):
        return
    registrar(internacao, tipo, FINALIZADO, relatorio.dados, [], relatorio.assinatura or relatorio.finalizado_por,
              relatorio.finalizado_em or relatorio.atualizado_em)


def descricao_da_ultima(internacao, tipo):
    """Para a trilha de auditoria, a versão mais nova: 'versão 3 · mudou: Moradia; Relatório social' (nunca o conteúdo, só quais perguntas)."""
    versoes = [h for h in historico(internacao, tipo) if h["numero"]]
    if not versoes:
        return ""
    ultima = versoes[-1]
    return f"versão {ultima['numero']}" + (" · mudou: " + "; ".join(ultima["campos"]) if ultima["campos"] else "")


def como_relatorio(relatorio, v):
    """O relatório (ou a ficha) com as respostas de uma versão do histórico, para abrir o documento daquela versão. A assinatura da finalização é a
    do relatório de agora: a versão é só o conteúdo."""
    return SimpleNamespace(dados=dict(v.dados or {}), situacao=relatorio.situacao, finalizado=relatorio.finalizado, finalizado_em=relatorio.finalizado_em,
                           finalizado_por=relatorio.finalizado_por, assinatura=relatorio.assinatura, atualizado_em=v.criado_em, atualizado_por=v.criado_por)
