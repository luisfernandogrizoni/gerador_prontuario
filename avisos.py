"""
Quadro de avisos da home.

Os avisos não ficam gravados: são calculados a cada vez a partir dos dados.
Assim, quando alguém corrige o CPF ou preenche a data que faltava, o aviso
some sozinho. Quem quiser tirar um aviso sem corrigir (ex.: "são pessoas
diferentes") clica em "Ciente" — isso grava a chave em avisos_dispensados.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from flask import url_for

from modelos import AvisoDispensado, Internacao, Pessoa, db
from validacao import cpf_valido, fmt_cpf, normalizar_nome, so_digitos


@dataclass
class Aviso:
    categoria: str
    texto: str
    url: str          # onde resolver
    chave: str        # identifica o aviso para "Ciente"
    acao: dict | None = None  # ação extra (ex.: unificar cadastros)


def _ficha(internacao):
    return url_for("ficha", id=internacao.id)


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
                      "url": url_for("unificar_pessoas", manter=manter.id, remover=outro.id)}))

    dispensados = set(db.session.execute(db.select(AvisoDispensado.chave)).scalars())
    avisos = [a for a in avisos if a.chave not in dispensados]

    grupos = defaultdict(list)
    for a in avisos:
        grupos[a.categoria].append(a)
    return dict(sorted(grupos.items()))
