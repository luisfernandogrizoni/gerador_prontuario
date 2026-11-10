"""
Documentos escaneados: o PDF do documento físico, assinado, anexado à ficha de cada triagem ou prontuário.

Como funciona:
  * O arquivo fica em DISCO (instance/anexos/<nº do registro>/<código>.pdf), não no banco: os PDFs são grandes e o backup diário copia o banco inteiro.
    O nome no disco é um código sorteado, nunca o que a pessoa digitou (não há como escapar da pasta). A tabela `anexos` (modelos.Anexo) guarda o título, o
    nome original (só para mostrar), o tamanho, a impressão digital (sha256), quem enviou e quando.
  * **O backup leva os PDFs**: backup.py espelha instance/anexos na pasta de backup (só copia o que ainda não está lá). A cópia externa criptografada dos
    pen-drives continua só com o banco: o original em papel segue guardado, e a cópia de segurança dos PDFs fica no disco do backup.
  * **Só PDF de verdade e inteiro**: começa com %PDF-, termina com %%EOF, até LIMITE_DO_ARQUIVO, sem senha e sem script nem arquivo embutido (um PDF de escaneamento
    comum não tem). É uma conferência do que dá para ver sem abrir o PDF, não um antivírus; quem abre é o leitor de PDF do navegador, que roda isolado.
  * **O mesmo arquivo não entra duas vezes** no mesmo registro (a impressão digital acusa).
  * **Área**: o documento pode ser vinculado a uma área (Saúde, Financeiro, Serviço Social; sem área = geral) e a central de documentos da ficha filtra por ela. Segue o sigilo
    de cada uma (app._pode_ver_area_do_anexo): o do Serviço Social só vai a quem lê o Serviço Social, o de Saúde a quem lê a saúde, o Financeiro a quem tem a
    permissão do financeiro; o geral, a quem tem `documentos`. O administrador vê tudo. Quem não vê uma área também não anexa nela.
  * Quem pode: ver e baixar, quem imprime os documentos do acolhido (permissão `documentos`); anexar e remover, a permissão `anexar`. Remover só esconde (o
    arquivo fica no disco); restaurar e apagar de vez são do administrador, como na lixeira (exclusao.py). Apagar um registro de vez leva os PDFs dele.
  * Toda abertura, download, envio e remoção entra na trilha de auditoria (auditoria.py), sem o nome do arquivo nem o conteúdo.
"""

import hashlib
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

import banco
from modelos import Anexo, db

RAIZ = Path(__file__).resolve().parent
LIMITE_DO_ARQUIVO = 25 * 1024 * 1024              # bytes; um escaneamento de várias páginas em 200 dpi costuma ter de 1 a 8 MB
LIMITE_DA_REQUISICAO = LIMITE_DO_ARQUIVO + 2 * 1024 * 1024        # o arquivo e o resto do formulário (app.py e servidor.py usam como teto do envio)
MAXIMO_POR_REGISTRO = 30
BLOCO = 1 << 20
AREAS = {"": "Geral", "saude": "Saúde", "financeiro": "Financeiro", "social": "Serviço Social"}      # a que área o documento está vinculado; "" = sem área
AREAS_SIGILOSAS = ("saude", "social")        # quem não lê o relatório da área não vê nem anexa nela (app._pode_ver_area_do_anexo)
TITULOS_SUGERIDOS = ("Prontuário assinado", "Termo de compromisso", "Termo de responsabilidade", "Documento do responsável", "Outro documento")

_NOME_NO_DISCO = re.compile(r"^[0-9a-f]{32}\.pdf$")
_ATIVO = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|RichMedia)\b")      # script, programa a abrir e arquivos escondidos dentro do PDF
_COM_SENHA = re.compile(rb"/Encrypt\b")


class ErroDeAnexo(Exception):
    """Algo que a pessoa pode corrigir (arquivo errado, grande demais...): a mensagem vai para ela, sem detalhe técnico."""


# ------------------------------------------------------------------ onde ficam
def pasta():
    return banco.pasta_dos_anexos(RAIZ / "instance")


