"""
Cópia externa criptografada do backup, em pen-drives em rodízio (plano de segurança, fase 5: docs/plano-de-seguranca.md).

O backup do dia (backup.py) fica neste computador. Aqui ele ganha uma segunda vida **fora** dele:

  * **Criptografado** (AES-256-GCM, com a chave tirada de uma *frase de recuperação* pelo scrypt) e comprimido. Quem achar ou
    roubar o pen-drive não lê nada. A frase é gerada uma vez, aparece uma vez na tela para ser anotada **em papel** e fica
    guardada neste computador (instance/backup_chave.txt, com acesso só do sistema e dos administradores) para a tarefa
    automática poder criptografar. Para restaurar em outro computador basta o arquivo e a frase do papel.
  * **Conferido na hora**: logo depois de gravar, o arquivo é aberto de novo, descriptografado e o banco de dentro é conferido
    (integridade e número de registros). Cópia que não abre não vale e não fica.
  * **Em rodízio**: cada pen-drive é *preparado* uma vez (uma pastinha `prontuario-backup` com um código próprio) e o sistema o
    reconhece em qualquer porta ou letra de unidade. Um fica plugado no computador, o outro guardado trancado (o ideal é fora do
    escritório; na gaveta trancada protege de vírus e de erro, mas não de incêndio nem de roubo); o sistema anota
    desde quando cada um está plugado e avisa na página inicial quando é hora de trocar, de plugar o pen-drive ou de testar.
  * **Com histórico**: em cada pen-drive ficam as cópias dos últimos 14 dias, uma por semana nas 8 semanas seguintes e uma
    por mês até completar um ano, para um erro descoberto tarde ainda ter de onde voltar.
  * **Testável**: `backup.py --testar-restauracao` abre a cópia mais nova com a frase do papel e confere o banco.

Formato do arquivo (.pbk): "PBK1", parâmetros do scrypt (3 bytes), sal (16), nonce (12); depois o banco comprimido e
criptografado (AES-GCM, com o cabeçalho como dado autenticado) e, no fim, a marca de autenticação (16 bytes). Trocar um byte
qualquer, ou errar a frase, é detectado.

A biblioteca `cryptography` só é carregada quando se criptografa ou descriptografa: a página inicial e a tela de backup usam só
o estado (instance/backup_externo.json) e funcionam sem ela.
"""

import ctypes
import hashlib
import json
import os
import re
import secrets
import sqlite3
import tempfile
import uuid
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PASTA_INSTANCE = RAIZ / "instance"
PASTA_NA_MIDIA = "prontuario-backup"
ARQUIVO_DA_MIDIA = "midia.json"
ARQUIVO_DO_ESTADO = "backup_externo.json"
ARQUIVO_DA_FRASE = "backup_chave.txt"
ARQUIVO_DO_BLOQUEIO = "backup_externo.lock"

MAGICA = b"PBK1"
N_LOG2, R, P = 15, 8, 1               # scrypt: ~32 MB de memória e uns 100 ms por cópia
TAMANHO_DO_CABECALHO = len(MAGICA) + 3 + 16 + 12
TAMANHO_DA_MARCA = 16
BLOCO = 1 << 20
ALFABETO = "ABCDEFGHJKMNPQRSTVWXYZ23456789"      # sem 0/O, 1/I/L, U: não se confunde no papel
TABELAS_ESPERADAS = ("pessoas", "internacoes", "parcelas", "usuarios")

# prazos dos avisos da página inicial
DIAS_SEM_COPIA = 3                    # sem cópia externa há mais que isso: o pen-drive está plugado?
DIAS_PARA_TROCAR = 7                  # o mesmo pen-drive plugado há 7 dias (de calendário) ou mais: troque (tire-o, guarde-o trancado e plugue o outro)
DIA_DA_TROCA = 4                      # sexta-feira (weekday(): segunda = 0): o dia combinado da troca semanal
DIAS_MINIMOS_NA_SEXTA = 4             # na sexta, o lembrete vale para um pen-drive plugado há pelo menos 4 dias
HORA_DA_TROCA = (18, 45)              # depois do backup das 18:30 e da cópia externa que vai junto
DIAS_SEM_TESTE = 100                  # teste de restauração: a cada ~3 meses
DIAS_ATE_O_PRIMEIRO_TESTE = 7
MANTER_DIARIAS, MANTER_SEMANAS, GUARDAR_ATE_DIAS = 14, 8, 366     # cópias: todas por 14 dias, 1 por semana por 8 semanas, 1 por mês até 1 ano


