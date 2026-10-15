"""
Senhas fáceis de adivinhar (plano de segurança, fase 3: docs/plano-de-seguranca.md).

Segue a orientação do NIST SP 800-63B: em vez de exigir símbolo e maiúscula (o que leva a "Senha@123"), **barra as senhas que um
atacante tenta primeiro**: as mais usadas no Brasil e no mundo, o nome da casa e do sistema, o nome do usuário e da pessoa, e as
trocas óbvias (maiúscula no começo, número ou símbolo no fim, "a" por "@", "o" por "0"...). A lista fica aqui dentro, sem depender
de internet. O tamanho mínimo é conferido em autenticacao.validar_senha.

    senha_fraca("Senha@123")            -> "É uma senha muito usada..."
    senha_fraca("tres tigres tristes")  -> None
"""

import re
import unicodedata

# as mais usadas (em português e inglês), já na forma "raiz": minúsculas, sem acento, sem símbolos nem número no começo ou no fim
MAIS_USADAS = frozenset("""
senha senhas minhasenha senhasecreta senhaforte senhafraca senhanova mudar mudarsenha trocar trocarsenha segredo secreta
password passw0rd passwd pass pwd secret admin administrador administrator root user usuario login master guest test teste testes
qwerty qwertyuiop qwertyuiopasdfghjkl qwertyui asdf asdfg asdfgh asdfghjkl asdfghjk zxcv zxcvb zxcvbn zxcvbnm azerty qazwsx qazwsxedc
qweasd qweasdzxc qwerasdf abc abcd abcde abcdef abcdefg abcdefgh abcdefghi abcdefghij xyz
abc123 iloveyou loveyou letmein welcome welcome1 monkey dragon baseball football soccer futebol master shadow sunshine princess
superman batman michael jennifer jordan hunter ranger trustno computador computer internet sistema windows
brasil brasileiro brasileira brazil brasilia saopaulo riodejaneiro minasgerais bahia parana curitiba recife salvador fortaleza assis
flamengo corinthians palmeiras santos saopaulofc gremio internacional vasco botafogo fluminense cruzeiro atletico sport bahia
vitoria coritiba goias ceara fortaleza
amor amorzinho meuamor teamo teamomuito amo amoreterno eutequero euteamo felicidade feliz alegria paz fe deus deusefiel deusteama
jesus jesuscristo jesuseamor jesussalva senhor senhorjesus cristo aleluia gloria glorias santo oracao abencoado abencoada bencao
familia minhafamilia mae mamae papai pai filho filha filhos amigo amiga irmao irma gatinho gatinha cachorro princesa principe
lindo linda bonita bonito gostoso gostosa meninas menino menina mulher homem amigos
restauracao restauracaoacolhida acolhida acolhimento associacao casadeacolhida casaacolhida prontuario prontuarios casa
casarestauracao comunidade terapeutica
admin1 admin12 admin123 administrador123 root123 user123 usuario123 teste123 test123
janeiro fevereiro marco abril maio junho julho agosto setembro outubro novembro dezembro verao inverno primavera outono
segunda terca quarta quinta sexta sabado domingo
""".split())

_SEQUENCIAS = ("01234567890123456789", "98765432109876543210", "abcdefghijklmnopqrstuvwxyz", "zyxwvutsrqponmlkjihgfedcba", "qwertyuiopasdfghjklzxcvbnm",
               "1q2w3e4r5t6y7u8i9o0p", "1qaz2wsx3edc4rfv", "qazwsxedcrfvtgb", "asdfghjklzxcvbnm")
_TROCAS = str.maketrans({"@": "a", "4": "a", "3": "e", "1": "i", "!": "i", "0": "o", "$": "s", "5": "s", "7": "t", "8": "b"})


def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _bases(senha):
    """As formas em que a senha pode estar disfarçada: tudo minúsculo e sem acento, sem símbolos, sem número no começo nem no fim, e
    também com as trocas óbvias desfeitas (a=@/4, e=3, i=1/!, o=0, s=$/5)."""
    minuscula = _sem_acento(senha).lower()
    saida = set()
    for texto in (minuscula, minuscula.translate(_TROCAS)):
        so_letras_e_numeros = re.sub(r"[^a-z0-9]", "", texto)
        saida.add(so_letras_e_numeros)
        saida.add(so_letras_e_numeros.strip("0123456789"))            # número no começo ou no fim: "senha2024", "123senha"
        saida.add(re.sub(r"[^a-z]", "", texto))                       # só as letras: "s3nh4-2024"
    # o miolo, sem números nem símbolos nas pontas, e só então as trocas: "p@ssw0rd123" -> "p@ssw0rd" -> "password"
    miolo = re.sub(r"^[^a-z]+", "", re.sub(r"[^a-z]+$", "", minuscula))
    for texto in (miolo, miolo.translate(_TROCAS)):
        saida.add(re.sub(r"[^a-z0-9]", "", texto))
        saida.add(re.sub(r"[^a-z]", "", texto))
    return {b for b in saida if b}


def _em_sequencia(base):
    return len(base) >= 6 and any(base in s for s in _SEQUENCIAS)


def senha_fraca(senha, nomes=()):
    """None se a senha é aceitável; senão, o motivo em palavras. `nomes`: o usuário de login e o nome da pessoa (a senha não pode ser
    o nome nem uma das palavras dele)."""
    texto = senha or ""
    bases = _bases(texto)
    pessoais = set()
    for nome in nomes:
        for parte in re.split(r"[^a-z0-9]+", _sem_acento(nome or "").lower()):
            if len(parte) >= 4:
                pessoais.add(parte)
        completo = re.sub(r"[^a-z0-9]", "", _sem_acento(nome or "").lower())
        if len(completo) >= 4:
            pessoais.add(completo)
    sem_acento_minuscula = re.sub(r"[^a-z0-9]", "", _sem_acento(texto).lower())
    if len(set(sem_acento_minuscula)) < 5:
        return "A senha tem poucos caracteres diferentes (como aaaa1111). Use uma frase com várias palavras."
    if any(b in MAIS_USADAS for b in bases):
        return "Essa senha é muito usada e é das primeiras que um atacante tenta. Use uma frase com várias palavras (ex.: três palavras que só você junta)."
    if any(_em_sequencia(b) for b in bases):
        return "Essa senha é uma sequência fácil de teclas ou números. Use uma frase com várias palavras."
    if any(b in pessoais for b in bases):
        return "A senha não pode ser o seu nome nem o seu usuário. Use uma frase com várias palavras."
    return None