def pasta_do_registro(internacao_id):
    return pasta() / str(int(internacao_id))


def caminho(anexo):
    """O arquivo no disco. Confere o nome guardado (um código e .pdf) para um valor adulterado no banco não apontar para fora da pasta."""
    if not _NOME_NO_DISCO.match(anexo.arquivo or ""):
        raise ErroDeAnexo("O registro deste anexo está inválido.")
    return pasta_do_registro(anexo.internacao_id) / anexo.arquivo


# ------------------------------------------------------------------ o que mostrar
def tamanho_legivel(bytes_):
    """1234567 -> '1,2 MB'; 52000 -> '51 KB'."""
    if bytes_ < 1024 * 1024:
        return f"{max(1, round(bytes_ / 1024))} KB"
    return f"{bytes_ / (1024 * 1024):.1f}".replace(".", ",") + " MB"


def limpar_area(valor):
    """A área que veio do formulário: uma das AREAS, ou "" (geral) se não for nenhuma."""
    valor = (valor or "").strip()
    return valor if valor in AREAS else ""


def do_registro(internacao, com_removidos=False):
    """Os anexos do registro, do mais antigo para o mais novo; os removidos só se pedir (quem pode restaurar)."""
    return [a for a in internacao.anexos if com_removidos or a.excluido_em is None]


def achar(internacao, anexo_id, com_removidos=False):
    """O anexo `anexo_id` DESTE registro (um número de outro registro não serve), ou None."""
    return next((a for a in do_registro(internacao, com_removidos) if a.id == anexo_id), None)


def nome_para_baixar(anexo):
    """'Prontuário assinado.pdf': o título, sem o que o Windows não aceita num nome de arquivo."""
    nome = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", anexo.titulo or "").strip(" .-") or "Documento escaneado"
    return nome[:100] + ".pdf"


def _nome_para_mostrar(nome):
    nome = (nome or "").replace("\\", "/").rsplit("/", 1)[-1]
    return "".join(c for c in nome if c.isprintable()).strip()[:200]


# ------------------------------------------------------------------ receber o arquivo
def _receber(entrada, pasta_do_arquivo):
    """Grava o que veio do navegador num arquivo provisório, conferindo no caminho. Devolve (arquivo provisório, tamanho, sha256) ou levanta ErroDeAnexo
    (sem deixar rastro no disco)."""
    pasta_do_arquivo.mkdir(parents=True, exist_ok=True)
    provisorio = pasta_do_arquivo / f".{uuid.uuid4().hex}.parcial"
    impressao, total, cabeca, cauda = hashlib.sha256(), 0, b"", b""
    try:
        with open(provisorio, "wb") as saida:
            while True:
                bloco = entrada.read(BLOCO)
                if not bloco:
                    break
                total += len(bloco)
                if total > LIMITE_DO_ARQUIVO:
                    raise ErroDeAnexo(f"O arquivo passa de {LIMITE_DO_ARQUIVO // (1024 * 1024)} MB. Escaneie de novo com resolução menor (150 a 200 dpi bastam).")
                if len(cabeca) < 8:
                    cabeca = (cabeca + bloco)[:8]
                cauda = (cauda + bloco)[-2048:]
                impressao.update(bloco)
                saida.write(bloco)
        if total == 0:
            raise ErroDeAnexo("O arquivo está vazio.")
        if not cabeca.startswith(b"%PDF-"):
            raise ErroDeAnexo("O arquivo não é um PDF. Só PDF é aceito.")
        if b"%%EOF" not in cauda:
            raise ErroDeAnexo("O PDF parece incompleto ou corrompido (o final do arquivo não está lá). Escaneie ou salve de novo.")
        conteudo = provisorio.read_bytes()
        if _COM_SENHA.search(conteudo):
            raise ErroDeAnexo("O PDF está protegido por senha. Envie uma cópia sem senha.")
        if _ATIVO.search(conteudo):
            raise ErroDeAnexo("O PDF tem script ou arquivo embutido, que o sistema não aceita. Escaneie de novo: um PDF de escaneamento comum não tem isso.")
    except BaseException:
        provisorio.unlink(missing_ok=True)
        raise
    return provisorio, total, impressao.hexdigest()


