"""
Copia os dados do SQLite local (instance/internos.db) para o banco da hospedagem.

Os dados vão DIRETO do seu computador para o banco, por conexão criptografada.
Não passam pelo git nem pelo GitHub.

Uso:
    python copiar_banco.py                  # copia para o banco cuja URL você informar
    python copiar_banco.py --substituir     # destino já tem dados: apaga e copia de novo
    python copiar_banco.py --origem outro.db

A URL do banco de destino é lida da variável DESTINO_URL; se ela não existir, o script a
pede (a digitação não aparece na tela, para a senha não ficar no histórico do terminal).
Use a "External Database URL" do Render, que só deve ficar liberada durante a cópia:
  1. antes: no banco, em Networking, deixe só o seu IP na lista de acesso;
  2. rode este script;
  3. depois: apague a lista de acesso externo (o serviço web usa a URL interna).

Os usuários do login NÃO são copiados: crie-os no destino (ADMIN_USUARIO/ADMIN_SENHA ou
flask criar-usuario). O script confere, linha por linha, se o destino ficou igual à origem.
"""

import os
from pathlib import Path

import click
from sqlalchemy import create_engine, func, select, text

import banco
from modelos import db

RAIZ = Path(__file__).parent
TABELAS_COPIADAS = ("pessoas", "internacoes", "parcelas", "avisos_dispensados")   # ordem das chaves
SEM_ID_SEQUENCIAL = {"avisos_dispensados"}   # a chave é um texto, não há sequência para acertar


def _tabelas():
    por_nome = db.metadata.tables
    return [por_nome[nome] for nome in TABELAS_COPIADAS]


def _linhas(conexao, tabela):
    """Todas as linhas, na ordem da chave (ordenado aqui: SQLite e Postgres ordenam texto diferente)."""
    posicoes = [tabela.columns.keys().index(c.name) for c in tabela.primary_key.columns]
    return sorted((tuple(l) for l in conexao.execute(select(tabela))),
                  key=lambda l: tuple(l[i] for i in posicoes))


def _acertar_sequencias(conexao, tabelas):
    """No Postgres, depois de inserir com id explícito a sequência continua em 1: o próximo
    cadastro novo bateria numa chave que já existe. Põe cada sequência depois do maior id."""
    for tabela in tabelas:
        if tabela.name in SEM_ID_SEQUENCIAL:
            continue
        conexao.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{tabela.name}', 'id'), "
            f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {tabela.name}"))


@click.command()
@click.option("--origem", default=str(RAIZ / "instance" / "internos.db"), show_default=True,
              help="banco SQLite com os dados")
@click.option("--substituir", is_flag=True, help="apaga os dados que já existirem no destino")
def copiar(origem, substituir):
    if not Path(origem).exists():
        raise click.ClickException(f"Não achei o banco de origem: {origem}")
    texto = os.environ.get("DESTINO_URL") or click.prompt("URL do banco de destino", hide_input=True)
    url = banco.normalizar_url(texto)
    if url.get_backend_name() == "sqlite":
        raise click.ClickException("O destino precisa ser o Postgres da hospedagem, não um SQLite.")

    de = create_engine(f"sqlite:///{Path(origem).resolve().as_posix()}")
    para = create_engine(url, **banco.opcoes_do_motor(url))
    tabelas = _tabelas()
    click.echo(f"Origem : {origem}\nDestino: {banco.descrever(url)}")

    try:
        db.metadata.create_all(para)                 # cria o que faltar (inclusive usuarios)
        with de.connect() as o, para.begin() as d:   # destino numa transação: erro = nada muda
            existentes = {t.name: d.execute(select(func.count()).select_from(t)).scalar() for t in tabelas}
            if any(existentes.values()):
                resumo = ", ".join(f"{n}: {q}" for n, q in existentes.items())
                if not substituir:
                    raise click.ClickException(
                        f"O destino já tem dados ({resumo}). Nada foi alterado. "
                        "Para apagar e copiar de novo, use --substituir.")
                click.confirm(f"Isto APAGA os dados do destino ({resumo}). Continuar?", abort=True)
                for t in reversed(tabelas):
                    d.execute(t.delete())

            for t in tabelas:
                linhas = o.execute(select(t)).mappings().all()
                if linhas:
                    d.execute(t.insert(), [dict(l) for l in linhas])
                click.echo(f"  {t.name}: {len(linhas)} linhas copiadas")
            _acertar_sequencias(d, tabelas)

            # conferência: o destino tem que ser IGUAL à origem, valor por valor
            for t in tabelas:
                if _linhas(o, t) != _linhas(d, t):
                    raise click.ClickException(f"A tabela {t.name} ficou diferente da origem. "
                                               "Nada foi gravado (a cópia foi desfeita).")
        click.echo("Conferido: o destino é idêntico à origem. Lembre de fechar o acesso externo ao banco.")
    finally:
        de.dispose()
        para.dispose()


if __name__ == "__main__":
    copiar()
