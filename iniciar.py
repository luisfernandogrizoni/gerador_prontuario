"""
Abre o sistema neste computador com um clique. É este arquivo que vira o .exe
(construir_exe.bat gera dist\\SistemaProntuarios\\SistemaProntuarios.exe).

O que acontece ao abrir:
  1. sobe o sistema SÓ neste computador (127.0.0.1): ninguém na rede consegue acessar;
  2. abre o navegador na tela de entrada (no primeiro uso, na tela de criar o usuário);
  3. a janela preta fica aberta enquanto o sistema roda. Para encerrar, feche-a.

Onde ficam os dados (banco e chave da sessão): na pasta do seu usuário no Windows,
  C:\\Users\\<você>\\AppData\\Local\\SistemaProntuarios
FORA da pasta do programa — assim dá para copiar o programa para outro computador sem levar
os dados dos internos junto. Faça cópia dessa pasta de tempos em tempos (backup).

Variáveis opcionais: DADOS_DIR (outra pasta de dados), PORTA (padrão 8765),
SEM_NAVEGADOR=1 (não abre o navegador; usado nos testes).
"""

import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

NOME = "SistemaProntuarios"
ENDERECO = "127.0.0.1"   # nunca 0.0.0.0: isso abriria o sistema para toda a rede
PORTA_PADRAO = 8765
TENTATIVAS_DE_PORTA = 20


def pasta_de_dados():
    if os.environ.get("DADOS_DIR"):
        return Path(os.environ["DADOS_DIR"]).resolve()
    base = os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share")
    return Path(base) / NOME


def porta_em_uso(porta):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((ENDERECO, porta)) == 0


def e_o_sistema(porta):
    """A porta está ocupada pelo próprio sistema (já aberto) ou por outro programa?"""
    try:
        with urllib.request.urlopen(f"http://{ENDERECO}:{porta}/login", timeout=3) as r:
            return b"Casa de Acolhida" in r.read(20000)
    except Exception:
        return False


def abrir_navegador(url, esperar=False, porta=None):
    if esperar:       # espera o servidor responder antes de abrir (até 30 s)
        for _ in range(60):
            if porta_em_uso(porta):
                break
            time.sleep(0.5)
    if not os.environ.get("SEM_NAVEGADOR"):
        webbrowser.open(url)


def escolher_porta():
    """(porta, ja_aberto): a primeira porta livre ou a que já tem o próprio sistema rodando."""
    inicial = int(os.environ.get("PORTA") or PORTA_PADRAO)
    for porta in range(inicial, inicial + TENTATIVAS_DE_PORTA):
        if not porta_em_uso(porta):
            return porta, False
        if e_o_sistema(porta):
            return porta, True
    raise RuntimeError(f"Não achei uma porta livre entre {inicial} e {inicial + TENTATIVAS_DE_PORTA - 1}.")


def main():
    for saida in (sys.stdout, sys.stderr):    # acentos certos e texto na tela na hora, mesmo se redirecionado
        if saida:
            saida.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    pasta = pasta_de_dados()
    pasta.mkdir(parents=True, exist_ok=True)
    os.environ["DADOS_DIR"] = str(pasta)   # o sistema (app.py) lê estas duas variáveis
    os.environ["MODO_LOCAL"] = "1"

    porta, ja_aberto = escolher_porta()
    url = f"http://{ENDERECO}:{porta}/"
    if ja_aberto:
        print("O sistema já está aberto. Abrindo no navegador...")
        abrir_navegador(url)
        return

    print("Sistema de Prontuários — Casa de Acolhida Restauração")
    print("Iniciando...")
    from waitress import serve      # importados só agora: dependem das variáveis acima
    from app import app

    print(f"\nPronto! Endereço: {url}")
    print("Só este computador consegue acessar. Se o navegador não abrir sozinho, copie o endereço acima.")
    print(f"Seus dados ficam em: {pasta}")
    print("\nNÃO feche esta janela enquanto estiver usando o sistema.")
    print("Para encerrar o sistema, feche esta janela.")
    threading.Thread(target=abrir_navegador, args=(url, True, porta), daemon=True).start()
    try:
        serve(app, host=ENDERECO, port=porta, threads=4)
    except KeyboardInterrupt:
        pass
    print("\nSistema encerrado.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # com duplo clique a janela fecharia na hora e ninguém leria o erro: segura a janela
        print("\nNão foi possível abrir o sistema:\n")
        traceback.print_exc()
        try:
            input("\nTecle Enter para fechar...")
        except EOFError:
            pass
        sys.exit(1)
