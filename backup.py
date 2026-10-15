"""
Backup do banco SQLite do servidor do escritório.

    python backup.py                            copia para a pasta de backup e guarda as últimas 30
    python backup.py --destino E:\\backup        escolhe a pasta (de preferência em OUTRO disco)
    python backup.py --manter 60                guarda as últimas 60 cópias
    python backup.py --copiar-para ARQ.db       cópia avulsa e consistente (ex.: levar os dados para o servidor)
                    [--origem OUTRO.db]

Cópia externa criptografada em pen-drives em rodízio (fase 5 do plano de segurança; veja copia_externa.py):

    python backup.py --configurar-externo       gera a frase de recuperação (uma vez; anote em papel)
    python backup.py --informar-frase           computador novo: guarda a frase que você já tem no papel
    python backup.py --preparar-midia E: --nome A     prepara um pen-drive (faça com cada um)
    python backup.py --listar-midias            mostra as unidades e quais pen-drives estão preparados
    python backup.py --so-externo               só a cópia externa do backup mais novo (a tarefa de hora em hora)
    python backup.py --testar-restauracao       abre a cópia mais nova com a frase do papel e confere o banco
    python backup.py --restaurar ARQ.pbk --para NOVO.db     restaura uma cópia externa (pede a frase)

O backup do dia (que roda como sempre) leva a cópia externa junto quando ela está configurada. Falha da cópia externa
(pen-drive fora, por exemplo) nunca cancela o backup do dia nem a atualização: vira aviso na página inicial.

A pasta de backup é, nesta ordem: --destino, a variável PASTA_BACKUP, o texto de instance/pasta_backup.txt
(gravado pelo implantacao/instalar.ps1) ou a pasta backups/ do projeto.

A cópia usa o backup do próprio SQLite: sai inteira e consistente mesmo com o sistema em uso, coisa que
copiar o arquivo na mão não garante. Depois de copiar, o arquivo é aberto e conferido; só então a cópia
vale, entra no registro (logs/backup.log) e o sistema sabe que o backup está em dia (instance/ultimo_backup.txt:
sem ele, ou velho, a página inicial avisa). Os arquivos de backup têm dados pessoais: guarde-os com o mesmo cuidado.
"""

import argparse
import getpass
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import banco
import copia_externa
import email_envio

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


def levar_para_externo(arquivo):
    """Leva o backup `arquivo` para os pen-drives preparados que estiverem plugados. Nunca levanta erro: o backup do dia já valeu."""
    if not copia_externa.frase_guardada(PASTA_INSTANCE):
        return
    try:
        resultados = copia_externa.copiar_para_as_midias(arquivo, PASTA_INSTANCE, log=registrar)
    except copia_externa.ErroDeCopia as erro:
        registrar(f"COPIA EXTERNA FALHOU: {erro}")
        return
    except Exception as erro:       # biblioteca ausente, disco com defeito...: o aviso da página inicial cobra
        registrar(f"COPIA EXTERNA FALHOU: {type(erro).__name__}: {erro}")
        return
    if not resultados:
        registrar("Cópia externa: nenhum pen-drive preparado está plugado agora (a página inicial avisa se passar de 3 dias).")


ASSINATURA_DO_EMAIL = "\n\n—\nCasa de Acolhida Restauração · Sistema de prontuários\nMensagem automática: não responda."


def avisar_por_email():
    """Manda por e-mail, para quem recebe os avisos do sistema, o que a cópia externa está pedindo (troca do pen-drive, cópia atrasada, dois
    pen-drives plugados, teste de restauração), no máximo uma vez por dia por assunto. Nunca levanta erro: o backup do dia já valeu."""
    try:
        destinos = email_envio.avisos_para(PASTA_INSTANCE)
        if not destinos:
            return
        for chave, assunto, texto in copia_externa.avisos_para_enviar_por_email(PASTA_INSTANCE):
            try:
                email_envio.enviar(PASTA_INSTANCE, destinos, assunto, texto + ASSINATURA_DO_EMAIL)
            except email_envio.ErroDeEmail as erro:
                registrar(f"AVISO POR E-MAIL NÃO ENVIADO ({chave}): {erro}")
                continue
            copia_externa.marcar_avisado(chave, PASTA_INSTANCE)
            registrar(f"Aviso por e-mail enviado ({chave}).")
    except Exception as erro:       # noqa: BLE001 - aviso é cortesia, nunca derruba a tarefa
        registrar(f"AVISO POR E-MAIL FALHOU: {type(erro).__name__}: {erro}")


def backup_mais_novo(pasta):
    """O backup `internos-*.db` mais recente da pasta de backup (o nome leva a data), ou None."""
    achados = sorted(pasta.glob("internos-*.db"))
    return achados[-1] if achados else None


