"""
Backup do banco SQLite do servidor do escritório.

    python backup.py                            copia para a pasta de backup e guarda as últimas 30
    python backup.py --destino E:\\backup        escolhe a pasta (de preferência em OUTRO disco)
    python backup.py --manter 60                guarda as últimas 60 cópias
    python backup.py --copiar-para ARQ.db       cópia avulsa e consistente (ex.: levar os dados para o servidor)
                    [--origem OUTRO.db]

A pasta de backup é, nesta ordem: --destino, a variável PASTA_BACKUP, o texto de instance/pasta_backup.txt
(gravado pelo implantacao/instalar.ps1) ou a pasta backups/ do projeto.

A cópia usa o backup do próprio SQLite: sai inteira e consistente mesmo com o sistema em uso, coisa que
copiar o arquivo na mão não garante. Depois de copiar, o arquivo é aberto e conferido; só então a cópia
vale, entra no registro (logs/backup.log) e o sistema sabe que o backup está em dia (instance/ultimo_backup.txt:
sem ele, ou velho, a página inicial avisa). Os arquivos de backup têm dados pessoais: guarde-os com o mesmo cuidado.
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import banco

RAIZ = Path(__file__).resolve().parent
PASTA_INSTANCE = RAIZ / "instance"
BANCO_PADRAO = PASTA_INSTANCE / "internos.db"
TABELAS_ESPERADAS = {"pessoas", "internacoes", "parcelas", "usuarios"}


class ErroDeBackup(Exception):
    pass


def registrar(texto):
    linha = f"{datetime.now():%Y-%m-%d %H:%M:%S} {texto}"
    print(linha)
    try:
        pasta = RAIZ / "logs"
        pasta.mkdir(exist_ok=True)
        with open(pasta / "backup.log", "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def pasta_de_backup(argumento):
    if argumento:
        return Path(argumento)
    if os.environ.get("PASTA_BACKUP"):
        return Path(os.environ["PASTA_BACKUP"])
    escolhida = PASTA_INSTANCE / "pasta_backup.txt"
    if escolhida.exists() and escolhida.read_text(encoding="utf-8-sig").strip():
        return Path(escolhida.read_text(encoding="utf-8-sig").strip())
    return RAIZ / "backups"


def copiar(origem, destino):
    """Copia `origem` para o arquivo `destino` (por um nome provisório) e confere a cópia."""
    if not origem.exists():
        raise ErroDeBackup(f"Não achei o banco de origem: {origem}")
    provisorio = destino.with_name(destino.name + ".parcial")
    provisorio.unlink(missing_ok=True)
    de = sqlite3.connect(f"file:{origem.as_posix()}?mode=ro", uri=True, timeout=60)
    para = sqlite3.connect(provisorio)
    concluida = False
    try:
        de.backup(para)
        para.commit()
        resultado = para.execute("PRAGMA integrity_check").fetchone()[0]
        if resultado != "ok":
            raise ErroDeBackup(f"A cópia ficou com defeito ({resultado}). Nada foi guardado.")
        tabelas = {l[0] for l in para.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"pessoas", "internacoes"} <= tabelas:
            raise ErroDeBackup("A cópia não tem as tabelas do sistema: o arquivo de origem é mesmo o banco do sistema?")
        contagem = {t: para.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                    for t in sorted(TABELAS_ESPERADAS & tabelas)}
        concluida = True
    except sqlite3.Error as erro:
        raise ErroDeBackup(f"O SQLite recusou a cópia: {erro}") from erro
    finally:
        de.close()
        para.close()
        if not concluida:
            provisorio.unlink(missing_ok=True)      # cópia que falhou não fica no destino
    os.replace(provisorio, destino)
    return contagem


def podar(pasta, manter):
    """Guarda só as `manter` cópias mais recentes (o nome leva a data, então a ordem do nome é a do tempo)."""
    antigas = sorted(pasta.glob("internos-*.db"))[:-manter] if manter > 0 else []
    for arquivo in antigas:
        arquivo.unlink()
    return len(antigas)


def fazer_backup(origem, destino_pasta, manter):
    if not destino_pasta.exists():
        try:
            destino_pasta.mkdir(parents=True)
        except OSError as erro:
            raise ErroDeBackup(f"Não consegui acessar a pasta de backup {destino_pasta} "
                               f"(o HD externo está conectado?): {erro}") from erro
    agora = datetime.now()
    arquivo = destino_pasta / f"internos-{agora:%Y-%m-%d_%H%M%S}.db"
    contagem = copiar(origem, arquivo)
    removidas = podar(destino_pasta, manter)
    banco.arquivo_ultimo_backup(PASTA_INSTANCE).write_text(agora.isoformat(timespec="seconds"), encoding="utf-8")
    resumo = ", ".join(f"{n}: {q}" for n, q in contagem.items())
    registrar(f"Backup ok: {arquivo} ({arquivo.stat().st_size // 1024} KB; registros — {resumo}). "
              f"Cópias antigas apagadas: {removidas}.")
    return arquivo


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backup do banco SQLite do sistema.")
    ap.add_argument("--origem", help="banco de origem (padrão: instance/internos.db)")
    ap.add_argument("--destino", help="pasta onde guardar as cópias")
    ap.add_argument("--manter", type=int, default=30, help="quantas cópias guardar (padrão: 30)")
    ap.add_argument("--copiar-para", metavar="ARQUIVO", help="cópia avulsa para este arquivo (não conta como backup)")
    args = ap.parse_args(argv)

    if os.environ.get("DATABASE_URL", "").strip() and not os.environ["DATABASE_URL"].lower().startswith("sqlite"):
        print("Este backup é só para o SQLite. Com Postgres (hospedagem) o backup é feito pelo próprio serviço.")
        return 1
    origem = Path(args.origem) if args.origem else BANCO_PADRAO
    try:
        if args.copiar_para:
            destino = Path(args.copiar_para)
            if destino.exists():
                raise ErroDeBackup(f"{destino} já existe: não vou sobrescrever. Apague ou escolha outro nome.")
            destino.parent.mkdir(parents=True, exist_ok=True)
            contagem = copiar(origem, destino)
            print(f"Copiado para {destino} (registros — {', '.join(f'{n}: {q}' for n, q in contagem.items())}).")
        else:
            fazer_backup(origem, pasta_de_backup(args.destino), args.manter)
    except ErroDeBackup as erro:
        registrar(f"BACKUP FALHOU: {erro}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
