"""
Escreve do jeito padrão os nomes e endereços que já estavam gravados em maiúsculas (ou todos em minúsculas): FULANO FICTICIO DE TAL -> Fulano Ficticio
de Tal. O que for gravado daqui em diante já passa por essa regra (validacao.py); este script cuida do que foi digitado antes.

    python normalizar_cadastros.py            só MOSTRA o que mudaria (não altera nada)
    python normalizar_cadastros.py --aplicar  faz um backup e grava
    python normalizar_cadastros.py --tudo     mostra todas as mudanças, não só as primeiras

Mexe em: acolhido (nome, mãe, cônjuge, endereço, bairro, cidade, profissão, religião, escolaridade), responsável e parentesco, outro documento,
condições da contribuição e funcionário (nome e cargo). Não mexe em: textos livres, relatórios e fichas já escritos (o acolhimento social e a
ficha de saúde finalizados têm histórico de versões), nomes de convênios e níveis, nem em quem assinou o quê. Só muda texto TODO em maiúsculas ou
TODO em minúsculas; o que mistura os dois (McDonald, "Maria da Silva") fica como está. Acento o script não coloca: JOSE vira Jose.
Nenhuma data de "alterado em" é mexida: a correção de maiúsculas não conta como alteração do cadastro. Sem o --aplicar nada é gravado.
"""

import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm.attributes import flag_modified

import backup
from app import app
from modelos import Funcionario, Internacao, Pessoa, db
from validacao import escrever_bem

MOSTRAR = 40
FUNCIONARIO = {"nome": "nome", "cargo": "local"}


def mudancas():
    """[(registro, coluna, antes, depois)] de tudo o que a regra mudaria."""
    achadas = []
    for modelo, formas in ((Pessoa, Pessoa.FORMAS), (Internacao, Internacao.FORMAS), (Funcionario, FUNCIONARIO)):
        for registro in db.session.query(modelo).order_by(modelo.id):
            for coluna, forma in formas.items():
                antes = getattr(registro, coluna) or ""
                depois = escrever_bem(forma, antes)
                if depois != antes:
                    achadas.append((registro, coluna, antes, depois))
    return achadas


def main(argv):
    aplicar, tudo = "--aplicar" in argv, "--tudo" in argv
    with app.app_context():
        achadas = mudancas()
        por_campo = Counter(f"{type(r).__name__}.{c}" for r, c, _, _ in achadas)
        for registro, coluna, antes, depois in achadas[: None if tudo else MOSTRAR]:
            print(f"  {type(registro).__name__} nº {registro.id}, {coluna}: {antes!r} -> {depois!r}")
        if len(achadas) > MOSTRAR and not tudo:
            print(f"  ... e mais {len(achadas) - MOSTRAR} (use --tudo para ver todas)")
        if not achadas:
            print("Nada a mudar: tudo já está escrito do jeito padrão.")
            return 0
        print(f"\n{len(achadas)} campo(s) em {len({(type(r).__name__, r.id) for r, *_ in achadas})} registro(s):")
        for nome, n in sorted(por_campo.items()):
            print(f"  {nome}: {n}")
        if not aplicar:
            print("\nNada foi gravado. Para gravar, rode de novo com --aplicar (ele faz um backup antes).")
            return 0

        if db.engine.url.get_backend_name() == "sqlite":
            copia = backup.fazer_backup(Path(db.engine.url.database), backup.pasta_de_backup(None), 30)
            print(f"\nBackup feito: {copia}")
        elif "--sem-backup" not in argv:
            print("\nO banco não é SQLite: faça o backup pelo serviço da hospedagem e rode com --aplicar --sem-backup.")
            return 1
        for registro, coluna, _, depois in achadas:
            setattr(registro, coluna, depois)
            if hasattr(registro, "atualizado_em"):
                flag_modified(registro, "atualizado_em")           # grava o valor que já estava: o `onupdate` não carimba a hora de agora
        db.session.commit()
        resumo = ", ".join(f"{nome}: {n}" for nome, n in sorted(por_campo.items()))
        pasta = Path(__file__).resolve().parent / "logs"
        pasta.mkdir(exist_ok=True)
        with open(pasta / "normalizar_cadastros.log", "a", encoding="utf-8") as arq:
            arq.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {len(achadas)} campo(s) reescritos ({resumo})\n")
        print(f"\nGravado: {len(achadas)} campo(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
