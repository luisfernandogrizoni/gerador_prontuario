"""
Declarações de internação, uma para cada situação do interno:

  * ativo   -> "Declaração de internação" (encontra-se internado, com o prazo de término);
  * inativo -> "Declaração de ex-interno" (encontrava-se internado, com o período).

O texto vem dos modelos usados no escritório (Declaração de Internação e Declaração de Internação Ex-Internos),
com os erros de digitação corrigidos. Triagens (ainda não internadas) não têm declaração.
"""

import re

from documentos import N, Documento, Paragrafo, Titulo, fecho
from prontuario import fmt_data, previsao_termino
from validacao import fmt_cpf, fmt_rg

ENTIDADE = "COMUNIDADE TERAPÊUTICA CASA DE ACOLHIDA RESTAURAÇÃO"
APRESENTACAO = (" mantida pela Associação Restauração, inscrita no CNPJ sob o n° 03.508.198/0001-07, reconhecida como "
                "Utilidade Pública Municipal pela lei n° 3960/2000, com escritório administrativo situado à Rua "
                "Sebastião da Silva Leite, 1145 em Assis-SP,")
FINALIDADE = "para fins de tratamento da Dependência Química"
CID = " CID F 14/F10."
EM_BRANCO = "_" * 14          # dado que falta no cadastro: fica uma linha para escrever à mão

TIPOS = {"ativo": "interno", "inativo": "ex-interno"}


def tipo_da_declaracao(internacao):
    """'interno' (ativo), 'ex-interno' (inativo) ou None (triagem: não tem declaração)."""
    return TIPOS.get(internacao.status)


def _dado(valor):
    return N(valor) if valor else N(EM_BRANCO)


def _nome_de_arquivo(texto):
    return re.sub(r'[\\/:*?"<>|]+', " ", texto).strip()


def documento(internacao, hoje):
    """Internação ativa ou inativa -> Documento (blocos). Levanta ValueError para triagem."""
    tipo = tipo_da_declaracao(internacao)
    if tipo is None:
        raise ValueError("só internos ativos ou inativos têm declaração")
    pessoa = internacao.pessoa
    identificacao = ["Declaro para devidos fins, e a pedido do interessado ", _dado(pessoa.nome), ", CPF: ",
                     _dado(fmt_cpf(pessoa.cpf) if pessoa.cpf else ""), ", RG: ", _dado(fmt_rg(pessoa.rg) if pessoa.rg else ""),
                     ", DN: ", _dado(fmt_data(pessoa.nascimento)), ", "]
    if tipo == "interno":
        situacao = ["encontra-se internado na ", N(ENTIDADE), APRESENTACAO, " desde o dia ", _dado(fmt_data(internacao.inicio)),
                    f", {FINALIDADE}, com prazo de término no dia ",
                    _dado(fmt_data(previsao_termino(internacao.inicio, internacao.tratamento_ate))), "." + CID]
        titulo = f"Declaração de internação - {pessoa.nome}"
    else:
        situacao = ["encontrava-se internado na ", N(ENTIDADE), APRESENTACAO, " no período de ", _dado(fmt_data(internacao.inicio)),
                    " a ", _dado(fmt_data(internacao.termino)), f", {FINALIDADE}." + CID]
        titulo = f"Declaração de ex-interno - {pessoa.nome}"
    blocos = [Titulo("Declaração", tamanho=14, antes=30, depois=26),
              Paragrafo(identificacao + situacao, "justificado", primeira_linha=708, entrelinha=1.5)]
    blocos += fecho(hoje)
    return Documento(nome_arquivo=_nome_de_arquivo(titulo), titulo=titulo, blocos=blocos, fonte="Verdana", tamanho=10)
