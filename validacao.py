"""
Validação e formatação de documentos e campos (CPF, RG, CEP, telefone, hora).

Regra usada no sistema inteiro:
  - no banco, documentos ficam "limpos" (CPF e CEP só com dígitos, RG com dígitos e X);
  - na tela e no .docx, aparecem formatados (000.000.000-00, 00.000.000-0, 00000-000).

O mesmo algoritmo de CPF existe em static/formularios.js para avisar enquanto se
digita; quem decide de verdade é o servidor (cpf_valido, aqui).
"""

import re
import unicodedata
from datetime import time


def so_digitos(texto):
    return "".join(c for c in (texto or "") if c.isdigit())


# ------------------------------------------------------------------- CPF
def cpf_valido(cpf):
    """Confere os dois dígitos verificadores. Aceita com ou sem pontuação."""
    d = so_digitos(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def fmt_cpf(texto):
    """Aplica a máscara 000.000.000-00 quando vierem 11 dígitos."""
    d = so_digitos(texto)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return texto or ""


# -------------------------------------------------------------------- RG
# RG não tem padrão nacional (SP tem dígito verificador, PR não segue o mesmo).
# Por isso a validação é de formato: só dígitos, com X opcional no final.
RG_FORMATO = re.compile(r"^\d{5,13}X?$")


def limpar_rg(texto):
    return re.sub(r"[^0-9X]", "", (texto or "").upper())


def rg_valido(texto):
    return bool(RG_FORMATO.match(limpar_rg(texto)))


def rg_dv_sp_ok(texto):
    """Dígito verificador do RG de SP (8 dígitos + DV). Usado só para desempatar."""
    r = limpar_rg(texto)
    if len(r) != 9 or not r[:8].isdigit():
        return False
    resto = 11 - sum(int(c) * p for c, p in zip(r[:8], range(2, 10))) % 11
    return r[8] == {10: "X", 11: "0"}.get(resto, str(resto))


def fmt_rg(texto):
    """9 caracteres (8 dígitos + DV) -> 00.000.000-0; outros tamanhos ficam como estão."""
    r = limpar_rg(texto)
    if len(r) == 9:
        return f"{r[:2]}.{r[2:5]}.{r[5:8]}-{r[8]}"
    return r


# ------------------------------------------------------------- CEP, telefone
def fmt_cep(texto):
    d = so_digitos(texto)
    return f"{d[:5]}-{d[5:]}" if len(d) == 8 else d


def fmt_telefone(texto):
    d = so_digitos(texto)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return (texto or "").strip()


# ------------------------------------------------------------------- hora
def ler_hora(texto):
    """'14:00', '9:30' ou '14:00:00' -> time; vazio/inválido -> None."""
    texto = (texto or "").strip()
    if re.match(r"^\d:\d\d", texto):  # '9:30' -> '09:30'
        texto = "0" + texto
    try:
        return time.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def fmt_hora(h):
    return h.strftime("%H:%M") if h else ""


# ------------------------------------------------------------------ busca
def normalizar_nome(t):
    """'  José  da SILVA' -> 'jose da silva' (para comparar e buscar sem acento)."""
    t = unicodedata.normalize("NFD", t or "")
    return " ".join("".join(c for c in t if unicodedata.category(c) != "Mn").lower().split())
