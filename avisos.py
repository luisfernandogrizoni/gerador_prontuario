"""
Quadro de avisos da home.

Os avisos não ficam gravados: são calculados a cada vez a partir dos dados.
Assim, quando alguém corrige o CPF ou preenche a data que faltava, o aviso
some sozinho. Quem quiser tirar um aviso sem corrigir (ex.: "são pessoas
diferentes") clica em "Ciente" — isso grava a chave em avisos_dispensados.
"""

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from flask import current_app, url_for

import rejeicao
from banco import arquivo_ultimo_backup
from modelos import ENVELOPE_PENDENTE, AvisoDispensado, Internacao, Pessoa, db
from relatorios import hoje_no_brasil
from validacao import cpf_valido, fmt_cpf, normalizar_nome, so_digitos

# Depois da baixa, o prontuário em papel (envelope) tem este prazo para voltar da casa de acolhida
# ao escritório. Passou disso, o aviso fica vermelho: é hora de cobrar.
PRAZO_ENVELOPE_DIAS = 7
CATEGORIA_ENVELOPE = "Prontuário a receber da casa de acolhida"
CATEGORIA_REJEICAO = "Relatório de rejeição a escrever"      # a assistente social ainda não escreveu o porquê da rejeição

# No servidor do escritório (servidor.py), o backup diário (backup.py) anota quando terminou. Passou deste
# prazo sem backup, a página inicial avisa. 3 dias cobrem um fim de semana prolongado com o computador desligado.
PRAZO_BACKUP = timedelta(days=3)
CATEGORIA_BACKUP = "Backup do banco"


@dataclass
class Aviso:
    categoria: str
    texto: str
    url: str          # onde resolver
    chave: str        # identifica o aviso para "Ciente"
    # ação extra, um botão que envia um formulário: {"rotulo", "url", "confirmar" (pergunta, opcional),
    # "campos" (campos ocultos), "principal" (botão cheio em vez de branco)} — ex.: unificar cadastros,
    # marcar o prontuário como recebido
    acao: dict | None = None
    etiqueta: tuple[str, str] | None = None   # (cor, texto) ao lado do aviso: cor = proximo | urgente | vencido
    dispensavel: bool = True                  # False = não tem "Ciente": só some quando resolvido


def _ficha(internacao):
    return url_for("ficha", id=internacao.id)


def tempo_decorrido(dias):
    return "hoje" if dias == 0 else f"há {dias} dia{'' if dias == 1 else 's'}"