class ErroDeCopia(Exception):
    """Falha esperada (frase errada, pen-drive ausente, arquivo danificado): a mensagem é para a pessoa ler."""


# ============================================================================= frase de recuperação
def gerar_frase():
    """24 letras e números sem ambiguidade em 6 grupos (cerca de 118 bits): XXXX-XXXX-XXXX-XXXX-XXXX-XXXX."""
    return "-".join("".join(secrets.choice(ALFABETO) for _ in range(4)) for _ in range(6))


def normalizar_frase(texto):
    """Maiúsculas, sem espaços nem hífens: dá para digitar do papel de qualquer jeito."""
    return re.sub(r"[\s\-]", "", texto or "").upper()


def arquivo_da_frase(instance=PASTA_INSTANCE):
    return Path(instance) / ARQUIVO_DA_FRASE


def frase_guardada(instance=PASTA_INSTANCE):
    arquivo = arquivo_da_frase(instance)
    if not arquivo.exists():
        return None
    texto = arquivo.read_text(encoding="utf-8-sig").strip()
    return texto or None


def guardar_frase(frase, instance=PASTA_INSTANCE):
    arquivo = arquivo_da_frase(instance)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    if frase_guardada(instance):
        raise ErroDeCopia("Já existe uma frase de recuperação. Trocar a frase deixaria as cópias antigas sem chave: "
                          "se for mesmo preciso, apague instance\\backup_chave.txt sabendo que elas continuam pedindo a frase de antes.")
    arquivo.write_text(frase + "\n", encoding="utf-8")
    try:
        os.chmod(arquivo, 0o600)
    except OSError:
        pass


def formatar_frase(texto):
    """A frase em 6 grupos de 4, como aparece no papel. ErroDeCopia se não tem o formato (24 letras e números do alfabeto)."""
    limpa = normalizar_frase(texto)
    if len(limpa) != 24 or any(c not in ALFABETO for c in limpa):
        raise ErroDeCopia("A frase tem 24 letras e números, em 6 grupos de 4 (XXXX-XXXX-XXXX-XXXX-XXXX-XXXX). Confira o papel: "
                          "não existem 0, 1, I, L, O nem U nela.")
    return "-".join(limpa[i:i + 4] for i in range(0, 24, 4))


def adotar_frase(texto, instance=PASTA_INSTANCE, raizes=None, exigir_conferencia=True):
    """Computador novo, frase que já existia (a do papel): confere o formato e, se houver cópia em pen-drive plugado, que ela
    ABRE com essa frase; só então guarda. Devolve o nome do arquivo usado na conferência (None se não havia cópia plugada e
    `exigir_conferencia` é False)."""
    frase = formatar_frase(texto)
    candidatas = [(data_da_copia(p.name), p) for m in achar_midias(raizes) for p in m.pasta.glob("prontuario-*.pbk") if data_da_copia(p.name)]
    conferida = None
    if candidatas:
        conferida = max(candidatas)[1]
        verificar_copia(conferida, frase, Path(instance) / "tmp_backup")            # frase errada: ErroDeCopia, nada é guardado
    elif exigir_conferencia:
        raise ErroDeCopia("Não achei nenhuma cópia nos pen-drives plugados para conferir a frase. Plugue um pen-drive preparado.")
    guardar_frase(frase, instance)
    marcar_configurado(instance)
    return conferida.name if conferida else None


# ============================================================================= o arquivo .pbk
def _chave(frase, sal, n_log2, r, p):
    return hashlib.scrypt(normalizar_frase(frase).encode("utf-8"), salt=sal, n=1 << n_log2, r=r, p=p, dklen=32,
                          maxmem=256 * (1 << n_log2) * r + (1 << 20))


