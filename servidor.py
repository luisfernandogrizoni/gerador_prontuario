"""
Servidor para a rede do escritório: um computador atende os demais.

    python servidor.py [--porta 8000] [--host 0.0.0.0]

Sobe o sistema com o waitress (que roda no Windows; o gunicorn não) na porta 8000 e aberto
para a rede local. O passo a passo — instalação, firewall, backup diário e atualizações —
está em implantacao/LEIA-ME.md.

Diferenças para o uso no seu computador (python app.py):
  * não é o modo de desenvolvimento: sem recarga automática e sem páginas de depuração;
  * aceita o login em http (SESSAO_SEM_HTTPS=1): a rede interna não tem HTTPS e, sem isso, o
    cookie do login (marcado "só HTTPS") nunca voltaria e ninguém conseguiria entrar;
  * a página inicial avisa se o backup diário parar de funcionar (AVISAR_BACKUP=1);
  * os erros vão para logs/servidor.log. Acessos NÃO são registrados (o endereço traz buscas
    por nome) e os erros do banco não mostram os valores gravados.

A porta e o endereço também podem vir das variáveis PORTA e HOST (a linha de comando vence).
O firewall do Windows é quem limita o acesso à rede do escritório (veja implantacao/instalar.ps1).
"""

import argparse
import logging
import os
import socket
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# antes de importar o sistema: é na importação que ele lê estas opções
os.environ.setdefault("SESSAO_SEM_HTTPS", "1")
os.environ.setdefault("AVISAR_BACKUP", "1")


def configurar_log():
    pasta = RAIZ / "logs"
    pasta.mkdir(exist_ok=True)
    arquivo = RotatingFileHandler(pasta / "servidor.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    arquivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.WARNING)
    raiz.addHandler(arquivo)
    if sys.stderr is not None and sys.stderr.isatty():       # rodando à mão: mostra também na tela
        raiz.addHandler(logging.StreamHandler())
    logging.getLogger("waitress").setLevel(logging.INFO)     # registra a subida do servidor
    return logging.getLogger("servidor")


def endereco_na_rede():
    """O IP deste computador na rede (o que os outros digitam no navegador)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))                  # não envia nada: só descobre a rota
            return s.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())


def main():
    ap = argparse.ArgumentParser(description="Sobe o sistema para a rede do escritório.")
    ap.add_argument("--porta", type=int, help="porta (padrão: 8000)")
    ap.add_argument("--host", help="endereço de escuta (padrão: 0.0.0.0, toda a rede local)")
    args = ap.parse_args()
    log = configurar_log()
    porta = args.porta or int(os.environ.get("PORTA", "8000"))
    host = args.host or os.environ.get("HOST", "0.0.0.0")

    from waitress import serve
    from app import app

    onde = endereco_na_rede() if host == "0.0.0.0" else host
    log.warning("Sistema no ar: http://%s:%s (computador %s)", onde, porta, socket.gethostname())
    print(f"Sistema no ar: http://{onde}:{porta}  (Ctrl+C para parar)")
    try:
        serve(app, host=host, port=porta, threads=4)
    except OSError as erro:
        log.error("Não foi possível abrir a porta %s (já está em uso?): %s", porta, erro)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
