"""
Regras de negócio: validar e gravar triagens e prontuários, mudar status,
lançar parcelas e unificar cadastros duplicados.

As rotas (app.py) só chamam estas funções. Cada função de gravação devolve
(objeto, erros): se `erros` vier preenchido, nada foi gravado e o formulário
volta para a tela com as mensagens ao lado de cada campo.
"""

from datetime import date

import catalogo
from modelos import (ENVELOPE_PENDENTE, ENVELOPE_RECEBIDO, STATUS, STATUS_TRIAGEM, Internacao, Parcela,
                     Pessoa, db)
from prontuario import CONVENIO_A_DEFINIR, ler_data, ler_valor
from relatorios import hoje_no_brasil
from validacao import cpf_valido, fmt_cpf, ler_hora, normalizar_nome, rg_valido, so_digitos

MOTIVOS = ["Conclusão", "Desistência", "Desligamento"]


# ------------------------------------------------------------------ validação
def _validar_pessoa(form, pessoa_id):
    erros = {}
    if not (form.get("nome") or "").strip():
        erros["nome"] = "Informe o nome."
    cpf = so_digitos(form.get("cpf"))
    if cpf:
        if not cpf_valido(cpf):
            erros["cpf"] = "CPF inválido (dígito verificador não confere)."
        else:
            outra = db.session.execute(
                db.select(Pessoa).filter(Pessoa.cpf == cpf, Pessoa.id != (pessoa_id or 0))
            ).scalars().first()
            if outra:
                erros["cpf"] = (f"CPF já cadastrado para {outra.nome}. "
                                "Use \"Paciente já cadastrado\" no topo do formulário.")
    if form.get("rg") and not rg_valido(form["rg"]):
        erros["rg"] = "RG inválido: use só números (e X no final, se houver)."
    cep = so_digitos(form.get("cep"))
    if cep and len(cep) != 8:
        erros["cep"] = "CEP deve ter 8 dígitos."
    return erros


def _validar_responsavel(form):
    erros = {}
    if form.get("resp_cpf") and not cpf_valido(form["resp_cpf"]):
        erros["resp_cpf"] = "CPF inválido (dígito verificador não confere)."
    if form.get("resp_rg") and not rg_valido(form["resp_rg"]):
        erros["resp_rg"] = "RG inválido: use só números (e X no final, se houver)."
    return erros


def validar_prontuario(form, pessoa_id=None):
    erros = _validar_pessoa(form, pessoa_id) | _validar_responsavel(form)
    inicio, termino = ler_data(form.get("inicio")), ler_data(form.get("termino"))
    if not inicio:
        erros["inicio"] = "A data em que foi efetivamente internado é obrigatória."
    if termino and inicio and termino < inicio:
        erros["termino"] = "O término não pode ser antes do início."
    if not catalogo.atual().existe(form.get("convenio")):
        erros["convenio"] = "Escolha o convênio."
    return erros


def validar_triagem(form, pessoa_id=None):
    erros = _validar_pessoa(form, pessoa_id) | _validar_responsavel(form)
    contato, agendada = ler_data(form.get("primeiro_contato")), ler_data(form.get("internacao_agendada"))
    if contato and agendada and agendada < contato:
        erros["internacao_agendada"] = "O agendamento não pode ser antes do 1º contato."
    if form.get("status") not in STATUS_TRIAGEM:
        erros["status"] = "Escolha a situação da triagem."
    if not (catalogo.atual().existe(form.get("convenio")) or form.get("convenio") == CONVENIO_A_DEFINIR):
        erros["convenio"] = "Escolha o convênio (ou \"A definir\")."
    return erros


# ------------------------------------------------------------------ gravação
def _pessoa_e_internacao(form):
    """Decide o que criar e o que atualizar, pelos campos ocultos do formulário:
         internacao_id -> editar uma internação/triagem existente
         pessoa_id     -> nova internação de paciente já cadastrado
         nenhum        -> paciente novo"""
    internacao = db.session.get(Internacao, int(form["internacao_id"])) if form.get("internacao_id") else None
    if internacao:
        return internacao.pessoa, internacao
    pessoa = db.session.get(Pessoa, int(form["pessoa_id"])) if form.get("pessoa_id") else None
    return pessoa, None