def criptografar(origem, destino, frase):
    """Comprime e criptografa `origem` em `destino` (por um nome provisório, que só vira definitivo se tudo deu certo)."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    origem, destino = Path(origem), Path(destino)
    sal, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    cabecalho = MAGICA + bytes([N_LOG2, R, P]) + sal + nonce
    cifra = Cipher(algorithms.AES(_chave(frase, sal, N_LOG2, R, P)), modes.GCM(nonce)).encryptor()
    cifra.authenticate_additional_data(cabecalho)
    compressor = zlib.compressobj(6)
    provisorio = destino.with_name(destino.name + ".parcial")
    try:
        with open(origem, "rb") as de, open(provisorio, "wb") as para:
            para.write(cabecalho)
            while bloco := de.read(BLOCO):
                para.write(cifra.update(compressor.compress(bloco)))
            para.write(cifra.update(compressor.flush()))
            cifra.finalize()
            para.write(cifra.tag)
            para.flush()
            os.fsync(para.fileno())
        os.replace(provisorio, destino)
    except BaseException:
        provisorio.unlink(missing_ok=True)
        raise


def descriptografar(origem, destino, frase):
    """Abre `origem` e grava o banco em `destino`. Frase errada ou arquivo mexido: ErroDeCopia e nada fica gravado."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    origem, destino = Path(origem), Path(destino)
    tamanho = origem.stat().st_size
    if tamanho < TAMANHO_DO_CABECALHO + TAMANHO_DA_MARCA:
        raise ErroDeCopia(f"{origem.name} é pequeno demais para ser uma cópia do sistema (arquivo cortado?).")
    provisorio = destino.with_name(destino.name + ".parcial")
    try:
        with open(origem, "rb") as de:
            cabecalho = de.read(TAMANHO_DO_CABECALHO)
            if cabecalho[:4] != MAGICA:
                raise ErroDeCopia(f"{origem.name} não é uma cópia criptografada do sistema.")
            n_log2, r, p = cabecalho[4], cabecalho[5], cabecalho[6]
            if not (10 <= n_log2 <= 20 and 1 <= r <= 16 and 1 <= p <= 4):
                raise ErroDeCopia(f"{origem.name} tem um cabeçalho que não reconheço (arquivo danificado?).")
            sal, nonce = cabecalho[7:23], cabecalho[23:35]
            de.seek(tamanho - TAMANHO_DA_MARCA)
            marca = de.read(TAMANHO_DA_MARCA)
            de.seek(TAMANHO_DO_CABECALHO)
            restante = tamanho - TAMANHO_DO_CABECALHO - TAMANHO_DA_MARCA
            decifra = Cipher(algorithms.AES(_chave(frase, sal, n_log2, r, p)), modes.GCM(nonce, marca)).decryptor()
            decifra.authenticate_additional_data(cabecalho)
            descompressor = zlib.decompressobj()
            with open(provisorio, "wb") as para:
                while restante > 0:
                    bloco = de.read(min(BLOCO, restante))
                    if not bloco:
                        raise ErroDeCopia(f"{origem.name} acabou antes da hora (arquivo cortado?).")
                    restante -= len(bloco)
                    para.write(descompressor.decompress(decifra.update(bloco)))
                para.write(descompressor.flush())
                decifra.finalize()                 # é aqui que a frase errada ou um byte mexido aparece
                para.flush()
                os.fsync(para.fileno())
        os.replace(provisorio, destino)
    except (InvalidTag, zlib.error) as erro:
        provisorio.unlink(missing_ok=True)
        raise ErroDeCopia("A frase de recuperação não confere, ou o arquivo está danificado.") from erro
    except BaseException:
        provisorio.unlink(missing_ok=True)
        raise


def conferir_banco(caminho):
    """Abre o banco SQLite e confere: íntegro, com as tabelas do sistema. Devolve {tabela: nº de registros}."""
    try:
        con = sqlite3.connect(f"file:{Path(caminho).as_posix()}?mode=ro", uri=True, timeout=30)
        try:
            resultado = con.execute("PRAGMA integrity_check").fetchone()[0]
            if resultado != "ok":
                raise ErroDeCopia(f"O banco dentro da cópia está com defeito ({resultado}).")
            tabelas = {l[0] for l in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if not {"pessoas", "internacoes"} <= tabelas:
                raise ErroDeCopia("O arquivo aberto não tem as tabelas do sistema: é mesmo o banco do prontuário?")
            return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in TABELAS_ESPERADAS if t in tabelas}
        finally:
            con.close()
    except sqlite3.Error as erro:
        raise ErroDeCopia(f"O SQLite não conseguiu abrir o banco da cópia: {erro}") from erro


