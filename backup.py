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
    python backup.py --testar-restauracao       abre a cópia mais nova com a frase do papel e confere o banco (e alguns documentos escaneados)
    python backup.py --restaurar ARQ.pbk --para NOVO.db     restaura uma cópia externa (pede a frase)

O backup do dia (que roda como sempre) leva a cópia externa junto quando ela está configurada. Falha da cópia externa
(pen-drive fora, por exemplo) nunca cancela o backup do dia nem a atualização: vira aviso na página inicial.

A pasta de backup é, nesta ordem: --destino, a variável PASTA_BACKUP, o texto de instance/pasta_backup.txt
(gravado pelo implantacao/instalar.ps1) ou a pasta backups/ do projeto.

Os documentos escaneados (os PDFs anexados às fichas, anexos.py) ficam em instance/anexos, fora do banco: o backup do dia os espelha em <pasta de backup>/anexos,
copiando só o que ainda não está lá (um PDF não muda depois de enviado). O que o administrador apaga de vez sai do espelho 30 dias depois. A cópia externa
criptografada dos pen-drives leva os PDFs também, um arquivo criptografado por PDF na pasta `anexos` do pen-drive (copia_externa.py). Falha na cópia dos PDFs para o
disco de backup não impede o backup do banco nem a cópia externa: o comando termina com erro no fim.

    python backup.py --restaurar-anexos E: --para C:\\prontuario\\instance\\anexos     restaura os PDFs de um pen-drive (pede a frase; a pasta não pode existir)
                    [--incluir-apagados]

A cópia usa o backup do próprio SQLite: sai inteira e consistente mesmo com o sistema em uso, coisa que
copiar o arquivo na mão não garante. Depois de copiar, o arquivo é aberto e conferido; só então a cópia
vale, entra no registro (logs/backup.log) e o sistema sabe que o backup está em dia (instance/ultimo_backup.txt:
sem ele, ou velho, a página inicial avisa). Os arquivos de backup têm dados pessoais: guarde-os com o mesmo cuidado.
"""

import argparse
import getpass
import os
import shutil
import sqlite3
import sys
import time
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


DIAS_NO_ESPELHO = 30               # quanto tempo um PDF apagado de vez ainda fica no espelho (como os 30 backups do banco)


def espelhar_anexos(destino_pasta, agora=None):
    """Copia os PDFs dos documentos escaneados para <destino_pasta>/anexos, só os que ainda não estão lá (mesmo nome e tamanho). Quem sumiu da origem (apagado
    de vez) é separado como .apagado e some do espelho depois de DIAS_NO_ESPELHO dias. Devolve (arquivos na origem, bytes, copiados agora, descartados)."""
    agora = agora or time.time()
    origem, espelho = banco.pasta_dos_anexos(PASTA_INSTANCE), destino_pasta / "anexos"
    total = tamanho_total = copiados = descartados = 0
    if origem.is_dir():
        for arquivo in sorted(origem.rglob("*.pdf")):
            alvo = espelho / arquivo.relative_to(origem)
            tamanho = arquivo.stat().st_size
            total, tamanho_total = total + 1, tamanho_total + tamanho
            if alvo.is_file() and alvo.stat().st_size == tamanho:
                continue
            alvo.parent.mkdir(parents=True, exist_ok=True)
            provisorio = alvo.with_name(alvo.name + ".parcial")
            shutil.copy2(arquivo, provisorio)
            if provisorio.stat().st_size != tamanho:
                provisorio.unlink(missing_ok=True)
                raise ErroDeBackup(f"A cópia de {arquivo.name} ficou com tamanho diferente do original.")
            os.replace(provisorio, alvo)
            copiados += 1
    if espelho.is_dir():
        for alvo in sorted(espelho.rglob("*.pdf")):
            if not (origem / alvo.relative_to(espelho)).exists():           # apagado de vez na origem: separa, e o relógio dos 30 dias começa agora
                separado = alvo.with_name(alvo.name + ".apagado")
                os.replace(alvo, separado)
                os.utime(separado, (agora, agora))
        for separado in sorted(espelho.rglob("*.apagado")):
            if agora - separado.stat().st_mtime > DIAS_NO_ESPELHO * 86400:
                separado.unlink()
                descartados += 1
                try:
                    separado.parent.rmdir()
                except OSError:
                    pass
    return total, tamanho_total, copiados, descartados


def copiar_anexos(destino_pasta):
    total, tamanho, copiados, descartados = espelhar_anexos(destino_pasta)
    if total or copiados or descartados:
        registrar(f"Documentos escaneados: {total} arquivo(s), {tamanho / (1024 * 1024):.1f} MB; copiados agora: {copiados}; descartados do espelho: {descartados}.")


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
    pdfs = (copia_externa.carregar(PASTA_INSTANCE).get("ultimo_teste") or {}).get("documentos") or 0
    registrar(f"TESTE DE RESTAURAÇÃO OK: {abriu.name} abriu e o banco está íntegro (registros — {resumo})"
              + (f"; {pdfs} documento(s) escaneado(s) do pen-drive também abriram." if pdfs else "."))
    return 0


def restaurar_anexos_externo(origem, destino, incluir_apagados):
    frase = pedir_frase()
    if not frase:
        raise ErroDeBackup("Faltou a frase de recuperação.")
    restaurados, defeituosos = copia_externa.restaurar_anexos(Path(origem), Path(destino), frase, incluir_apagados, log=registrar)
    registrar(f"Documentos escaneados restaurados: {origem} -> {destino} ({restaurados} arquivo(s)"
              + (f"; {defeituosos} NÃO abriram: veja as linhas NAO ABRIU acima" if defeituosos else "") + "). Para usar, pare o sistema e coloque esta pasta em instance\\anexos.")
    return 1 if defeituosos else 0


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
    ap.add_argument("--para", metavar="NOVO.db", help="onde gravar o banco restaurado, ou a pasta dos documentos restaurados (não pode existir)")
    ap.add_argument("--restaurar-anexos", metavar="PENDRIVE", help="restaura os documentos escaneados de um pen-drive (ex.: E:) em --para (pede a frase de recuperação)")
    ap.add_argument("--incluir-apagados", action="store_true", help="na restauração dos documentos, traz também os que foram apagados de vez no sistema (guardados por um ano)")
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
        if args.restaurar_anexos:
            if not args.para:
                raise ErroDeBackup("Diga onde gravar: --restaurar-anexos E: --para PASTA_NOVA")
            return restaurar_anexos_externo(args.restaurar_anexos, args.para, args.incluir_apagados)
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
            arquivo = fazer_backup(origem, pasta_de_backup(args.destino), args.manter)
            falha_dos_pdfs = None
            try:
                copiar_anexos(pasta_de_backup(args.destino))
            except (ErroDeBackup, OSError) as erro:                  # o banco já foi copiado: a cópia externa e o aviso seguem, e o comando termina com erro
                falha_dos_pdfs = erro
            levar_para_externo(arquivo)
            avisar_por_email()
            if falha_dos_pdfs is not None:
                raise ErroDeBackup(f"O banco foi copiado, mas a cópia dos documentos escaneados falhou: {falha_dos_pdfs}")
    except (ErroDeBackup, copia_externa.ErroDeCopia) as erro:
        registrar(f"BACKUP FALHOU: {erro}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
