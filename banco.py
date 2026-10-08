"""
Qual banco o sistema usa e como achá-lo.

Os dados dos internos NUNCA vão para o git. O banco fica fora do repositório e o
sistema o encontra pela variável de ambiente DATABASE_URL:

    (sem DATABASE_URL)   SQLite local em instance/internos.db — uso no seu computador
    DATABASE_URL=...     o banco indicado; na hospedagem, o Postgres do Render

No Render:
  1. Crie um banco PostgreSQL pago (o gratuito expira em 30 dias e não tem backup).
  2. No serviço web, crie DATABASE_URL com a "Internal Database URL" do banco. Essa URL
     só funciona de dentro do Render, então o banco não precisa ficar aberto à internet.
  3. Para levar os dados que estão no seu computador, use copiar_banco.py (veja nele).
"""

import os

from sqlalchemy.engine import make_url

SQLITE_LOCAL = "sqlite:///internos.db"        # relativo à pasta instance/
SERVIDOR_LOCAL = {None, "", "localhost", "127.0.0.1", "::1"}


def normalizar_url(texto):
    """Ajusta a URL que a hospedagem entrega para a que o SQLAlchemy entende:
       - postgres:// e postgresql:// viram postgresql+psycopg:// (o driver instalado);
       - Postgres fora desta máquina exige conexão criptografada (sslmode=require)."""
    url = make_url(texto.strip())
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername.startswith("postgresql") and url.host not in SERVIDOR_LOCAL \
            and "sslmode" not in url.query:
        url = url.update_query_dict({"sslmode": "require"})
    return url


def url_do_banco():
    texto = os.environ.get("DATABASE_URL", "").strip()
    return normalizar_url(texto) if texto else SQLITE_LOCAL


def opcoes_do_motor(url):
    """Conexões de Postgres ficam ociosas e a hospedagem as derruba: testa antes de usar."""
    if isinstance(url, str) or url.get_backend_name() == "sqlite":
        return {}
    return {"pool_pre_ping": True, "pool_recycle": 1800}


def descrever(url):
    """Texto seguro para tela e logs: sem usuário e sem senha."""
    url = make_url(url) if isinstance(url, str) else url
    if url.get_backend_name() == "sqlite":
        return f"SQLite ({url.database})"
    return f"{url.get_backend_name()} em {url.host or 'socket local'}/{url.database}"