def verificar_copia(arquivo, frase, pasta_temporaria):
    """Abre a cópia do jeito que uma restauração abriria e confere o banco. Devolve a contagem de registros."""
    pasta_temporaria = Path(pasta_temporaria)
    pasta_temporaria.mkdir(parents=True, exist_ok=True)
    corrente = Path(tempfile.mkdtemp(prefix="verificacao_", dir=pasta_temporaria))
    try:
        banco = corrente / "banco.db"
        descriptografar(arquivo, banco, frase)
        return conferir_banco(banco)
    finally:
        for sobra in corrente.glob("*"):
            sobra.unlink(missing_ok=True)
        try:
            corrente.rmdir()
        except OSError:
            pass


def restaurar(arquivo, destino, frase, pasta_temporaria=None):
    """Restaura `arquivo` (.pbk) em `destino`, que não pode existir. Só grava se o banco de dentro está íntegro."""
    destino = Path(destino)
    if destino.exists():
        raise ErroDeCopia(f"{destino} já existe: não vou sobrescrever. Escolha outro nome (ou mova o arquivo de lá).")
    destino.parent.mkdir(parents=True, exist_ok=True)
    provisorio = destino.with_name(destino.name + ".restaurando")
    try:
        descriptografar(arquivo, provisorio, frase)
        contagem = conferir_banco(provisorio)
        os.replace(provisorio, destino)
    finally:
        provisorio.unlink(missing_ok=True)
    return contagem


# ============================================================================= pen-drives
@dataclass(frozen=True)
class Midia:
    id: str
    nome: str
    pasta: Path          # a pasta prontuario-backup dentro dela
    unidade: str         # "E:\" (ou a raiz que foi passada)


def unidades():
    """Raízes das unidades do computador (E:\\...), só as que podem ser pen-drive ou HD: removíveis e fixas. Fora do Windows, nenhuma."""
    if os.name != "nt":
        return []
    achadas = []
    mascara = ctypes.windll.kernel32.GetLogicalDrives()
    for i in range(26):
        if mascara >> i & 1:
            raiz = f"{chr(65 + i)}:\\"
            if ctypes.windll.kernel32.GetDriveTypeW(raiz) in (2, 3):
                achadas.append(Path(raiz))
    return achadas


def _unidade_de(caminho):
    return os.path.splitdrive(str(caminho))[0].upper()


def unidades_proibidas():
    """A unidade do Windows e a deste sistema: a cópia externa nunca vai parar no mesmo disco do banco."""
    return {u for u in (os.environ.get("SystemDrive", "C:").upper(), _unidade_de(RAIZ)) if u}