def pedir_frase(rotulo="Frase de recuperação (a do papel)"):
    """Pede a frase sem mostrar na tela; sem terminal, a guardada neste computador."""
    if sys.stdin is not None and sys.stdin.isatty():
        return getpass.getpass(f"{rotulo}: ")
    return copia_externa.frase_guardada(PASTA_INSTANCE) or ""


def configurar_externo():
    if copia_externa.frase_guardada(PASTA_INSTANCE):
        print("A frase de recuperação já existe neste computador. Nada foi mudado.")
        print("Para preparar um pen-drive:  python backup.py --preparar-midia E: --nome A")
        return 0
    if sys.stdin is None or not sys.stdin.isatty():
        raise ErroDeBackup("Preciso de um terminal para mostrar a frase e esperar você anotar. Rode no PowerShell, sem redirecionar a entrada.")
    frase = copia_externa.gerar_frase()
    print("\n" + "=" * 70)
    print("FRASE DE RECUPERAÇÃO DO BACKUP (aparece só agora):\n")
    print(f"        {frase}\n")
    print("Anote EM PAPEL, com letra clara, e guarde fora do computador (não tire foto, não salve em arquivo).")
    print("Sem esta frase as cópias dos pen-drives NÃO abrem, nem para você. Ela é a chave.")
    print("=" * 70)
    while input("\nDigite ANOTEI quando tiver anotado: ").strip().upper() != "ANOTEI":
        print("Anote primeiro: a frase não será mostrada de novo.")
    copia_externa.guardar_frase(frase, PASTA_INSTANCE)
    copia_externa.marcar_configurado(PASTA_INSTANCE)
    registrar("Cópia externa: frase de recuperação criada neste computador (instance\\backup_chave.txt).")
    print("\nPronto. Agora prepare cada pen-drive:  python backup.py --preparar-midia E: --nome A")
    return 0


def informar_frase():
    if copia_externa.frase_guardada(PASTA_INSTANCE):
        print("Já existe uma frase de recuperação neste computador. Nada foi mudado.")
        return 0
    if sys.stdin is None or not sys.stdin.isatty():
        raise ErroDeBackup("Preciso de um terminal para você digitar a frase. Rode no PowerShell, sem redirecionar a entrada.")
    texto = getpass.getpass("Frase de recuperação (a do papel; não aparece na tela): ")
    try:
        usada = copia_externa.adotar_frase(texto, PASTA_INSTANCE)
    except copia_externa.ErroDeCopia as erro:
        if "Não achei nenhuma cópia" not in str(erro):
            raise
        print(f"{erro}")
        if input("Digite SIM para guardar a frase mesmo sem conferir: ").strip().upper() != "SIM":
            raise ErroDeBackup("A frase não foi guardada.") from None
        usada = copia_externa.adotar_frase(texto, PASTA_INSTANCE, exigir_conferencia=False)
    registrar("Cópia externa: frase de recuperação informada neste computador"
              + (f" (conferida abrindo {usada})." if usada else " (sem conferência: nenhum pen-drive plugado)."))
    print("Frase guardada" + (f" e conferida: ela abriu {usada}." if usada else ", sem conferência.") + " Agora prepare os pen-drives.")
    return 0


def listar_midias():
    preparadas = {m.unidade: m for m in copia_externa.achar_midias()}
    unidades = copia_externa.unidades()
    for raiz in unidades:
        marca = "  [proibida: disco do sistema]" if copia_externa._unidade_de(raiz) in copia_externa.unidades_proibidas() else ""
        m = preparadas.get(str(raiz))
        print(f"{raiz}  " + (f"pen-drive preparado: {m.nome}" if m else "sem preparo") + marca)
    if not unidades:
        print("Nenhuma unidade encontrada (este comando é para o Windows).")
    return 0


def preparar_midia(letra, nome):
    raiz = Path(letra if letra.endswith(("\\", "/")) else letra + "\\")
    midia, existia = copia_externa.preparar_midia(raiz, nome, PASTA_INSTANCE)
    registrar(f"Cópia externa: pen-drive {midia.nome} {'já estava preparado' if existia else 'preparado'} em {midia.unidade}.")
    print(f"Plugue sempre este mesmo pen-drive ({midia.nome}): o sistema o reconhece em qualquer porta.")
    return 0