def salvar_prontuario(form):
    pessoa, internacao = _pessoa_e_internacao(form)
    erros = validar_prontuario(form, pessoa.id if pessoa else None)
    if erros:
        return None, erros

    if pessoa is None:
        pessoa = Pessoa()
        db.session.add(pessoa)
    pessoa.preencher(form)
    if internacao is None:
        internacao = Internacao(pessoa=pessoa)
        db.session.add(internacao)
    era_ativo = internacao.status == "ativo"      # registro novo ainda não tem status: não conta
    internacao.preencher(form)
    if not internacao.data_documento:
        internacao.data_documento = internacao.inicio
    # prontuário salvo = internação: encerrada se tiver término ou motivo
    internacao.status = "inativo" if (internacao.termino or internacao.motivo) else "ativo"
    if internacao.status == "ativo":
        _limpar_envelope(internacao)          # voltou a ser interno: não há envelope para esperar
    elif era_ativo:
        # a baixa veio por aqui, sem a pergunta da janela "Dar baixa": o envelope fica como pendente
        # (um clique em "Chegou" resolve; esquecer um envelope na casa de acolhida é o que se quer evitar)
        _esperar_envelope(internacao)
    db.session.commit()
    return internacao, {}


def salvar_triagem(form):
    pessoa, internacao = _pessoa_e_internacao(form)
    erros = validar_triagem(form, pessoa.id if pessoa else None)
    if erros:
        return None, erros

    if pessoa is None:
        pessoa = Pessoa()
        db.session.add(pessoa)
    pessoa.preencher(form)
    if internacao is None:
        internacao = Internacao(pessoa=pessoa)
        db.session.add(internacao)
    internacao.preencher(form)
    internacao.status = form["status"]
    db.session.commit()
    return internacao, {}


# ------------------------------------------------------------- mudar status
def mudar_status(internacao, dados):
    """Chamado pela lista de triagens. `dados` vem do navegador (JSON).
    'ativo' = Admitido: exige data de internação e convênio definido."""
    novo = dados.get("status")
    if novo in STATUS_TRIAGEM:
        internacao.status = novo
        db.session.commit()
        return {}

    if novo != "ativo":
        return {"status": "Situação inválida."}

    erros = {}
    # data EFETIVA de internação: o dia em que ele de fato entrou (a agendada é só sugestão)
    inicio = ler_data(dados.get("inicio")) or internacao.inicio
    if not inicio:
        erros["inicio"] = "Informe a data em que foi efetivamente internado."
    convenio = dados.get("convenio") or internacao.convenio
    if not catalogo.atual().existe(convenio):
        erros["convenio"] = "Defina o convênio para admitir."
    if erros:
        return erros

    internacao.inicio = inicio
    internacao.hora_internacao = ler_hora(dados.get("hora_internacao")) or internacao.hora_internacao
    internacao.convenio = convenio
    if dados.get("contribuicao_valor") not in (None, ""):
        internacao.contribuicao_valor = ler_valor(dados["contribuicao_valor"])
    internacao.normalizar()
    internacao.data_documento = internacao.data_documento or inicio
    internacao.status = "ativo"
    db.session.commit()
    return {}


# ---------------------------------------------------------------- dar baixa
def dar_baixa(internacao, dados):
    """Dar baixa em quem está ativo: grava a data e o motivo da saída e passa para inativo.
    Pergunta também se o prontuário em papel (o envelope que foi com o interno para a casa de
    acolhida) já voltou ao escritório: se não, a página inicial passa a avisar.
    Chamado pela lista de internos. `dados` vem do navegador (JSON).
    Devolve {campo: mensagem}; vazio = deu certo."""
    if internacao.status != "ativo":
        return {"status": "Só quem está ativo pode receber baixa."}

    erros = {}
    saida = ler_data(dados.get("termino"))
    if not saida:
        erros["termino"] = "Informe a data da saída."
    elif saida > date.today():
        erros["termino"] = "A data da saída não pode ser no futuro."
    elif internacao.inicio and saida < internacao.inicio:
        erros["termino"] = f"A saída não pode ser antes da internação ({internacao.inicio.strftime('%d/%m/%Y')})."
    if dados.get("motivo") not in MOTIVOS:
        erros["motivo"] = "Escolha o motivo."
    voltou = dados.get("prontuario_voltou")
    if voltou not in ("sim", "nao"):
        erros["prontuario_voltou"] = "Informe se o prontuário já voltou ao escritório."
    if erros:
        return erros

    internacao.termino = saida
    internacao.motivo = dados["motivo"]
    internacao.status = "inativo"
    _limpar_envelope(internacao)                  # o que valia de uma baixa anterior (se houve) não vale mais
    if voltou == "sim":
        _envelope_recebido(internacao)
    else:
        _esperar_envelope(internacao)
    db.session.commit()
    return {}


