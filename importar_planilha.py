"""
Importa a planilha antiga (tbl_internos exportada em CSV) para o banco do sistema.

Uso:
    python importar_planilha.py caminho/tbl_internos.csv              # banco vazio
    python importar_planilha.py caminho/tbl_internos.csv --substituir # apaga tudo e reimporta

Cada linha da planilha vira um registro em `internacoes` (triagem ou internação).
Linhas com o mesmo CPF viram UMA pessoa com várias internações (reinternação).
O que ficar estranho não é decidido aqui: aparece no quadro de avisos da home.

Legendas (decididas pelo Luís):
  ativo (status, legenda da aba Triagens):
        1 ativo, 2 inativo, 3 em processo de admissão, 4 lista de espera, 5 desistiu
  convenio:
        1 capsAD, 2 particular, 3 social, 4 taruma, 5 morador, 6 acolhido,
        7 social_parcial1, 8 social_parcial2, 9 á_definir
        -> 1 = CAPS AD, 4 = Prefeitura Tarumã, 2/3/7/8 = Particular (categoria pelo valor)
        -> 5/6/9/vazio = "A definir" se ainda em triagem (admissão/espera); senão Social
"""

import csv
import sys
import unicodedata

from app import app
from modelos import AvisoDispensado, Internacao, Parcela, Pessoa, db
from prontuario import ler_data
from validacao import cpf_valido, limpar_rg, rg_dv_sp_ok, so_digitos

STATUS = {"1": "ativo", "2": "inativo", "3": "em_admissao", "4": "lista_espera", "5": "desistiu"}
EM_TRIAGEM = {"em_admissao", "lista_espera"}
CONVENIO = {"1": "CAPS AD", "4": "Prefeitura Tarumã", "2": "Particular", "3": "Particular",
            "7": "Particular", "8": "Particular"}
MOTIVO = {"conclusao": "Conclusão", "desistencia": "Desistência", "desligamento": "Desligamento"}
MODALIDADE = {"online": "Online", "presencial": "Presencial"}
# correções de UF decididas pelo Luís
UF_CORRIGIDA = {"santo antonio da platina": "PR"}

# ------------------------------------------------------------ texto
PARTICULAS = {"de", "da", "do", "das", "dos", "e"}
ACENTOS = {"medio": "médio", "catolico": "católico", "moveis": "móveis", "mae": "mãe",
           "irma": "irmã", "avo": "avó", "funcionaria": "funcionária",
           "funcionario": "funcionário", "cras": "CRAS", "creas": "CREAS", "candido": "cândido"}


def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn")


def palavras(t):
    """'ensino_medio_completo' -> ['ensino', 'médio', 'completo']"""
    t = (t or "").replace("_", " ").replace("\n", " ").strip()
    if t.lower() == "indefinido":
        return []
    return [ACENTOS.get(p.lower(), p.lower()) for p in t.split()]


def nome_proprio(t):
    """'fulano_de_tal' -> 'Fulano de Tal'"""
    return " ".join(p if (i and p in PARTICULAS) else p[:1].upper() + p[1:]
                    for i, p in enumerate(palavras(t)))


def frase(t):
    """'ensino_medio_completo' -> 'Ensino médio completo'"""
    s = " ".join(palavras(t))
    return s[:1].upper() + s[1:]


def tratar_cpf(bruto):
    """O Excel apaga zeros à esquerda: completa com zeros e só aceita se o dígito conferir.
    Se não conferir, grava como veio (o quadro de avisos aponta)."""
    d = so_digitos(bruto)
    if d and len(d) < 11 and cpf_valido(d.zfill(11)):
        return d.zfill(11)
    return d


# ------------------------------------------------------------ conversão
def dados_pessoa(r):
    cidade = nome_proprio(r["cidade"])
    uf = UF_CORRIGIDA.get(sem_acento(cidade).lower(), r["estado"].strip().upper())
    if sem_acento(cidade).lower() == "santo antonio da platina":
        cidade = "Santo Antônio da Platina"
    return {
        "nome": nome_proprio(r["nome"]),
        "nascimento": r["data_nascimento"],
        "cpf": tratar_cpf(r["cpf"]),
        "rg": r["rg"],
        "cartao_sus": r["cartao_sus"].strip(),
        "estado_civil": frase(r["estado_civil"]),
        "conjuge": nome_proprio(r["conjuge"]),
        "escolaridade": frase(r["escolaridade"]),
        "profissao": frase(r["profissao"]),
        "religiao": frase(r["religiao"]),
        "mae": nome_proprio(r["mae"]),
        "cep": r["cep"],
        "endereco": nome_proprio(r["rua"]),
        "numero": r["num"].strip(),
        "bairro": nome_proprio(r["bairro"]),
        "cidade": cidade,
        "estado": uf,
        # 1 = contato (família), 2 = contato_dois, 3 = contato do próprio acolhido
        "contato1": r["contato"], "contato2": r["contato_dois"], "contato3": r["contato_paciente"],
    }


