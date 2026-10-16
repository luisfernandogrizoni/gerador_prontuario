"""
Servidor para a rede do escritório: um computador atende os demais.

    python servidor.py [--porta 8000] [--host 0.0.0.0]

Sobe o sistema com o waitress (que roda no Windows; o gunicorn não) na porta 8000 e aberto
para a rede local. O passo a passo — instalação, firewall, backup diário e atualizações —
está em implantacao/LEIA-ME.md.

Como o sistema é servido (instance/rede.json, escrito por implantacao/configurar-https.ps1; a variável MODO_DE_REDE vence o arquivo):
  * "http"  (padrão, como sempre foi): aberto na rede local, sem HTTPS;
  * "misto" (transição): igual ao "http", e **também** atende o HTTPS que o Tailscale Serve entrega por trás (aqui em 127.0.0.1);
  * "https" (final): o waitress escuta só em 127.0.0.1, ninguém chega sem passar pelo HTTPS do Tailscale; o cookie do login volta a ser
    "só HTTPS" e o navegador passa a exigir HTTPS neste endereço (HSTS).
Nos modos "misto" e "https" o waitress confia nos cabeçalhos X-Forwarded-* **só** de quem vem de 127.0.0.1 (o Tailscale Serve): é assim que
o sistema sabe o endereço de quem acessa, para a auditoria e para o limite de tentativas.

Diferenças para o uso no seu computador (python app.py):
  * não é o modo de desenvolvimento: sem recarga automática e sem páginas de depuração;
  * nos modos "http" e "misto" aceita o login em http (SESSAO_SEM_HTTPS=1): a rede interna não tem HTTPS e, sem isso, o
    cookie do login (marcado "só HTTPS") nunca voltaria e ninguém conseguiria entrar;
  * a página inicial avisa se o backup diário parar de funcionar (AVISAR_BACKUP=1);
  * os erros vão para logs/servidor.log. Acessos NÃO são registrados (o endereço traz buscas
    por nome) e os erros do banco não mostram os valores gravados.

A porta e o endereço também podem vir das variáveis PORTA e HOST (a linha de comando vence).
O firewall do Windows é quem limita o acesso à rede do escritório (veja implantacao/instalar.ps1).
"""

import argparse
import json
import logging
import os
import socket
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
MODOS = ("http", "misto", "https")

# antes de importar o sistema: é na importação que ele lê estas opções
os.environ.setdefault("AVISAR_BACKUP", "1")


def carregar_modo(pasta_instance=RAIZ / "instance"):
    """O modo de rede: MODO_DE_REDE, ou instance/rede.json ({"modo": "..."}), ou "http". Valor desconhecido vira "http" (o de sempre)."""
    modo = (os.environ.get("MODO_DE_REDE") or "").strip().lower()
    if not modo:
        try:
            modo = str(json.loads((Path(pasta_instance) / "rede.json").read_text(encoding="utf-8-sig")).get("modo", "")).strip().lower()
        except (OSError, ValueError, AttributeError):
            modo = ""
    return modo if modo in MODOS else "http"


def opcoes_de_rede(modo, host_pedido=None):
    """(host, opções do waitress, ambiente) de cada modo. `host_pedido` (--host ou HOST) vence o padrão do modo."""
    host = host_pedido or ("127.0.0.1" if modo == "https" else "0.0.0.0")
    opcoes = {}
    if modo in ("misto", "https"):
        opcoes = {"trusted_proxy": "127.0.0.1", "trusted_proxy_headers": {"x-forwarded-for", "x-forwarded-proto"},
                  "clear_untrusted_proxy_headers": True, "log_untrusted_proxy_headers": False}
    ambiente = {"SESSAO_SEM_HTTPS": "1"} if modo in ("http", "misto") else {"SOMENTE_HTTPS": "1"}
    return host, opcoes, ambiente


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
    modo = carregar_modo()
    host, opcoes, ambiente = opcoes_de_rede(modo, args.host or os.environ.get("HOST"))
    if modo == "https":
        os.environ.pop("SESSAO_SEM_HTTPS", None)             # (a variável do modo "http" não pode sobrar: o cookie volta a ser só-HTTPS)
    for chave, valor in ambiente.items():
        os.environ.setdefault(chave, valor)                  # (quem definiu a variável de propósito mantém o que definiu)
    os.environ["MODO_DE_REDE_ATUAL"] = modo                  # a página inicial lembra de ligar o HTTPS (avisos._avisos_de_rede)

    from waitress import serve
    from app import app

    onde = endereco_na_rede() if host == "0.0.0.0" else host
    log.warning("Sistema no ar (modo %s): http://%s:%s (computador %s)", modo, onde, porta, socket.gethostname())
    print(f"Sistema no ar (modo {modo}): http://{onde}:{porta}  (Ctrl+C para parar)")
    try:
        serve(app, host=host, port=porta, threads=4, **opcoes)
    except OSError as erro:
        log.error("Não foi possível abrir a porta %s (já está em uso?): %s", porta, erro)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
