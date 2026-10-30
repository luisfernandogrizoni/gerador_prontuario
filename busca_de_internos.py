"""
A lista de internos: busca, filtros, ordem e páginas feitos aqui, no servidor (GET /api/internos/busca).

Antes, a página baixava TODOS os internos a cada 30 segundos e filtrava no navegador: com a casa crescendo, ficaria cada vez mais pesada (o servidor
montando milhares de registros, a rede levando-os e o navegador desenhando milhares de linhas). Agora o navegador pede só a página que está vendo.

Como é feito (sem coluna nova nem migração): uma consulta leve traz, de todos os internos, só o que a busca, os filtros e a ordem usam (colunas, não
objetos); o filtro e a ordem rodam em Python, onde "José" = "jose" e a conta é a mesma no SQLite e no Postgres; só a página pedida é carregada
inteira (`Internacao.para_lista`), com a pessoa, as parcelas e o acolhimento numa consulta cada, e não uma por linha.

A busca (várias palavras, em qualquer ordem, todas precisam aparecer; sem acento e sem diferença de maiúsculas):
  - letras: nome, mãe, responsável, parentesco, categoria, convênio, cidade e situação ("inativo", "desistência"...);
  - números: CPF, RG, cartão SUS, CPF do responsável e telefones, com ou sem pontuação ("123.456" acha "12345678900");
  - "#123" acha o registro de número 123.
Sem ordem escolhida, quem tem o nome começando pelo que foi digitado vem antes de quem só tem a mãe ou o responsável com aquele nome.
"""

import math
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import extract
from sqlalchemy.orm import joinedload, selectinload

import catalogo
from modelos import STATUS_INTERNACAO, Internacao, Pessoa, db, status_texto
from prontuario import categoria_efetiva, previsao_termino
from validacao import normalizar_nome, so_digitos

TAMANHOS = (25, 50, 100)
TAMANHO_PADRAO = 50
LIMITE_DE_TODOS = 2000        # "Todos" serve para imprimir a lista; tem teto para uma lista enorme não travar o servidor nem o navegador
TAMANHO_DA_BUSCA = 100        # caracteres da busca que valem
SEM_DATA = "sem"              # o valor do filtro "ano de início" para quem não tem data de início
_SO_DIGITOS = re.compile(r"\D+")


@dataclass
class Linha:
    """O que a busca, os filtros e a ordem enxergam de um interno."""
    id: int
    status: str
    status_txt: str
    categoria: str
    valor: float
    inicio: date | None
    previsao: date | None
    termino: date | None
    responsavel: str
    nome: str
    nome_norm: str
    texto: str
    numeros: tuple


def _linhas():
    """Todos os internos (ativos e inativos), do início mais recente para o mais antigo: a ordem de quando nenhuma é escolhida."""
    colunas = (Internacao.id, Internacao.status, Internacao.motivo, Internacao.convenio, Internacao.contribuicao_valor, Internacao.inicio,
               Internacao.tratamento_ate, Internacao.termino, Internacao.resp_nome, Internacao.parentesco, Internacao.resp_cpf,
               Pessoa.nome, Pessoa.cpf, Pessoa.rg, Pessoa.cartao_sus, Pessoa.mae, Pessoa.cidade, Pessoa.contato1, Pessoa.contato2, Pessoa.contato3)
    consulta = (db.select(*colunas).join(Pessoa, Internacao.pessoa_id == Pessoa.id)
                .where(Internacao.status.in_(STATUS_INTERNACAO), Internacao.excluido_em.is_(None), Pessoa.excluido_em.is_(None))
                .order_by(Internacao.inicio.desc().nulls_last(), Internacao.id.desc()))
    linhas = []
    categorias = {}                                       # (convênio, valor) -> categoria: a conta se repete para quase todos
    for r in db.session.execute(consulta):
        situacao = status_texto(r.status, r.motivo)
        categoria = categorias.get((r.convenio, r.contribuicao_valor))
        if categoria is None:
            categoria = categorias[(r.convenio, r.contribuicao_valor)] = categoria_efetiva(r.convenio, r.contribuicao_valor or 0.0)
        letras = " | ".join(p for p in (r.nome, r.mae, r.resp_nome, r.parentesco, categoria, r.convenio, r.cidade, situacao) if p)
        numeros = tuple(d for d in (_SO_DIGITOS.sub("", x or "") for x in (r.cpf, r.rg, r.cartao_sus, r.resp_cpf, r.contato1, r.contato2, r.contato3)) if d)
        linhas.append(Linha(r.id, r.status, situacao, categoria, r.contribuicao_valor or 0.0, r.inicio, previsao_termino(r.inicio, r.tratamento_ate),
                            r.termino, r.resp_nome or "", r.nome or "", normalizar_nome(r.nome), normalizar_nome(letras), numeros))
    return linhas


# ------------------------------------------------------------------ busca
def termos_da_busca(q):
    """'maria  Silva 123.456 #7' -> [('txt', 'maria'), ('txt', 'silva'), ('num', '123456', '123.456'), ('id', 7)]"""
    termos = []
    for palavra in normalizar_nome((q or "")[:TAMANHO_DA_BUSCA]).split():
        if palavra.startswith("#") and palavra[1:].isdigit():
            termos.append(("id", int(palavra[1:])))
        elif any(c.isdigit() for c in palavra):
            termos.append(("num", so_digitos(palavra), palavra))
        else:
            termos.append(("txt", palavra))
    return termos


def _casa(linha, termos):
    for termo in termos:
        if termo[0] == "id":
            ok = linha.id == termo[1]
        elif termo[0] == "num":
            ok = any(termo[1] in n for n in linha.numeros) or termo[2] in linha.texto
        else:
            ok = termo[1] in linha.texto
        if not ok:
            return False
    return True


