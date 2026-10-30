"""
Validação e formatação de documentos e campos (CPF, RG, CEP, telefone, hora, COREN).

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


# ------------------------------------------------------------------- COREN
UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
       "RR", "SC", "SP", "SE", "TO")
# a categoria vem no fim do número do COREN: ENF enfermeiro(a), TE/TEC técnico(a) de enfermagem, AE/AUX auxiliar, OBS obstetriz
CATEGORIAS_COREN = {"ENF": "enfermeiro(a)", "TE": "técnico(a) de enfermagem", "TEC": "técnico(a) de enfermagem", "AE": "auxiliar de enfermagem",
                    "AUX": "auxiliar de enfermagem", "OBS": "obstetriz"}
_COREN = re.compile(r"^COREN\W*([A-Z]{2})\W*(?:N\.?\W*)?(\d[\d.\s]*)\W*([A-Z]{2,3})$")
EXEMPLO_DE_COREN = "COREN-SP 123.456-ENF"


def ler_coren(texto):
    """'COREN-SP 123456-ENF' (e variações: 'coren/sp nº 123.456 enf'...) -> (forma padrão 'COREN-SP 123.456-ENF', categoria 'ENF'), ou
    (None, None) se não for um COREN completo: precisa da UF (a do conselho regional), do número (3 a 7 dígitos) e da categoria.
    Isto só confere como o número está escrito: o sistema não consulta o Conselho, que não tem consulta automática."""
    bruto = (texto or "").strip().upper().replace("º", " ").replace("°", " ")
    m = _COREN.match(bruto)
    if not m:
        return None, None
    uf, numero, categoria = m.group(1), so_digitos(m.group(2)), m.group(3)
    if uf not in UFS or categoria not in CATEGORIAS_COREN or not 3 <= len(numero) <= 7:
        return None, None
    grupos = []
    while numero:                                    # de três em três, da direita para a esquerda (o número não muda: zero à esquerda fica)
        grupos.insert(0, numero[-3:])
        numero = numero[:-3]
    return f"COREN-{uf} {'.'.join(grupos)}-{categoria}", categoria


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
_ACENTOS_SOLTOS = re.compile("[̀-ͯ]")       # os acentos depois de separados da letra (NFD): agudo, til, cedilha...


def normalizar_nome(t):
    """'  José  da SILVA' -> 'jose da silva' (para comparar e buscar sem acento). É chamada milhares de vezes por busca na lista de internos:
    por isso é uma expressão regular, e não um teste letra por letra."""
    return " ".join(_ACENTOS_SOLTOS.sub("", unicodedata.normalize("NFD", t or "")).lower().split())


# ------------------------------------------------- como nomes e endereços são escritos
# "FULANO FICTICIO DE TAL" ou "fulano ficticio de tal" -> "Fulano Ficticio de Tal". É só uma regra de maiúsculas e minúsculas: acento o
# sistema não adivinha (JOSE pode ser José ou Jose, e o nome tem de ficar como está no documento).
# O mesmo algoritmo existe em static/base.js (formata o campo ao sair dele, para a pessoa ver o resultado); quem decide de verdade é o servidor.
PARTICULAS = ("de", "da", "do", "das", "dos", "e")
_NUMERAL_ROMANO = re.compile(r"X{0,3}(?:IX|IV|V?I{0,3})")        # João Paulo II, Pedro IV...
_SEPARADORES = re.compile(r"([-'’/.])")                           # Maria-Clara, D'Ávila, S/N, Av., J.R.


def _com_inicial_maiuscula(pedaco):
    pedaco = pedaco.lower()
    for i, c in enumerate(pedaco):
        if c.isalpha():
            return pedaco[:i] + c.upper() + pedaco[i + 1:]
    return pedaco


def _uma_linha(texto):
    """Espaços do começo, do fim e repetidos saem; acento solto (o Mac manda a letra e o acento separados) vira o caractere inteiro."""
    return " ".join(unicodedata.normalize("NFC", texto or "").split())


def nome_proprio(texto, siglas=False):
    """'FULANO FICTICIO DE TAL' -> 'Fulano Ficticio de Tal'. De, da, do, das, dos e e ficam em minúsculas (menos no começo); numeral romano
    (II, IV...) fica como veio; Maria-Clara, D'Ávila e S/N levam maiúscula depois do hífen, do apóstrofo e da barra.
    Só mexe no que está TODO em maiúsculas ou TODO em minúsculas: a palavra com letras dos dois jeitos (McDonald, DeSouza) é escolha de quem
    escreveu. `siglas=True` (endereço, cidade, cargo...): palavra em maiúsculas num texto misturado pode ser sigla (CAPS, UBS, "Jardim ABC") e
    fica; só se o texto inteiro estiver em maiúsculas é que as palavras mudam."""
    texto = _uma_linha(texto)
    tudo = texto.isupper() or texto.islower()
    palavras = []
    for i, palavra in enumerate(texto.split()):
        maiuscula, minuscula = palavra.isupper(), palavra.islower()
        solta = palavra.strip(",;:")
        if not ((tudo or minuscula) if siglas else (maiuscula or minuscula)) or re.search(r"\d", palavra):
            palavras.append(palavra)                                  # misturada, sigla ou com número (4B, 1º): fica
        elif i and solta.lower() in PARTICULAS:
            palavras.append(palavra.lower())
        elif maiuscula and len(solta) >= 2 and _NUMERAL_ROMANO.fullmatch(solta):
            palavras.append(palavra)
        else:
            palavras.append("".join(p if j % 2 else _com_inicial_maiuscula(p) for j, p in enumerate(_SEPARADORES.split(palavra))))
    return " ".join(palavras)


def frase(texto):
    """'AUXILIAR DE SERVIÇOS GERAIS' -> 'Auxiliar de serviços gerais': só a primeira letra em maiúscula. Texto que já mistura os dois fica."""
    texto = _uma_linha(texto)
    return _com_inicial_maiuscula(texto) if texto.isupper() or texto.islower() else texto


# como cada campo é escrito: o que vai em `FORMAS` dos modelos e em `Campo.forma` do acolhimento social
FORMAS = {
    "nome": nome_proprio,                                             # nome de pessoa
    "local": lambda texto: nome_proprio(texto, siglas=True),          # rua, bairro, cidade, cargo
    "frase": frase,                                                   # profissão, religião, parentesco...
    "uf": lambda texto: _uma_linha(texto).upper()[:2],
    "email": lambda texto: _uma_linha(texto).lower(),
}


def escrever_bem(forma, texto):
    """O texto do campo na `forma` pedida ('nome', 'local', 'frase', 'uf', 'email'); sem forma, só tira os espaços das pontas."""
    return FORMAS[forma](texto) if forma else (texto or "").strip()


# ------------------------------------------------------------------ avatar
def avatar_da_pessoa(nome):
    """(iniciais, cor de 0 a 7) da bolinha da pessoa: o mesmo cálculo de static/tabela.js (avatar), para a ficha e as listas
    mostrarem a mesma bolinha: primeira e última letras do nome (sem de, da, do...) e uma cor sempre igual para o mesmo nome."""
    palavras = [w for w in (nome or "?").split() if w.lower() not in PARTICULAS] or ["?"]
    iniciais = (palavras[0][0] + (palavras[-1][0] if len(palavras) > 1 else "")).upper()
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", nome or "") if unicodedata.category(c) != "Mn").lower()
    return iniciais, sum(ord(c) for c in sem_acento) % 8
