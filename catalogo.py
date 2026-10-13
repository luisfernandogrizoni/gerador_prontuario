"""
Catálogo de convênios: o que o sistema sabe sobre cada convênio (nome, vagas, cor, se é gratuito).

Os convênios ficam no banco (tabela `convenios`, editada em Cadastros > Convênios) e este módulo os entrega
ao resto do sistema como valores simples. As regras de classificação (prontuario.py), o quadro de vagas
(vagas.py), os relatórios (relatorios.py) e os formulários perguntam aqui em vez de usar listas escritas no código.

`atual()` lê o banco UMA vez por requisição (guarda em `flask.g`), então uma mudança no cadastro vale na
requisição seguinte, em qualquer processo do servidor. Fora de uma requisição (testes, scripts) devolve o padrão
de fábrica: os três convênios com que o sistema nasceu.
"""

from dataclasses import dataclass

from flask import g, has_app_context

# Convênios de fábrica (o que o cadastro traz na primeira vez). `nome` é o texto guardado em cada internação.
# Em convênios gratuitos a contribuição é sempre R$ 0,00 e a categoria é o próprio convênio; o "Particular"
# classifica pelo valor pago (Social, Social I, Social II ou Particular).
CONVENIOS_DE_FABRICA = [
    # nome, nome na tela, endereço (slug), gratuito, vagas, cor
    ("CAPS AD", "Caps AD", "caps-ad", True, 9, "caps"),
    ("Prefeitura Tarumã", "Prefeitura Tarumã", "taruma", True, 10, "taruma"),
    ("Particular", "Particular", "particular", False, None, "particular"),
]

# Níveis de acesso de fábrica, do que tem mais acesso para o que tem menos (a cascata). Podem ser trocados, reordenados
# e ampliados em Cadastros > Níveis de acesso.
NIVEIS_DE_FABRICA = ["Administrador", "Operador", "Consulta"]

# Cores que um convênio pode ter nas telas (classe CSS em base.html). A ordem é a da escolha automática.
CORES = [("caps", "Vermelho"), ("taruma", "Laranja"), ("verde", "Verde"), ("roxo", "Roxo"), ("rosa", "Rosa"),
         ("turquesa", "Turquesa"), ("amarelo", "Amarelo"), ("marrom", "Marrom")]

# Nomes que uma categoria já usa nas telas: um convênio não pode ter nome na tela igual a eles
CATEGORIAS_RESERVADAS = ["A definir", "Social", "Social I", "Social II", "Particular"]

# Cor das categorias que não são convênios (Social vai do azul acinzentado mais escuro, que contribui menos,
# ao mais claro, que contribui mais; Particular é azul bebê)
TIPO_DAS_CATEGORIAS = {"Social": "social", "Social I": "social-1", "Social II": "social-2", "Particular": "particular"}


@dataclass(frozen=True)
class ConvenioDef:
    nome: str
    nome_tela: str
    slug: str
    gratuito: bool
    vagas: int | None
    cor: str
    ativo: bool = True
    ordem: int = 0


class Catalogo:
    def __init__(self, convenios):
        self.convenios = tuple(convenios)
        self._por_nome = {c.nome: c for c in self.convenios}
        self._por_slug = {c.slug: c for c in self.convenios}

    # ------------------------------------------------------------ consultas
    def existe(self, nome):
        return nome in self._por_nome

    def convenio(self, nome):
        return self._por_nome.get(nome)

    def por_slug(self, slug):
        return self._por_slug.get(slug)

    def e_gratuito(self, nome):
        c = self._por_nome.get(nome)
        return bool(c and c.gratuito)

    def nome_na_tela(self, nome):
        c = self._por_nome.get(nome)
        return c.nome_tela if c else nome

    def tipo_da_categoria(self, categoria):
        """Classe de cor de uma categoria (nome como aparece nas telas), ou "outro"."""
        if categoria in TIPO_DAS_CATEGORIAS:
            return TIPO_DAS_CATEGORIAS[categoria]
        for c in self.convenios:
            if c.gratuito and c.nome_tela == categoria:
                return c.cor
        return "outro"

    @property
    def gratuitos(self):
        """Nomes guardados dos convênios em que a contribuição é sempre R$ 0,00."""
        return [c.nome for c in self.convenios if c.gratuito]

    @property
    def com_relatorio(self):
        """Convênios gratuitos: têm vagas próprias, relatório de internos ativos e coluna no relatório anual."""
        return [c for c in self.convenios if c.gratuito]

    def para_escolher(self, atual=""):
        """(nome guardado, nome na tela) para o select dos formulários: os ativos, mais o `atual` se ele foi desativado."""
        return [(c.nome, c.nome_tela) for c in self.convenios if c.ativo or c.nome == atual]


PADRAO = Catalogo(ConvenioDef(nome, tela, slug, gratuito, vagas, cor, True, ordem)
                  for ordem, (nome, tela, slug, gratuito, vagas, cor) in enumerate(CONVENIOS_DE_FABRICA, 1))


def _do_banco():
    from modelos import Convenio, db
    try:
        linhas = db.session.execute(db.select(Convenio).order_by(Convenio.ordem, Convenio.id)).scalars().all()
    except Exception:           # tabela ainda não existe (primeira subida, antes da migração)
        db.session.rollback()
        return PADRAO
    if not linhas:
        return PADRAO
    return Catalogo(ConvenioDef(c.nome, c.nome_tela, c.slug, c.gratuito, c.vagas, c.cor, c.ativo, c.ordem) for c in linhas)


def atual():
    """O catálogo desta requisição (o padrão de fábrica fora de uma requisição)."""
    if not has_app_context():
        return PADRAO
    if "catalogo" not in g:
        g.catalogo = _do_banco()
    return g.catalogo


def esquecer():
    """Depois de alterar o cadastro dentro da mesma requisição: a próxima consulta lê o banco de novo."""
    if has_app_context():
        g.pop("catalogo", None)
