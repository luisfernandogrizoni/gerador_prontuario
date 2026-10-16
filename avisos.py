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

import copia_externa
import servico_social
from banco import arquivo_ultimo_backup
from modelos import ENVELOPE_PENDENTE, AvisoDispensado, Internacao, Pessoa, db
from relatorios import hoje_no_brasil
from validacao import cpf_valido, fmt_cpf, normalizar_nome, so_digitos

# Depois da baixa, o prontuário em papel (envelope) tem este prazo para voltar da casa de acolhida
# ao escritório. Passou disso, o aviso fica vermelho: é hora de cobrar.
PRAZO_ENVELOPE_DIAS = 7
CATEGORIA_ENVELOPE = "Prontuário a receber da casa de acolhida"
CATEGORIA_REJEICAO = "Parecer da rejeição a escrever"          # rejeitado na triagem, e a assistente social ainda não finalizou o parecer
CATEGORIA_ACOLHIMENTO = "Acolhimento social a finalizar"        # a triagem já aconteceu e o acolhimento social não foi finalizado

# No servidor do escritório (servidor.py), o backup diário (backup.py) anota quando terminou. Passou deste
# prazo sem backup, a página inicial avisa. 3 dias cobrem um fim de semana prolongado com o computador desligado.
PRAZO_BACKUP = timedelta(days=3)
CATEGORIA_BACKUP = "Backup do banco"
# Cópia criptografada em pen-drives em rodízio (copia_externa.py): não configurada, pen-drive fora, hora de trocar, teste por fazer
CATEGORIA_BACKUP_EXTERNO = "Cópia externa do backup"
CATEGORIA_REDE = "Segurança da rede"             # o HTTPS ainda não está ligado, ou o http da rede local ainda não foi fechado (servidor.py, modos de rede)
CATEGORIA_CONTA = "Sua conta"                    # o que a própria pessoa ainda precisa fazer na segurança dela (contas.pendencias_da_conta)


@dataclass
class Aviso:
    categoria: str
    texto: str
    url: str          # onde resolver
    chave: str        # identifica o aviso para "Ciente"
    # ação extra, um botão que envia um formulário: {"rotulo", "url", "confirmar" (pergunta, opcional),
    # "campos" (campos ocultos), "principal" (botão cheio em vez de branco), "exige" (a permissão que a ação pede,
    # permissoes.py: quem não a tem não vê o botão)} — ex.: unificar cadastros, marcar o prontuário como recebido
    acao: dict | None = None
    etiqueta: tuple[str, str] | None = None   # (cor, texto) ao lado do aviso: cor = proximo | urgente | vencido
    dispensavel: bool = True                  # False = não tem "Ciente": só some quando resolvido
    rotulo_url: str = "Abrir ficha"           # o texto do botão que leva a `url`


def _ficha(internacao):
    return url_for("ficha", id=internacao.id)


def tempo_decorrido(dias):
    return "hoje" if dias == 0 else f"há {dias} dia{'' if dias == 1 else 's'}"