def achar_midias(raizes=None):
    """Os pen-drives preparados que estão plugados agora (procura em todas as unidades, menos a do sistema)."""
    achadas, vistos = [], set()
    proibidas = unidades_proibidas()
    for raiz in (unidades() if raizes is None else [Path(r) for r in raizes]):
        if raizes is None and _unidade_de(raiz) in proibidas:
            continue
        marca = raiz / PASTA_NA_MIDIA / ARQUIVO_DA_MIDIA
        try:
            dados = json.loads(marca.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(dados, dict) or not dados.get("id") or dados["id"] in vistos:
            continue                                    # (pen-drive clonado: a segunda cópia do mesmo código é ignorada)
        vistos.add(dados["id"])
        achadas.append(Midia(dados["id"], dados.get("nome") or dados["id"][:6], raiz / PASTA_NA_MIDIA, str(raiz)))
    return achadas


def preparar_midia(raiz, nome="", instance=PASTA_INSTANCE, agora=None, proibidas=None):
    """Prepara o pen-drive em `raiz` (E:\\): cria a pasta prontuario-backup com um código só dele. Devolve (Midia, já_existia)."""
    raiz = Path(raiz)
    agora = agora or datetime.now()
    proibidas = unidades_proibidas() if proibidas is None else proibidas
    if not raiz.is_dir():
        raise ErroDeCopia(f"Não achei a unidade {raiz}. O pen-drive está plugado? Veja as letras com: python backup.py --listar-midias")
    if raiz.drive and _unidade_de(raiz) in proibidas:
        raise ErroDeCopia(f"{raiz} é o disco do próprio computador: a cópia externa precisa ir para um pen-drive ou HD externo.")
    pasta = raiz / PASTA_NA_MIDIA
    marca = pasta / ARQUIVO_DA_MIDIA
    if marca.exists():
        try:
            dados = json.loads(marca.read_text(encoding="utf-8"))
            existente = Midia(dados["id"], dados.get("nome") or dados["id"][:6], pasta, str(raiz))
        except (OSError, ValueError, KeyError) as erro:
            raise ErroDeCopia(f"{marca} existe mas não consigo ler: apague a pasta {pasta} e prepare de novo.") from erro
        estado = carregar(instance)
        estado["midias"].setdefault(existente.id, {"nome": existente.nome, "preparada_em": agora.isoformat(timespec="seconds")})
        salvar(estado, instance)
        return existente, True
    estado = carregar(instance)
    nome = (nome or "").strip() or f"Pen-drive {len(estado['midias']) + 1}"
    if nome.lower() in {m.get("nome", "").lower() for m in estado["midias"].values()}:
        raise ErroDeCopia(f"Já existe uma mídia chamada {nome}. Escolha outro nome (por exemplo A e B), para saber qual levar para casa.")
    novo = uuid.uuid4().hex
    pasta.mkdir(exist_ok=True)
    marca.write_text(json.dumps({"id": novo, "nome": nome, "preparada_em": agora.isoformat(timespec="seconds")}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    estado["midias"][novo] = {"nome": nome, "preparada_em": agora.isoformat(timespec="seconds")}
    salvar(estado, instance)
    return Midia(novo, nome, pasta, str(raiz)), False


# ============================================================================= estado (instance/backup_externo.json)
def _estado_vazio():
    return {"midias": {}, "ultima_midia": None, "ultima_copia": None, "vistas": [], "vistas_em": None, "ultimo_teste": None,
            "configurado_em": None}


def carregar(instance=PASTA_INSTANCE):
    arquivo = Path(instance) / ARQUIVO_DO_ESTADO
    estado = _estado_vazio()
    try:
        estado.update(json.loads(arquivo.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return estado


def salvar(estado, instance=PASTA_INSTANCE):
    arquivo = Path(instance) / ARQUIVO_DO_ESTADO
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    provisorio = arquivo.with_name(arquivo.name + ".tmp")
    provisorio.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(provisorio, arquivo)


@contextmanager
def bloqueio(instance=PASTA_INSTANCE, agora=None, validade=timedelta(minutes=30)):
    """Uma cópia externa de cada vez (a tarefa das 18:30 e a de hora em hora podem se encontrar). Bloqueio velho é ignorado."""
    arquivo = Path(instance) / ARQUIVO_DO_BLOQUEIO
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    agora = agora or datetime.now()
    try:
        descritor = os.open(arquivo, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        idade = agora - datetime.fromtimestamp(arquivo.stat().st_mtime)
        if idade < validade:
            raise ErroDeCopia("Já tem uma cópia externa em andamento. Tente de novo daqui a pouco.") from None
        arquivo.unlink(missing_ok=True)
        descritor = os.open(arquivo, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(descritor)
    try:
        yield
    finally:
        arquivo.unlink(missing_ok=True)


# ============================================================================= quantas cópias guardar em cada pen-drive
_NOME_DA_COPIA = re.compile(r"^prontuario-(\d{4}-\d{2}-\d{2})_(\d{6})\.pbk$")


def data_da_copia(nome):
    achou = _NOME_DA_COPIA.match(nome)
    return datetime.strptime(achou.group(1) + achou.group(2), "%Y-%m-%d%H%M%S") if achou else None


def quais_apagar(nomes, agora):
    """De uma lista de nomes de cópia, quais saem: guarda as dos últimos 14 dias; depois a mais nova de cada semana (8 semanas);
    depois a mais nova de cada mês, até 1 ano; o resto sai. Nome que não é de cópia nunca entra na conta."""
    datadas = sorted(((data_da_copia(n), n) for n in nomes if data_da_copia(n)), reverse=True)     # da mais nova para a mais velha
    ficam, baldes = set(), set()
    for quando, nome in datadas:
        idade = (agora - quando).days
        if idade < MANTER_DIARIAS:
            ficam.add(nome)
            continue
        if idade < MANTER_DIARIAS + 7 * MANTER_SEMANAS:
            balde = ("semana",) + tuple(quando.isocalendar()[:2])
        elif idade < GUARDAR_ATE_DIAS:
            balde = ("mes", quando.year, quando.month)
        else:
            continue
        if balde not in baldes:             # a primeira que aparece é a mais nova do balde
            baldes.add(balde)
            ficam.add(nome)
    return sorted(n for _, n in datadas if n not in ficam)


def podar_midia(pasta, agora):
    apagadas = quais_apagar([p.name for p in Path(pasta).glob("prontuario-*.pbk")], agora)
    for nome in apagadas:
        (Path(pasta) / nome).unlink(missing_ok=True)
    for sobra in Path(pasta).glob("*.parcial"):
        sobra.unlink(missing_ok=True)
    return len(apagadas)


# ============================================================================= a cópia
def copiar_para_as_midias(arquivo_local, instance=PASTA_INSTANCE, agora=None, raizes=None, log=print):
    """Criptografa `arquivo_local` (o backup do dia) para cada pen-drive preparado que estiver plugado, confere e anota.
    Devolve uma lista de (Midia, resultado): "copiada", "já tinha" ou o texto do erro. Sem frase guardada, não faz nada."""
    agora = agora or datetime.now()
    frase = frase_guardada(instance)
    if not frase:
        raise ErroDeCopia("A cópia externa ainda não foi configurada (falta a frase de recuperação): python backup.py --configurar-externo")
    arquivo_local = Path(arquivo_local)
    resultados = []
    with bloqueio(instance, agora):
        midias = achar_midias(raizes)
        estado = carregar(instance)
        estado["vistas"], estado["vistas_em"] = [m.id for m in midias], agora.isoformat(timespec="seconds")
        for midia in midias:
            ficha = estado["midias"].setdefault(midia.id, {"nome": midia.nome, "preparada_em": agora.isoformat(timespec="seconds")})
            ficha["nome"] = midia.nome
            if ficha.get("ultimo_origem") == arquivo_local.name and (midia.pasta / ficha.get("ultimo_arquivo", "?")).exists():
                resultados.append((midia, "já tinha"))
                continue
            destino = midia.pasta / f"prontuario-{agora:%Y-%m-%d_%H%M%S}.pbk"
            try:
                criptografar(arquivo_local, destino, frase)
                contagem = verificar_copia(destino, frase, Path(instance) / "tmp_backup")
            except (ErroDeCopia, OSError) as erro:
                destino.unlink(missing_ok=True)             # cópia que não abre não fica no pen-drive
                resultados.append((midia, f"falhou: {erro}"))
                log(f"COPIA EXTERNA FALHOU em {midia.nome} ({midia.unidade}): {erro}")
                continue
            if estado.get("ultima_midia") != midia.id:       # trocaram o pen-drive: começa a contar os dias dele no computador
                ficha["desde"] = agora.isoformat(timespec="seconds")
            ficha.setdefault("desde", agora.isoformat(timespec="seconds"))
            ficha.update(ultima_copia=agora.isoformat(timespec="seconds"), ultimo_origem=arquivo_local.name, ultimo_arquivo=destino.name)
            estado["ultima_midia"], estado["ultima_copia"] = midia.id, agora.isoformat(timespec="seconds")
            apagadas = podar_midia(midia.pasta, agora)
            resultados.append((midia, "copiada"))
            resumo = ", ".join(f"{n}: {q}" for n, q in contagem.items())
            log(f"Cópia externa ok em {midia.nome} ({midia.unidade}): {destino.name} ({destino.stat().st_size // 1024} KB; "
                f"conferida, registros — {resumo}). Cópias antigas apagadas: {apagadas}.")
        salvar(estado, instance)
    return resultados


def testar_restauracao(instance=PASTA_INSTANCE, frase=None, arquivo=None, agora=None, raizes=None):
    """O teste de restauração: abre a cópia mais nova (ou `arquivo`) com a frase e confere o banco. Anota o resultado no estado.
    Devolve (arquivo, contagem)."""
    agora = agora or datetime.now()
    frase = frase or frase_guardada(instance)
    if not frase:
        raise ErroDeCopia("Faltou a frase de recuperação.")
    if arquivo is None:
        candidatas = [(data_da_copia(p.name), p) for m in achar_midias(raizes) for p in m.pasta.glob("prontuario-*.pbk") if data_da_copia(p.name)]
        if not candidatas:
            raise ErroDeCopia("Não achei nenhuma cópia nos pen-drives plugados. Plugue um pen-drive preparado ou informe o arquivo com --arquivo.")
        arquivo = max(candidatas)[1]
    arquivo = Path(arquivo)
    contagem = verificar_copia(arquivo, frase, Path(instance) / "tmp_backup")
    estado = carregar(instance)
    estado["ultimo_teste"] = {"em": agora.isoformat(timespec="seconds"), "arquivo": arquivo.name, "registros": contagem}
    salvar(estado, instance)
    return arquivo, contagem


def marcar_configurado(instance=PASTA_INSTANCE, agora=None):
    estado = carregar(instance)
    estado["configurado_em"] = (agora or datetime.now()).isoformat(timespec="seconds")
    salvar(estado, instance)


# ============================================================================= o que a página inicial e a tela de backup mostram
def _quando(texto):
    try:
        return datetime.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def _dias(agora, quando):
    return max((agora - quando).days, 0)


def _dias_de_calendario(agora, quando):
    """Quantos dias do calendário se passaram (plugado na sexta às 18:50, na outra sexta de manhã já são 7)."""
    return max((agora.date() - quando.date()).days, 0)


def pendencias(instance=PASTA_INSTANCE, agora=None):
    """O que está faltando na cópia externa, para o quadro de avisos: lista de (chave, categoria, texto)."""
    agora = agora or datetime.now()
    estado = carregar(instance)
    lista = []
    if not frase_guardada(instance):
        return [("externo:configurar", "Cópia externa do backup",
                 "A cópia criptografada em pen-drive ainda não foi configurada: hoje o backup só existe neste computador. "
                 "Veja o passo a passo em implantacao\\LEIA-ME.md (parte 3).")]
    midias = estado["midias"]
    if not midias:
        return [("externo:preparar", "Cópia externa do backup",
                 "A frase de recuperação já existe, mas nenhum pen-drive foi preparado. Plugue um e prepare-o "
                 "(implantacao\\LEIA-ME.md, parte 3).")]
    ultima = _quando(estado["ultima_copia"])
    atual = midias.get(estado["ultima_midia"] or "", {})
    if ultima is None or (agora - ultima).days > DIAS_SEM_COPIA:
        quando = f"foi em {ultima:%d/%m} (há {_dias(agora, ultima)} dias)" if ultima else "nunca aconteceu"
        lista.append(("externo:atrasada", "Cópia externa do backup",
                      f"A última cópia para o pen-drive {quando}. Ele está plugado no computador do servidor?"))
    else:
        desde = _quando(atual.get("desde"))
        if desde and _dias_de_calendario(agora, desde) >= DIAS_PARA_TROCAR:
            outras = [m["nome"] for k, m in midias.items() if k != estado["ultima_midia"]]
            lista.append(("externo:trocar", "Cópia externa do backup",
                          f"O pen-drive {atual.get('nome', '?')} está plugado há {_dias_de_calendario(agora, desde)} dias. Troque: tire-o, guarde-o trancado e plugue "
                          + (f"o {outras[0]}." if outras else "outro: falta preparar o segundo pen-drive para o rodízio.")))
    vistas = _quando(estado["vistas_em"])
    if len(estado["vistas"]) >= 2 and vistas and (agora - vistas).days <= DIAS_SEM_COPIA:
        lista.append(("externo:duas", "Cópia externa do backup",
                      "Os dois pen-drives estão plugados ao mesmo tempo: um deles precisa ficar guardado, sem estar plugado, senão um vírus, um incêndio ou um roubo leva os dois."))
    primeira = min((_quando(m.get("preparada_em")) for m in midias.values() if _quando(m.get("preparada_em"))), default=None)
    teste = _quando((estado["ultimo_teste"] or {}).get("em"))
    if teste is None and primeira and (agora - primeira).days >= DIAS_ATE_O_PRIMEIRO_TESTE:
        lista.append(("externo:teste", "Cópia externa do backup",
                      "O teste de restauração ainda não foi feito (implantacao\\RESTAURAR.md, parte Treino: leva 2 minutos, com a frase do papel). "
                      "Backup que nunca foi aberto é uma esperança."))
    elif teste and (agora - teste).days >= DIAS_SEM_TESTE:
        lista.append(("externo:teste", "Cópia externa do backup",
                      f"O último teste de restauração foi em {teste:%d/%m/%Y} (há {_dias(agora, teste)} dias). Faça outro: implantacao\\RESTAURAR.md, parte Treino."))
    return lista


def lembrete_de_troca(instance=PASTA_INSTANCE, agora=None):
    """O pop-up da página inicial: hoje é dia de trocar o pen-drive? É na sexta (com o pen-drive plugado há 4 dias ou mais) e, se a
    troca ficou para trás, em qualquer dia a partir do 7º. Devolve {"titulo", "texto", "chave"} ou None. A `chave` é a data de hoje: a
    tela mostra o pop-up uma vez por dia em cada navegador, até a troca ser feita. Sem cópia recente (pen-drive fora) quem cobra é o
    aviso 'atrasada'; sem frase ou sem pen-drive preparado, os avisos de configurar/preparar."""
    agora = agora or datetime.now()
    estado = carregar(instance)
    ultima = _quando(estado["ultima_copia"])
    if not frase_guardada(instance) or not estado["midias"] or ultima is None or (agora - ultima).days > DIAS_SEM_COPIA:
        return None
    atual = estado["midias"].get(estado["ultima_midia"] or "", {})
    desde = _quando(atual.get("desde"))
    if desde is None:
        return None
    dias = _dias_de_calendario(agora, desde)
    sexta = agora.weekday() == DIA_DA_TROCA and dias >= DIAS_MINIMOS_NA_SEXTA
    if not (sexta or dias >= DIAS_PARA_TROCAR):
        return None
    nome = atual.get("nome", "?")
    outras = [m["nome"] for k, m in estado["midias"].items() if k != estado["ultima_midia"]]
    quem = f"o pen-drive {outras[0]}" if outras else "o outro pen-drive (falta preparar o segundo para o rodízio)"
    if (agora.hour, agora.minute) < HORA_DA_TROCA and agora.weekday() == DIA_DA_TROCA:
        texto = (f"Hoje é dia da troca semanal. Depois das {HORA_DA_TROCA[0]}:{HORA_DA_TROCA[1]:02d}, quando o backup do dia terminar, "
                 f"tire o pen-drive {nome}, guarde-o trancado e plugue {quem}.")
    else:
        texto = f"Tire o pen-drive {nome} (plugado há {dias} dias), guarde-o trancado e plugue {quem}."
    return {"titulo": "Hora de trocar o pen-drive do backup", "texto": texto, "chave": f"{agora:%Y-%m-%d}"}


def resumo(instance=PASTA_INSTANCE, agora=None):
    """Para a tela Cadastros > Backup: tudo o que o estado sabe, já em palavras."""
    agora = agora or datetime.now()
    estado = carregar(instance)
    midias = []
    for chave, ficha in estado["midias"].items():
        desde, ultima = _quando(ficha.get("desde")), _quando(ficha.get("ultima_copia"))
        midias.append({"nome": ficha.get("nome", chave[:6]), "preparada_em": _quando(ficha.get("preparada_em")), "desde": desde, "ultima_copia": ultima,
                       "no_computador": chave in estado["vistas"], "atual": chave == estado["ultima_midia"],
                       "dias_no_computador": _dias(agora, desde) if desde and chave == estado["ultima_midia"] else None,
                       "arquivo": ficha.get("ultimo_arquivo", "")})
    midias.sort(key=lambda m: (not m["atual"], m["nome"]))
    teste = estado["ultimo_teste"] or {}
    return {"configurado": bool(frase_guardada(instance)), "midias": midias, "ultima_copia": _quando(estado["ultima_copia"]),
            "ultimo_teste": _quando(teste.get("em")), "ultimo_teste_arquivo": teste.get("arquivo", ""),
            "ultimo_teste_registros": teste.get("registros") or {}, "vistas_em": _quando(estado["vistas_em"]),
            "pendencias": [{"chave": c, "texto": t} for c, _, t in pendencias(instance, agora)]}