def _relevancia(linha, termos):
    """0 = o nome começa, em alguma palavra, com cada palavra buscada; 1 = o nome só contém; 2 = achou na mãe, no responsável etc."""
    palavras = [t[1] for t in termos if t[0] == "txt"]
    if not palavras:
        return 0
    do_nome = linha.nome_norm.split()
    if all(any(p.startswith(w) for p in do_nome) for w in palavras):
        return 0
    return 1 if all(w in linha.nome_norm for w in palavras) else 2


# ------------------------------------------------------------------ ordem
ORDENS = {
    "nome": lambda l: l.nome_norm,
    "categoria": lambda l: normalizar_nome(l.categoria),
    "valor": lambda l: l.valor,
    "inicio": lambda l: l.inicio,
    "previsao": lambda l: l.previsao,
    "termino": lambda l: l.termino,
    "responsavel": lambda l: normalizar_nome(l.responsavel),
    "status_txt": lambda l: normalizar_nome(l.status_txt),
}


def _ordenar(linhas, chave, crescente):
    """Quem não tem o valor (data em branco, sem responsável) fica sempre no fim, nas duas direções; quem empata mantém a ordem de antes."""
    valor = ORDENS[chave]
    com = [l for l in linhas if valor(l) not in (None, "")]
    sem = [l for l in linhas if valor(l) in (None, "")]
    com.sort(key=valor, reverse=not crescente)
    return com + sem


# ------------------------------------------------------------------ opções dos filtros
def opcoes_dos_filtros():
    """O que a página oferece nos seletores: as categorias (os convênios que dão vaga e as faixas do particular) e os anos de início que existem."""
    cadastro = catalogo.atual()
    categorias = [c.nome_tela for c in cadastro.convenios if c.gratuito] + [c for c in catalogo.CATEGORIAS_RESERVADAS if c != "A definir"] + ["A definir"]
    anos = db.session.execute(db.select(extract("year", Internacao.inicio)).where(Internacao.status.in_(STATUS_INTERNACAO), Internacao.inicio.is_not(None))
                              .distinct()).scalars().all()
    sem_data = db.session.execute(db.select(Internacao.id).where(Internacao.status.in_(STATUS_INTERNACAO), Internacao.inicio.is_(None)).limit(1)).first()
    return {"categorias": categorias, "anos": sorted({int(a) for a in anos if a}, reverse=True), "sem_data": sem_data is not None}


# ------------------------------------------------------------------ a consulta
def _inteiro(valor, padrao=None):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def consultar(args):
    """`args`: q (busca), situacao (ativo | inativo | vazio = todos), categoria, ano (um ano ou 'sem'), ordem (uma chave de ORDENS) e dir (asc | desc),
    por (25, 50, 100 ou 'todos'), pagina (a partir de 1) e foco (o registro que precisa aparecer: devolve a página em que ele está).
    Devolve {itens, total, pagina, paginas, por, de, ate, contagens}; `contagens` é por situação, já com a busca e os outros filtros aplicados."""
    termos = termos_da_busca(args.get("q"))
    situacao = args.get("situacao") if args.get("situacao") in STATUS_INTERNACAO else ""
    categoria = args.get("categoria") or ""
    ano = args.get("ano") or ""
    chave = args.get("ordem") if args.get("ordem") in ORDENS else ""
    por = LIMITE_DE_TODOS if args.get("por") == "todos" else (_inteiro(args.get("por")) if _inteiro(args.get("por")) in TAMANHOS else TAMANHO_PADRAO)

    linhas = _linhas()
    if termos:
        linhas = [l for l in linhas if _casa(l, termos)]
    if categoria:
        linhas = [l for l in linhas if l.categoria == categoria]
    if ano == SEM_DATA:
        linhas = [l for l in linhas if l.inicio is None]
    elif _inteiro(ano) is not None:
        linhas = [l for l in linhas if l.inicio is not None and l.inicio.year == _inteiro(ano)]
    contagens = {s: sum(1 for l in linhas if l.status == s) for s in STATUS_INTERNACAO}
    contagens["todos"] = len(linhas)

    if situacao:
        linhas = [l for l in linhas if l.status == situacao]
    if chave:
        linhas = _ordenar(linhas, chave, args.get("dir") != "desc")
    elif termos:
        linhas = sorted(linhas, key=lambda l: _relevancia(l, termos))        # estável: dentro de cada grupo vale a ordem de antes

    total = len(linhas)
    paginas = max(1, math.ceil(total / por))
    pagina = _inteiro(args.get("pagina"), 1)
    foco = _inteiro(args.get("foco"))
    if foco is not None:
        posicao = next((n for n, l in enumerate(linhas) if l.id == foco), None)
        if posicao is not None:
            pagina = posicao // por + 1
    pagina = min(max(pagina, 1), paginas)
    da_pagina = linhas[(pagina - 1) * por: pagina * por]

    itens = []
    if da_pagina:
        ids = [l.id for l in da_pagina]
        carregados = db.session.execute(
            db.select(Internacao).where(Internacao.id.in_(ids))
            .options(joinedload(Internacao.pessoa), selectinload(Internacao.parcelas), selectinload(Internacao.relatorio_social))).scalars().all()
        por_id = {i.id: i for i in carregados}
        itens = [por_id[i].para_lista() for i in ids if i in por_id]
    de = (pagina - 1) * por + 1 if total else 0
    return {"itens": itens, "total": total, "pagina": pagina, "paginas": paginas, "por": por if por != LIMITE_DE_TODOS else "todos",
            "de": de, "ate": de + len(itens) - 1 if itens else 0, "contagens": contagens}