def dados_internacao(r):
    status = STATUS[r["ativo"]]
    cod = r["convenio"].strip()
    if cod in CONVENIO:
        convenio = CONVENIO[cod]
    else:  # 5 morador, 6 acolhido, 9 a definir, vazio
        convenio = "A definir" if status in EM_TRIAGEM else "Particular"  # Particular + R$ 0 = Social
    return status, {
        "primeiro_contato": r["primeiro_contato"], "hora_primeiro_contato": r["horario_contato"],
        "data_triagem": r["data_triagem"], "hora_triagem": r["horario_triagem"],
        "modalidade": MODALIDADE.get(r["modalidade"].strip().lower(), ""),
        **datas_de_internacao(status, r),
        "termino": r["data_saida"],
        "motivo": MOTIVO.get(sem_acento(r["motivo_saida"]).strip().lower(), ""),
        "resp_nome": nome_proprio(r["responsavel"]), "parentesco": frase(r["relacao"]),
        "resp_rg": r["rg_resp"], "resp_cpf": tratar_cpf(r["cpf_resp"]),
        "convenio": convenio,
        "contribuicao_valor": r["contrib"].strip().replace(",", "."),
    }


def datas_de_internacao(status, r):
    """Na planilha, data_internacao misturava duas coisas. Regra:
    - triagem (admissão/espera/desistência) SEM data de saída: a data era só o
      agendamento — ele não chegou a internar;
    - ativo/inativo, ou desistência COM data de saída: internação efetiva."""
    data, hora = r["data_internacao"], r["horaro_internacao"]
    if status in ("em_admissao", "lista_espera", "desistiu") and not r["data_saida"].strip():
        return {"internacao_agendada": data, "hora_agendada": hora}
    return {"inicio": data, "hora_internacao": hora, "data_documento": data}


def juntar_pessoa(pessoa, novos):
    """Mesma pessoa em outra linha: completa o que está vazio. No RG divergente,
    fica o que passa no dígito verificador de SP."""
    for campo, valor in novos.items():
        atual = getattr(pessoa, campo)
        if not valor:
            continue
        if campo == "rg" and atual and limpar_rg(valor) != atual:
            if rg_dv_sp_ok(valor) and not rg_dv_sp_ok(atual):
                pessoa.preencher({"rg": valor})
            continue
        if not atual:
            pessoa.preencher({campo: valor})


# ------------------------------------------------------------ principal
def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    caminho_csv, substituir = sys.argv[1], "--substituir" in sys.argv

    with open(caminho_csv, encoding="cp1252", newline="") as arq:
        linhas = [r for r in csv.DictReader(arq, delimiter=";")
                  if (r.get("id") or "").strip() and (r.get("nome") or "").strip()]

    with app.app_context():
        existentes = db.session.query(Internacao).count()
        if existentes and not substituir:
            sys.exit(f"O banco já tem {existentes} registros. Use --substituir para apagar e reimportar.")
        if substituir:
            for modelo in (Parcela, Internacao, Pessoa, AvisoDispensado):
                db.session.query(modelo).delete()

        por_cpf = {}
        n_parcelas = 0
        for r in linhas:
            dp = dados_pessoa(r)
            pessoa = por_cpf.get(dp["cpf"]) if dp["cpf"] else None
            if pessoa:
                juntar_pessoa(pessoa, dp)
            else:
                pessoa = Pessoa()
                pessoa.preencher(dp)
                db.session.add(pessoa)
                if dp["cpf"]:
                    por_cpf[dp["cpf"]] = pessoa

            status, di = dados_internacao(r)
            internacao = Internacao(id=int(r["id"]), pessoa=pessoa, status=status)
            internacao.preencher(di)
            db.session.add(internacao)

            valor = float(di["contribuicao_valor"]) if di["contribuicao_valor"] else None
            for n in range(1, 10):
                if r[f"p{n}"].strip():
                    internacao.parcelas.append(Parcela(numero=n, data=ler_data(r[f"p{n}"].strip()),
                                                       valor=valor))
                    n_parcelas += 1
        db.session.commit()

        n_pessoas = db.session.query(Pessoa).count()
        contagem = {s: db.session.query(Internacao).filter_by(status=s).count() for s in STATUS.values()}
        print(f"Registros: {len(linhas)} | pessoas: {n_pessoas} | parcelas: {n_parcelas}")
        print("Por situação:", contagem)


if __name__ == "__main__":
    main()
