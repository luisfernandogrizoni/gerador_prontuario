"""
Quadro de vagas da home.

Cada categoria tem um limite de vagas e só quem está com status "ativo" ocupa vaga. O limite de cada convênio
fica no cadastro de convênios (catalogo.py); as categorias do Particular (Social e Particular) têm limite fixo aqui.
Como os avisos, a ocupação não fica gravada: é contada a cada vez a partir dos dados.

Situação de cada categoria:
    disponivel   ocupadas < limite    (verde)
    lotada       ocupadas == limite   (verde)
    excedida     ocupadas > limite    (vermelho)
    sem_limite   limite ainda não definido (cinza)
"""

from collections import Counter

import catalogo
from modelos import Internacao, db
from prontuario import categoria_vaga, tipo_da_categoria

# Limite de vagas das categorias de quem paga (Particular), depois dos convênios na home.
# None = limite ainda não definido. Para mudar um limite, é só trocar o número.
LIMITES_FIXOS = {
    "Social": 5,
    "Social I": 2,
    "Social II": 3,
    "Particular": 1,
}


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def _vaga(categoria, ocupadas, limite):
    if limite is None:
        situacao, texto = "sem_limite", "Limite não definido"
    elif ocupadas > limite:
        situacao, texto = "excedida", f"{ocupadas - limite} acima do limite"
    elif ocupadas == limite:
        situacao, texto = "lotada", "Lotada"
    else:
        livres = limite - ocupadas
        situacao, texto = "disponivel", _plural(livres, "vaga livre", "vagas livres")
    # quanto da barra de progresso fica preenchida (a barra nunca passa de 100%)
    percentual = 0 if not limite else min(100, round(ocupadas * 100 / limite))
    if limite == 0 and ocupadas:
        percentual = 100
    return {"categoria": categoria, "ocupadas": ocupadas, "limite": limite,
            "situacao": situacao, "texto": texto, "percentual": percentual,
            "tipo": tipo_da_categoria(categoria)}


def gerar_vagas():
    ocupadas = Counter(
        categoria_vaga(convenio, valor or 0.0)
        for convenio, valor in db.session.execute(
            db.select(Internacao.convenio, Internacao.contribuicao_valor)
            .filter(Internacao.status == "ativo")))
    # primeiro os convênios (na ordem do cadastro): os ativos e os desativados que ainda têm gente internada
    linhas = [(c.nome_tela, c.vagas) for c in catalogo.atual().com_relatorio if c.ativo or ocupadas[c.nome_tela]]
    linhas += LIMITES_FIXOS.items()
    return [_vaga(categoria, ocupadas[categoria], limite) for categoria, limite in linhas]


def totais(vagas):
    """Soma de todas as categorias: ocupadas, limite e vagas livres.
    As vagas livres somam só o que sobra em cada categoria (uma vaga livre de Caps AD não serve
    para um particular), por isso uma categoria excedida não "tira" vaga das outras.
    Sem todos os limites definidos, `limite` e `livres` ficam None."""
    ocupadas = sum(v["ocupadas"] for v in vagas)
    if any(v["limite"] is None for v in vagas):
        return {"ocupadas": ocupadas, "limite": None, "livres": None}
    return {"ocupadas": ocupadas, "limite": sum(v["limite"] for v in vagas),
            "livres": sum(max(v["limite"] - v["ocupadas"], 0) for v in vagas)}