def guardar(internacao, arquivo, titulo, usuario, area=""):
    """Anexa o PDF `arquivo` (o que o Flask entrega em request.files) ao registro, vinculado a `area` (veja AREAS). Devolve o Anexo; com um problema que a pessoa
    corrige, levanta ErroDeAnexo e nada fica gravado nem no disco nem no banco."""
    if arquivo is None or not (arquivo.filename or "").strip():
        raise ErroDeAnexo("Escolha o arquivo PDF.")
    if len(internacao.anexos) >= MAXIMO_POR_REGISTRO:
        raise ErroDeAnexo(f"Este registro já tem {MAXIMO_POR_REGISTRO} documentos anexados.")
    pasta_do_arquivo = pasta_do_registro(internacao.id)
    provisorio, tamanho, impressao = _receber(arquivo.stream, pasta_do_arquivo)
    final = None
    try:
        repetido = next((a for a in internacao.anexos if a.sha256 == impressao), None)
        if repetido is not None:
            raise ErroDeAnexo("Este arquivo já está anexado a este registro." if repetido.excluido_em is None
                              else "Este arquivo já foi anexado e removido. Peça ao administrador para restaurá-lo.")
        nome = _nome_para_mostrar(arquivo.filename)
        titulo = " ".join((titulo or "").split())[:100] or re.sub(r"\.pdf$", "", nome, flags=re.I)[:100] or "Documento escaneado"
        final = pasta_do_arquivo / f"{uuid.uuid4().hex}.pdf"
        os.replace(provisorio, final)
        anexo = Anexo(internacao=internacao, titulo=titulo, area=limpar_area(area), nome_original=nome, arquivo=final.name, tamanho=tamanho, sha256=impressao,
                      enviado_em=datetime.now(), enviado_por=(usuario or "")[:50])
        db.session.add(anexo)
        db.session.commit()
        return anexo
    except BaseException:
        db.session.rollback()
        provisorio.unlink(missing_ok=True)
        if final is not None:
            final.unlink(missing_ok=True)
        raise


def mudar_area(anexo, area):
    """Vincula o documento a outra área (ou tira o vínculo: area = ""). Só mexe na área: o arquivo e o resto continuam."""
    anexo.area = limpar_area(area)
    db.session.commit()


# ------------------------------------------------------------------ remover, restaurar, apagar
def remover(anexo, usuario=""):
    """Esconde da ficha (o arquivo continua no disco)."""
    anexo.excluido_em, anexo.excluido_por = datetime.now(), (usuario or "")[:50]
    db.session.commit()


def restaurar(anexo):
    anexo.excluido_em, anexo.excluido_por = None, ""
    db.session.commit()


def apagar(anexo):
    """Apaga o registro do anexo e o arquivo, de vez."""
    arquivo, pasta_do_arquivo = caminho(anexo), pasta_do_registro(anexo.internacao_id)
    db.session.delete(anexo)
    db.session.commit()
    arquivo.unlink(missing_ok=True)
    _limpar_pasta_vazia(pasta_do_arquivo)


def arquivos_do_registro(internacao):
    """Os arquivos de todos os anexos do registro (inclusive removidos): para apagar junto com o registro (exclusao.apagar)."""
    return [caminho(a) for a in internacao.anexos if _NOME_NO_DISCO.match(a.arquivo or "")]


def apagar_arquivos(internacao_id, arquivos):
    """Depois de o banco gravar o fim do registro: tira os arquivos e a pasta dele do disco."""
    for arquivo in arquivos:
        arquivo.unlink(missing_ok=True)
    _limpar_pasta_vazia(pasta_do_registro(internacao_id))


def _limpar_pasta_vazia(pasta_do_arquivo):
    try:
        pasta_do_arquivo.rmdir()
    except OSError:
        pass                                                  # ainda tem arquivo (ou não existe): fica
