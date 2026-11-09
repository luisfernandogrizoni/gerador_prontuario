"""
Conferência dos registros IMPORTADOS com o prontuário físico (a tela "Para conferir").

Os registros que entraram por importar_historico.py (pastas e planilhas antigas) são dados parciais: faltam CPF, datas, convênio... Quem está com a pasta de
papel na mão abre "Para conferir", escolhe uma pessoa, completa o que o papel mostra e marca o registro como **conferido**. Conferir é um ato explícito: o
sistema não decide sozinho que um registro está completo (um papel pode simplesmente não ter a informação).

  * A fila é a dos importados que ainda não foram conferidos (`Internacao.origem` preenchida e `conferido_em` vazio), do mais recente para o mais antigo
    (pela data de saída ou de entrada; sem data, pelo ano que a pasta de origem diz; "anos anteriores" por último), e dentro do ano por nome.
  * "O que falta" é só um guia (CPF, nascimento, datas, motivo, convênio, endereço, mãe, responsável); não impede de marcar como conferido.
  * Os filtros (busca, pasta de origem, o que falta, a conferir/conferidos) viajam com a pessoa de uma ficha para a seguinte ("Salvar e ir para o próximo").
  * Quem conferiu e quando ficam no registro (`conferido_por`, `conferido_em`) e na trilha de auditoria. Dá para reabrir a conferência.
"""

import re
from datetime import datetime

from sqlalchemy.orm import selectinload

from modelos import Internacao, db
from validacao import normalizar_nome

TAMANHO_DA_PAGINA = 50

# (como o campo se chama aqui, como aparece na tela)
FALTAS = (("cpf", "CPF"), ("nascimento", "nascimento"), ("inicio", "data de entrada"), ("termino", "data de saída"), ("motivo", "motivo da saída"),
          ("convenio", "convênio"), ("endereco", "endereço"), ("mae", "nome da mãe"), ("resp_nome", "responsável"))
SITUACOES = (("a_conferir", "A conferir"), ("conferidos", "Já conferidos"), ("todos", "Todos os importados"))


def faltas(internacao):
    """[(chave, rótulo)] do que está em branco neste registro importado."""
    p = internacao.pessoa
    valor = {"cpf": p.cpf, "nascimento": p.nascimento, "endereco": p.endereco, "mae": p.mae, "inicio": internacao.inicio, "termino": internacao.termino,
             "motivo": internacao.motivo, "convenio": internacao.convenio, "resp_nome": internacao.resp_nome}
    return [(k, rotulo) for k, rotulo in FALTAS if not valor[k]]


def pasta_de_origem(internacao):
    """A primeira parte da origem ('Ex-Residentes / Saíram em 2024'), o que separa as pastas na tela."""
    return internacao.origem_txt.split(";")[0].strip()


def _ano(internacao):
    """O ano que serve para ordenar: o da saída ou da entrada, senão o maior ano que a origem cita, senão 0 ('anos anteriores')."""
    for d in (internacao.termino, internacao.inicio):
        if d:
            return d.year
    anos = [int(a) for a in re.findall(r"\b(?:19|20)\d{2}\b", internacao.origem_txt)]
    return max(anos) if anos else 0


def chave_de_ordem(internacao):
    return (-_ano(internacao), normalizar_nome(internacao.pessoa.nome), internacao.id)


# ------------------------------------------------------------------ filtros
def filtros_de(fonte, prefixo=""):
    """Os filtros da tela, vindos da querystring (prefixo "") ou dos campos escondidos de um formulário (prefixo "c_")."""
    pega = lambda nome: (fonte.get(prefixo + nome) or "").strip()
    situacao = pega("situacao")
    falta = pega("falta")
    return {"q": pega("q")[:80], "origem": pega("origem")[:120], "falta": falta if falta in {k for k, _ in FALTAS} else "",
            "situacao": situacao if situacao in {k for k, _ in SITUACOES} else "a_conferir"}


def como_argumentos(filtros):
    """Os filtros como argumentos de url_for (só os que não são o padrão)."""
    return {k: v for k, v in filtros.items() if v and not (k == "situacao" and v == "a_conferir")}


def _importados():
    return db.session.execute(db.select(Internacao).filter(Internacao.origem != "").options(selectinload(Internacao.pessoa))).scalars().all()


def _passa(internacao, filtros, termos):
    if filtros["situacao"] == "a_conferir" and internacao.conferido_em:
        return False
    if filtros["situacao"] == "conferidos" and not internacao.conferido_em:
        return False
    if filtros["origem"] and pasta_de_origem(internacao) != filtros["origem"]:
        return False
    if filtros["falta"] and filtros["falta"] not in {k for k, _ in faltas(internacao)}:
        return False
    if termos:
        nome = normalizar_nome(internacao.pessoa.nome)
        return all(t in nome for t in termos)
    return True


def fila(filtros):
    termos = normalizar_nome(filtros["q"]).split()
    return sorted((i for i in _importados() if _passa(i, filtros, termos)), key=chave_de_ordem)


def consultar(filtros, pagina=1):
    """A página pedida da fila: {itens, total, pagina, paginas}."""
    todos = fila(filtros)
    paginas = max(1, -(-len(todos) // TAMANHO_DA_PAGINA))
    pagina = min(max(1, pagina), paginas)
    parte = todos[(pagina - 1) * TAMANHO_DA_PAGINA: pagina * TAMANHO_DA_PAGINA]
    itens = [{"id": i.id, "nome": i.pessoa.nome, "origem": pasta_de_origem(i), "entrada": i.inicio, "saida": i.termino, "motivo": i.motivo, "faltas": faltas(i),
              "conferido_em": i.conferido_em, "conferido_por": i.conferido_por} for i in parte]
    return {"itens": itens, "total": len(todos), "pagina": pagina, "paginas": paginas}


def origens():
    """As pastas de origem que existem entre os importados (para o filtro), da mais recente para a mais antiga."""
    vistas = {}
    for i in _importados():
        vistas.setdefault(pasta_de_origem(i), 0)
        vistas[pasta_de_origem(i)] = max(vistas[pasta_de_origem(i)], _ano(i))
    return sorted(vistas, key=lambda o: (-vistas[o], o))


def progresso():
    """(quantos importados, quantos já conferidos)."""
    total = db.session.execute(db.select(db.func.count(Internacao.id)).filter(Internacao.origem != "")).scalar() or 0
    feitos = db.session.execute(db.select(db.func.count(Internacao.id)).filter(Internacao.origem != "", Internacao.conferido_em.isnot(None))).scalar() or 0
    return total, feitos


def quantos_a_conferir():
    return db.session.execute(db.select(db.func.count(Internacao.id)).filter(Internacao.origem != "", Internacao.conferido_em.is_(None))).scalar() or 0


def proxima(atual, filtros):
    """Quem vem depois de `atual` na fila dos que ainda faltam conferir (com os mesmos filtros), ou None. Funciona mesmo que `atual` acabe de sair da fila."""
    ref = chave_de_ordem(atual)
    filtros = {**filtros, "situacao": "a_conferir"}
    for i in fila(filtros):
        if i.id != atual.id and chave_de_ordem(i) > ref:
            return i
    return None


# ------------------------------------------------------------------ marcar
def marcar(internacao, usuario, conferido=True):
    internacao.conferido_em = datetime.now() if conferido else None
    internacao.conferido_por = (usuario or "")[:50] if conferido else ""
    db.session.commit()
