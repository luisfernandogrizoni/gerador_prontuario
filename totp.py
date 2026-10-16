"""
Segundo fator por aplicativo autenticador (plano de segurança, fase 3: docs/plano-de-seguranca.md).

Não é um aplicativo para criar: a pessoa instala no celular um que já existe e é gratuito (Google Authenticator, Microsoft
Authenticator, Authy...), lê o QR code que o sistema mostra **uma vez** e passa a ter, no celular, um número de 6 dígitos que muda
a cada 30 segundos. Depois da senha, o sistema pede esse número. É o TOTP da RFC 6238 (HMAC-SHA1, 6 dígitos, 30 s), que todos esses
aplicativos entendem. SMS fica de fora de propósito: o NIST deixou de aceitá-lo.

  * O segredo de cada pessoa é guardado **cifrado** (Fernet, com uma chave tirada de instance/secret.key, que não vai no banco): um
    backup do banco sozinho não dá o segundo fator de ninguém.
  * Um código só vale **uma vez** (o último passo aceito fica gravado), mesmo dentro da janela de tolerância de ±30 s do relógio.
  * **Códigos de recuperação** (8, de uso único) cobrem o celular perdido; só o resumo (scrypt) deles é guardado.

As bibliotecas `cryptography` (cifra do segredo) e `segno` (desenho do QR) só são carregadas quando usadas: o sistema sobe sem elas.
"""

import base64
import hashlib
import hmac
import json
import re
import secrets
import struct
import time
from urllib.parse import quote

from werkzeug.security import check_password_hash, generate_password_hash

PASSO = 30                  # segundos de cada código
DIGITOS = 6
JANELA = 1                  # aceita o passo anterior e o seguinte (relógio do celular um pouco fora)
EMISSOR = "Prontuario"                # o nome que aparece no aplicativo (curto e sem acento: um QR code menor se lê melhor na tela)
QUANTOS_CODIGOS_DE_RECUPERACAO = 8
ALFABETO = "ABCDEFGHJKMNPQRSTVWXYZ23456789"        # sem 0/O, 1/I/L, U: não se confunde no papel


# ====================================================================== o código
def novo_segredo():
    """20 bytes aleatórios em base32 (32 letras e números): o que o aplicativo guarda."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def _hotp(segredo, contador):
    chave = base64.b32decode(segredo + "=" * (-len(segredo) % 8), casefold=True)
    mac = hmac.new(chave, struct.pack(">Q", contador), hashlib.sha1).digest()
    deslocamento = mac[-1] & 0x0F
    numero = (struct.unpack(">I", mac[deslocamento:deslocamento + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITOS)
    return f"{numero:0{DIGITOS}d}"


def passo_atual(agora=None):
    return int((time.time() if agora is None else agora) // PASSO)


def codigo(segredo, passo):
    """O código de 6 dígitos de um passo de 30 s (usado pelo teste e pela verificação)."""
    return _hotp(segredo, passo)


def verificar(segredo, digitado, ultimo_passo=0, agora=None):
    """Devolve o passo do código digitado se ele vale (certo, dentro da janela e ainda não usado), senão None."""
    texto = re.sub(r"[\s\-]", "", digitado or "")
    if not (texto.isdigit() and len(texto) == DIGITOS):
        return None
    atual, achado = passo_atual(agora), None
    for passo in range(atual - JANELA, atual + JANELA + 1):
        if hmac.compare_digest(_hotp(segredo, passo), texto) and passo > ultimo_passo:      # (confere todos: o tempo não revela qual)
            achado = passo
    return achado


# ====================================================================== o QR e o endereço do aplicativo
def endereco_otpauth(segredo, conta):
    """O endereço otpauth:// que o aplicativo lê (no QR ou digitado): conta = o usuário de login."""
    # (SHA1, 6 dígitos e 30 segundos são o padrão de todos os aplicativos: não precisa dizer, e o endereço curto dá um QR code com menos quadradinhos)
    return f"otpauth://totp/{quote(EMISSOR)}:{quote(conta)}?secret={segredo}&issuer={quote(EMISSOR)}"


def qr_em_svg(endereco):
    """O QR code como SVG (para a página). Precisa da biblioteca `segno`."""
    import segno
    return segno.make(endereco, error="m").svg_inline(scale=6, border=4, dark="#000000", light="#ffffff", title="QR code do autenticador")


def segredo_para_digitar(segredo):
    """O segredo em grupos de 4, para quem digita no aplicativo em vez de ler o QR."""
    return " ".join(segredo[i:i + 4] for i in range(0, len(segredo), 4))


# ====================================================================== guardar o segredo cifrado
def _fernet(chave_mestra):
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"prontuario-totp|" + str(chave_mestra).encode("utf-8")).digest()))


def cifrar(segredo, chave_mestra):
    return _fernet(chave_mestra).encrypt(segredo.encode("ascii")).decode("ascii")


def decifrar(cifrado, chave_mestra):
    """O segredo em claro, ou None se não abre (a chave mudou ou o texto está estragado)."""
    from cryptography.fernet import InvalidToken
    try:
        return _fernet(chave_mestra).decrypt((cifrado or "").encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError):
        return None


# ====================================================================== códigos de recuperação
def gerar_codigos_de_recuperacao():
    """8 códigos de uso único, no formato XXXXX-XXXXX. Devolve (códigos para mostrar uma vez, texto JSON com os resumos para guardar)."""
    codigos = ["".join(secrets.choice(ALFABETO) for _ in range(5)) + "-" + "".join(secrets.choice(ALFABETO) for _ in range(5))
               for _ in range(QUANTOS_CODIGOS_DE_RECUPERACAO)]
    return codigos, json.dumps([generate_password_hash(c.replace("-", "")) for c in codigos])


def _normalizar_recuperacao(texto):
    return re.sub(r"[\s\-]", "", texto or "").upper()


def usar_codigo_de_recuperacao(guardados, digitado):
    """Confere o código digitado com os resumos guardados. Devolve (aceito?, novo texto JSON sem o código usado)."""
    limpo = _normalizar_recuperacao(digitado)
    try:
        resumos = json.loads(guardados or "[]")
    except ValueError:
        resumos = []
    if len(limpo) != 10 or any(c not in ALFABETO for c in limpo):
        return False, guardados
    for i, resumo in enumerate(resumos):
        if check_password_hash(resumo, limpo):
            return True, json.dumps(resumos[:i] + resumos[i + 1:])
    return False, guardados


def quantos_codigos_de_recuperacao(guardados):
    try:
        return len(json.loads(guardados or "[]"))
    except ValueError:
        return 0