def gerar_avisos():
    avisos = []
    pessoas = db.session.execute(db.select(Pessoa)).scalars().all()
    internacoes = db.session.execute(db.select(Internacao)).scalars().all()

    for p in pessoas:
        ultima = p.ultima_internacao
        if not ultima:
            continue
        if p.cpf and not cpf_valido(p.cpf):
            avisos.append(Aviso("CPF do acolhido inválido",
                                f"{p.nome}: CPF {fmt_cpf(p.cpf)} não confere.",
                                _ficha(ultima), f"cpf:{p.id}:{p.cpf}"))
        for campo in ("contato1", "contato2", "contato3"):
            tel = getattr(p, campo)
            if tel and len(so_digitos(tel)) not in (10, 11):
                avisos.append(Aviso("Telefone fora do padrão",
                                    f"{p.nome}: {tel} (sem DDD ou com dígitos a mais).",
                                    _ficha(ultima), f"tel:{p.id}:{tel}"))

    # o mais antigo (o que está esperando há mais tempo) no topo da lista
    pendentes = sorted((i for i in internacoes if i.status == "inativo" and i.envelope == ENVELOPE_PENDENTE),
                       key=lambda i: (i.termino or date.max, i.id))
    avisos.extend(_aviso_do_envelope(i, hoje_no_brasil()) for i in pendentes)

    for i in internacoes:
        nome = i.pessoa.nome
        if i.resp_cpf and not cpf_valido(i.resp_cpf):
            avisos.append(Aviso("CPF do responsável inválido",
                                f"{nome}: CPF de {i.resp_nome or 'responsável'} ({fmt_cpf(i.resp_cpf)}) não confere.",
                                _ficha(i), f"respcpf:{i.id}:{i.resp_cpf}"))
        if i.status == "ativo" and not i.inicio:
            avisos.append(Aviso("Interno ativo sem data de internação",
                                f"{nome}: preencher a data de internação.",
                                _ficha(i), f"seminicio:{i.id}"))
        if i.status == "inativo" and not i.termino:
            avisos.append(Aviso("Inativo sem data de saída",
                                f"{nome}: saída por {i.motivo or 'motivo não informado'}, sem data.",
                                _ficha(i), f"semtermino:{i.id}"))
        if i.status == "desistiu" and i.inicio:
            avisos.append(Aviso("Desistência com internação efetiva",
                                f"{nome}: está como desistência na triagem, mas tem internação efetiva em "
                                f"{i.inicio.strftime('%d/%m/%Y')}"
                                + (f" e saída em {i.termino.strftime('%d/%m/%Y')}" if i.termino else "")
                                + ". Se ele chegou a ficar na casa, o certo é Inativo (Desistência).",
                                _ficha(i), f"desistinicio:{i.id}"))
        if i.status == "rejeitado" and not rejeicao.preenchido(i.rejeicao):
            avisos.append(Aviso(CATEGORIA_REJEICAO, f"{nome}: marcado como rejeitado na triagem. Falta o relatório do porquê (assistente social).",
                                url_for("relatorio_de_rejeicao", id=i.id), f"rejeicao:{i.id}", dispensavel=False))
        if (i.status in ("em_admissao", "lista_espera") and i.internacao_agendada
                and i.internacao_agendada < date.today()):
            avisos.append(Aviso("Internação agendada já passou",
                                f"{nome}: internação estava agendada para "
                                f"{i.internacao_agendada.strftime('%d/%m/%Y')} e ele segue em "
                                f"{'admissão' if i.status == 'em_admissao' else 'lista de espera'}. "
                                "Admitir, reagendar ou marcar desistência.",
                                url_for("editar_internacao", id=i.id), f"agendavencida:{i.id}:{i.internacao_agendada}"))

    # mesmo nome em cadastros diferentes
    por_nome = defaultdict(list)
    for p in pessoas:
        por_nome[normalizar_nome(p.nome)].append(p)
    for grupo in por_nome.values():
        if len(grupo) < 2:
            continue
        grupo.sort(key=lambda p: (not p.cpf, p.id))  # quem tem CPF primeiro
        manter = grupo[0]
        for outro in grupo[1:]:
            avisos.append(Aviso(
                "Possível cadastro duplicado",
                f"{manter.nome}: cadastro {manter.id} ({fmt_cpf(manter.cpf) or 'sem CPF'}) "
                f"e cadastro {outro.id} ({fmt_cpf(outro.cpf) or 'sem CPF'}).",
                _ficha(outro.ultima_internacao) if outro.ultima_internacao else "#",
                f"dup:{manter.id}:{outro.id}",
                acao={"rotulo": f"Unificar no cadastro {manter.id}",
                      "url": url_for("unificar_pessoas", manter=manter.id, remover=outro.id),
                      "confirmar": "Unificar os dois cadastros? As internações passam para um só cadastro."}))

    dispensados = set(db.session.execute(db.select(AvisoDispensado.chave)).scalars())
    avisos = [a for a in avisos if a.chave not in dispensados]
    avisos.extend(a for a in (_aviso_do_backup(),) if a)

    grupos = defaultdict(list)
    for a in avisos:
        grupos[a.categoria].append(a)
    # o backup, o envelope pendente e o relatório de rejeição são tarefas, não correções de cadastro: vêm primeiro
    return dict(sorted(grupos.items(), key=lambda g: (g[0] not in (CATEGORIA_BACKUP, CATEGORIA_ENVELOPE, CATEGORIA_REJEICAO), g[0])))


def _aviso_do_backup():
    """Só no servidor do escritório (AVISAR_BACKUP=1): confere se o backup diário continua rodando."""
    if os.environ.get("AVISAR_BACKUP") != "1":
        return None
    try:
        ultimo = datetime.fromisoformat(arquivo_ultimo_backup(current_app.instance_path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        texto = "Nenhum backup do banco foi feito ainda. Confira a tarefa de backup do Windows (veja implantacao/LEIA-ME.md)."
    else:
        if datetime.now() - ultimo <= PRAZO_BACKUP:
            return None
        texto = (f"O último backup do banco foi em {ultimo:%d/%m/%Y %H:%M}. "
                 "Confira a tarefa de backup do Windows e o disco de destino (veja implantacao/LEIA-ME.md).")
    return Aviso(CATEGORIA_BACKUP, texto, "", "backup", dispensavel=False)


def dias_de_espera(internacao, hoje=None):
    """Há quantos dias o prontuário de quem recebeu baixa espera na casa de acolhida, contando da
    data da saída (None = sem data de saída) — e se já passou do prazo."""
    if not internacao.termino:
        return None, False
    dias = max(((hoje or hoje_no_brasil()) - internacao.termino).days, 0)
    return dias, dias > PRAZO_ENVELOPE_DIAS


def _aviso_do_envelope(i, hoje):
    """Quem recebeu baixa e cujo prontuário em papel ainda não voltou da casa de acolhida."""
    dias, atrasado = dias_de_espera(i, hoje)
    saida = f"saída em {i.termino.strftime('%d/%m/%Y')} ({i.motivo or 'motivo não informado'})" if i.termino else "sem data de saída"
    texto = (f"{i.pessoa.nome}: {saida}. O prontuário ainda não voltou ao escritório"
             + (": cobrar a casa de acolhida." if atrasado else "."))
    etiqueta = None if dias is None else ("vencido" if atrasado else "proximo", tempo_decorrido(dias))
    return Aviso(CATEGORIA_ENVELOPE, texto, _ficha(i), f"envelope:{i.id}", etiqueta=etiqueta, dispensavel=False,
                 acao={"rotulo": "Chegou ao escritório", "url": url_for("registrar_envelope", id=i.id),
                       "campos": {"situacao": "recebido", "voltar": "home"}, "principal": True})