def testar_restauracao(arquivo, usar_guardada):
    frase = copia_externa.frase_guardada(PASTA_INSTANCE) if usar_guardada else pedir_frase()
    if not frase:
        raise ErroDeBackup("Faltou a frase. Rode no PowerShell e digite a frase do papel (o teste vale mais assim: prova que o papel está certo).")
    abriu, contagem = copia_externa.testar_restauracao(PASTA_INSTANCE, frase, Path(arquivo) if arquivo else None)
    resumo = ", ".join(f"{n}: {q}" for n, q in contagem.items())
    registrar(f"TESTE DE RESTAURAÇÃO OK: {abriu.name} abriu e o banco está íntegro (registros — {resumo}).")
    return 0


def restaurar_externo(arquivo, destino):
    frase = pedir_frase()
    if not frase:
        raise ErroDeBackup("Faltou a frase de recuperação.")
    contagem = copia_externa.restaurar(Path(arquivo), Path(destino), frase, PASTA_INSTANCE / "tmp_backup")
    resumo = ", ".join(f"{n}: {q}" for n, q in contagem.items())
    registrar(f"Restaurado: {arquivo} -> {destino} (registros — {resumo}). Para usar, pare o sistema e coloque este arquivo em instance\\internos.db.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backup do banco SQLite do sistema.")
    ap.add_argument("--origem", help="banco de origem (padrão: instance/internos.db)")
    ap.add_argument("--destino", help="pasta onde guardar as cópias")
    ap.add_argument("--manter", type=int, default=30, help="quantas cópias guardar (padrão: 30)")
    ap.add_argument("--copiar-para", metavar="ARQUIVO", help="cópia avulsa para este arquivo (não conta como backup)")
    ap.add_argument("--configurar-externo", action="store_true", help="gera a frase de recuperação da cópia externa (uma vez)")
    ap.add_argument("--informar-frase", action="store_true", help="guarda neste computador a frase de recuperação que já existe (a do papel)")
    ap.add_argument("--preparar-midia", metavar="UNIDADE", help="prepara um pen-drive para a cópia externa (ex.: E:)")
    ap.add_argument("--nome", default="", help="nome do pen-drive que está sendo preparado (ex.: A)")
    ap.add_argument("--listar-midias", action="store_true", help="lista as unidades e os pen-drives preparados")
    ap.add_argument("--so-externo", action="store_true", help="só a cópia externa do backup mais novo (sem fazer outro backup)")
    ap.add_argument("--testar-restauracao", action="store_true", help="abre a cópia externa mais nova e confere o banco")
    ap.add_argument("--arquivo", help="a cópia (.pbk) a testar, em vez da mais nova dos pen-drives plugados")
    ap.add_argument("--usar-chave-guardada", action="store_true", help="no teste, usa a frase guardada neste computador em vez de pedir")
    ap.add_argument("--restaurar", metavar="ARQ.pbk", help="restaura uma cópia externa (pede a frase de recuperação)")
    ap.add_argument("--para", metavar="NOVO.db", help="onde gravar o banco restaurado (não pode existir)")
    args = ap.parse_args(argv)

    if os.environ.get("DATABASE_URL", "").strip() and not os.environ["DATABASE_URL"].lower().startswith("sqlite"):
        print("Este backup é só para o SQLite. Com Postgres (hospedagem) o backup é feito pelo próprio serviço.")
        return 1
    origem = Path(args.origem) if args.origem else BANCO_PADRAO
    try:
        if args.configurar_externo:
            return configurar_externo()
        if args.informar_frase:
            return informar_frase()
        if args.listar_midias:
            return listar_midias()
        if args.preparar_midia:
            return preparar_midia(args.preparar_midia, args.nome)
        if args.testar_restauracao:
            return testar_restauracao(args.arquivo, args.usar_chave_guardada)
        if args.restaurar:
            if not args.para:
                raise ErroDeBackup("Diga onde gravar: --restaurar ARQ.pbk --para NOVO.db")
            return restaurar_externo(args.restaurar, args.para)
        if args.so_externo:
            recente = backup_mais_novo(pasta_de_backup(args.destino))
            if recente is None:
                raise ErroDeBackup("Ainda não há backup do dia para levar ao pen-drive.")
            levar_para_externo(recente)
            avisar_por_email()
        elif args.copiar_para:
            destino = Path(args.copiar_para)
            if destino.exists():
                raise ErroDeBackup(f"{destino} já existe: não vou sobrescrever. Apague ou escolha outro nome.")
            destino.parent.mkdir(parents=True, exist_ok=True)
            contagem = copiar(origem, destino)
            print(f"Copiado para {destino} (registros — {', '.join(f'{n}: {q}' for n, q in contagem.items())}).")
        else:
            levar_para_externo(fazer_backup(origem, pasta_de_backup(args.destino), args.manter))
            avisar_por_email()
    except (ErroDeBackup, copia_externa.ErroDeCopia) as erro:
        registrar(f"BACKUP FALHOU: {erro}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
