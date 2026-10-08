"""
Quadro de vagas da home.

Cada categoria tem um limite de vagas e só quem está com status "ativo" ocupa vaga.
Como os avisos, a ocupação não fica gravada: é contada a cada vez a partir dos dados.

Situação de cada categoria:
    disponivel   ocupadas < limite    (verde)
    lotada       ocupadas == limite   (verde)
    excedida     ocupadas > limite    (vermelho)
    sem_limite   limite ainda não definido (cinza)
"""

from collections import Counter

from modelos import Internacao, db
from prontuario import categoria_vaga

# Limite de vagas de cada categoria, na ordem em que aparecem na home.
# None = limite ainda não definido. Para mudar um limite, é só trocar o número.
LIMITES = {
    "CAPS AD": None,
    "Prefeitura Tarumã": None,
    "Particular": None,
    "Social Parcial II": None,
    "Social Parcial I": None,
    "Social Total": None,
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
    return {"categoria": categoria, "ocupadas": ocupadas, "limite": limite,
            "situacao": situacao, "texto": texto}


def gerar_vagas():
    ocupadas = Counter(
        categoria_vaga(convenio, valor or 0.0)
        for convenio, valor in db.session.execute(
            db.select(Internacao.convenio, Internacao.contribuicao_valor)
            .filter(Internacao.status == "ativo")))
    return [_vaga(categoria, ocupadas[categoria], limite) for categoria, limite in LIMITES.items()]