def gerar_avisos(pode_servico_social=False, da_conta=()):
    """`pode_servico_social`: quem olha é do Serviço Social (ou administrador); só para ele o aviso do acolhimento social
    leva direto ao formulário (os outros vão à ficha, onde veem se já foi feito, sem o conteúdo)."""
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
        triagem_ja_foi = i.status in ("em_admissao", "lista_espera") and i.data_triagem and i.data_triagem <= hoje_no_brasil()
        if i.status == "rejeitado" or triagem_ja_foi:       # (só aqui se olha o acolhimento: é uma consulta por registro)
            situacao = servico_social.estado(i.relatorio_social)
            aonde = url_for("relatorio_social", id=i.id) if pode_servico_social else _ficha(i) + "#acolhimento"
            if situacao == "finalizado":
                pass
            elif i.status == "rejeitado":
                avisos.append(Aviso(CATEGORIA_REJEICAO, f"{nome}: marcado como rejeitado na triagem. Falta o parecer do porquê (assistente social).",
                                    aonde, f"rejeicao:{i.id}", dispensavel=False))
            else:
                avisos.append(Aviso(CATEGORIA_ACOLHIMENTO,
                                    f"{nome}: triagem em {i.data_triagem.strftime('%d/%m/%Y')}, e o acolhimento social ainda não foi finalizado "
                                    f"({'em rascunho' if situacao else 'não iniciado'}).",
                                    aonde, f"acolhimento:{i.id}", dispensavel=False))
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
                      "confirmar": "Unificar os dois cadastros? As internações passam para um só cadastro.", "exige": "unificar"}))

    dispensados = set(db.session.execute(db.select(AvisoDispensado.chave)).scalars())
    avisos = [a for a in avisos if a.chave not in dispensados]
    avisos.extend(a for a in (_aviso_do_backup(),) if a)
    avisos.extend(_avisos_do_backup_externo())
    avisos.extend(_avisos_de_rede())
    avisos.extend(Aviso(CATEGORIA_CONTA, texto, url_for("seguranca"), chave, dispensavel=False, rotulo_url="Abrir Minha segurança") for chave, texto in da_conta)

    grupos = defaultdict(list)
    for a in avisos:
        grupos[a.categoria].append(a)
    # o backup, o envelope pendente e o acolhimento social são tarefas, não correções de cadastro: vêm primeiro
    tarefas = (CATEGORIA_CONTA, CATEGORIA_REDE, CATEGORIA_BACKUP, CATEGORIA_BACKUP_EXTERNO, CATEGORIA_ENVELOPE, CATEGORIA_REJEICAO, CATEGORIA_ACOLHIMENTO)
    return dict(sorted(grupos.items(), key=lambda g: (g[0] not in tarefas, g[0])))


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


def _avisos_de_rede():
    """Só no servidor do escritório (AVISAR_BACKUP=1, e o servidor.py diz o modo de rede em MODO_DE_REDE_ATUAL): enquanto o acesso é por http, ou
    enquanto o http da rede local segue aberto depois de ligar o HTTPS, a página inicial lembra (implantacao\\LEIA-ME.md, parte 5)."""
    if os.environ.get("AVISAR_BACKUP") != "1":
        return []
    modo = os.environ.get("MODO_DE_REDE_ATUAL")
    if modo == "http":
        texto = ("O sistema ainda é acessado sem HTTPS: a senha e as fichas trafegam sem criptografia pela rede do escritório. "
                 "Para ligar o HTTPS pelo Tailscale, veja implantacao\\LEIA-ME.md, parte 5.")
    elif modo == "misto":
        if os.environ.get("MANTER_HTTP_NA_REDE") == "1":      # a casa escolheu manter os dois acessos (configurar-https.ps1 -ManterOsDois)
            return []
        texto = ("O HTTPS está ligado, mas o http da rede local continua aberto. Quando todos os computadores e celulares usarem o endereço https, "
                 "feche o http (implantacao\\LEIA-ME.md, parte 5).")
    else:
        return []
    return [Aviso(CATEGORIA_REDE, texto, "", f"rede:{modo}", dispensavel=False)]


def _avisos_do_backup_externo():
    """Só no servidor do escritório (AVISAR_BACKUP=1), como o aviso do backup do dia: o que falta na cópia externa criptografada."""
    if os.environ.get("AVISAR_BACKUP") != "1":
        return []
    return [Aviso(CATEGORIA_BACKUP_EXTERNO, texto, "", chave, dispensavel=False)        # sem botão: o botão dos avisos é "Abrir ficha"
            for chave, _, texto in copia_externa.pendencias(current_app.instance_path)]


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
                       "campos": {"situacao": "recebido", "voltar": "home"}, "principal": True, "exige": "baixa"})