# --------------------------------------------------- envelope do prontuário
def _esperar_envelope(internacao):
    internacao.envelope = ENVELOPE_PENDENTE
    internacao.envelope_recebido_em = None


def _envelope_recebido(internacao):
    internacao.envelope = ENVELOPE_RECEBIDO
    internacao.envelope_recebido_em = internacao.envelope_recebido_em or hoje_no_brasil()   # 2º clique não muda a data


def _limpar_envelope(internacao):
    internacao.envelope = ""
    internacao.envelope_recebido_em = None


def registrar_envelope(internacao, situacao):
    """Marca onde está o envelope de quem já recebeu baixa: 'recebido' (chegou ao escritório) ou
    'pendente' (desfaz um engano, ou começa a controlar uma baixa antiga). Devolve o erro, ou None."""
    if internacao.status != "inativo":
        return "Só quem já recebeu baixa tem prontuário para voltar ao escritório."
    if situacao == ENVELOPE_RECEBIDO:
        _envelope_recebido(internacao)
    elif situacao == ENVELOPE_PENDENTE:
        _esperar_envelope(internacao)
    else:
        return "Situação do prontuário inválida."
    db.session.commit()
    return None


# ------------------------------------------------------------------ parcelas
def lancar_parcela(internacao, form):
    data = ler_data(form.get("data"))
    if not data:
        return "Informe a data da parcela."
    numero = int(form.get("numero") or 0) or (max((p.numero for p in internacao.parcelas), default=0) + 1)
    valor = ler_valor(form.get("valor")) if form.get("valor") else None
    internacao.parcelas.append(Parcela(numero=numero, data=data, valor=valor))
    db.session.commit()
    return None


# ------------------------------------------------------------- unificação
def unificar(manter, remover):
    """Passa as internações de `remover` para `manter`, completa os campos vazios
    de `manter` com os de `remover` e apaga o cadastro duplicado."""
    for coluna in Pessoa.__table__.columns:
        if coluna.name in Pessoa.CAMPOS_DO_SISTEMA:
            continue
        if not getattr(manter, coluna.name) and getattr(remover, coluna.name):
            setattr(manter, coluna.name, getattr(remover, coluna.name))
    for internacao in list(remover.internacoes):
        internacao.pessoa = manter
    db.session.delete(remover)
    db.session.commit()


def buscar_pessoas(termo, limite=10):
    """Busca por nome (sem acento, qualquer parte) ou por CPF."""
    termo_n, termo_d = normalizar_nome(termo), so_digitos(termo)
    if len(termo_n) < 2 and len(termo_d) < 3:
        return []
    achados = []
    for p in db.session.execute(db.select(Pessoa).order_by(Pessoa.nome)).scalars():
        if (termo_n and termo_n in normalizar_nome(p.nome)) or (len(termo_d) >= 3 and termo_d in p.cpf):
            achados.append(p.resumo())
            if len(achados) >= limite:
                break
    return achados


def opcoes_formulario(convenio_atual=""):
    """Listas usadas pelos selects dos formulários. `convenio_atual`: o convênio do registro que está sendo
    editado, que continua na lista mesmo se foi desativado depois."""
    from modelos import MODALIDADES
    from prontuario import CATEGORIA_VALOR_ZERO, DOCUMENTOS, FAIXAS_PARTICULAR, NOME_CURTO
    # o texto "Categoria: ..." que aparece enquanto se digita o valor usa os nomes curtos das telas
    faixas = [(limite, NOME_CURTO.get(nome, nome)) for limite, nome in FAIXAS_PARTICULAR]
    # (valor guardado, nome na tela): o select mostra "Caps AD" e grava "CAPS AD"
    cadastro = catalogo.atual()
    return dict(convenios=cadastro.para_escolher(convenio_atual), gratuitos=cadastro.gratuitos, faixas=faixas,
                categoria_zero=NOME_CURTO[CATEGORIA_VALOR_ZERO], documentos=DOCUMENTOS, motivos=MOTIVOS,
                modalidades=MODALIDADES, a_definir=CONVENIO_A_DEFINIR,
                status_triagem=[(s, STATUS[s]) for s in STATUS_TRIAGEM], hoje=date.today().isoformat(),
                fmt_cpf=fmt_cpf)
