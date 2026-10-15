"""
Sistema de Prontuários — Casa de Acolhida Restauração

Telas:
    /login, /sair, /senha           entrar, sair e alterar a própria senha (todo o resto exige login)
    /                               home: indicadores, vagas por categoria, avisos e agenda dos próximos dias
    /triagens                       lista de triagens (muda a situação pelo navegador)
    /triagens/nova                  formulário de triagem (?pessoa=<id> = paciente já cadastrado)
    /internos                       lista de internos (ativos / inativos); "Dar baixa" muda para inativo
                                    e pergunta se o prontuário em papel já voltou ao escritório (avisos.py cobra)
    /prontuario/novo                formulário do prontuário (?pessoa=<id> = paciente já cadastrado)
    /internacoes/<id>               ficha: dados, parcelas, outras internações, ações
    /internacoes/<id>/editar        abre o formulário certo (triagem ou prontuário) já preenchido
    /internacoes/<id>/envelope      marca se o prontuário em papel de quem recebeu baixa já voltou ao escritório
    /relatorios                     relatórios (internos ativos por convênio; passaram pela casa no ano, com colunas
                                    opcionais por convênio e quem assina escolhido na própria tela)
    /cadastros/convenios            cadastro de convênios (nome, vagas, cor): um convênio novo aparece sozinho em
                                    formulários, vagas e relatórios
    /cadastros/funcionarios         cadastro de funcionários: quem assina como responsável pela emissão dos documentos;
                                    o administrador também cria o usuário e a senha de cada um e escolhe o nível de acesso
    /cadastros/niveis               níveis de acesso, em cascata (do que tem mais acesso para o que tem menos); o
                                    primeiro é o do administrador, e só ele altera os níveis
    /cadastros/permissoes           o que cada nível pode fazer (nível mínimo de cada permissão); só o administrador altera
    /cadastros/backup               (administrador) o backup do dia, os pen-drives em rodízio e o teste de restauração
    /internacoes/<id>/prontuario    baixa o .docx
    /internacoes/<id>/impressos     os impressos da triagem (pedido de exames, enxoval) e da internação (prontuário, manual
                                    de orientação, ficha multiprofissional, capa do envelope, relatório do Serviço Social)
                                    num documento só
    /internacoes/<id>/relatorio-social   o acolhimento social: a assistente social preenche a ficha, escreve o relatório, classifica
                                    o risco e dá o parecer no sistema (sigiloso: só Serviço Social e administrador); finalizar
                                    trava e um parecer "não condizente" marca a triagem como "Rejeitado na triagem"
    /internacoes/<id>/relatorio-social/adendo   correção ou informação nova num acolhimento já finalizado
    /internacoes/<id>/excluir      exclui o registro: o operador só tira de circulação; o administrador também apaga de vez
    /cadastros/lixeira              (administrador) o que foi excluído: restaurar ou apagar do banco

Organização:
    validacao.py   CPF, RG, CEP, telefone, hora
    prontuario.py  regras do documento e geração do .docx
    modelos.py     tabelas (pessoas, internacoes, parcelas)
    servicos.py    regras de negócio: validar, gravar, mudar status, parcelas
    avisos.py      quadro de avisos
    copia_externa.py  cópia criptografada do backup em pen-drives em rodízio (usada pelo backup.py)
    permissoes.py  o que cada nível de acesso pode fazer e a regra de cada rota (nega por padrão)
    catalogo.py    o que o sistema sabe de cada convênio (lido do cadastro, uma vez por requisição)
    cadastros.py   cadastros de convênios e de funcionários
    fichas.py      pedido de exames, enxoval, capa do envelope e ficha multiprofissional (em branco)
    manual_de_orientacao.py  o manual que a família recebe na internação (o texto fica lá)
    servico_social.py  o acolhimento social: perguntas, classificação, parecer, gravação e documento
    exclusao.py   excluir em duas etapas: some de tudo sem sair do banco, até o administrador apagar de vez
    impressos.py   reúne os impressos de cada acolhido num documento só
    vagas.py       ocupação das vagas por categoria
    painel.py      números e agenda dos próximos dias da página inicial
    autenticacao.py  login: usuários, senhas, sessão e proteção das rotas
    banco.py       onde fica o banco (SQLite local ou Postgres da hospedagem)
    copiar_banco.py  leva os dados do SQLite local para o banco da hospedagem
    verificar_vazamento.py  confere se algum dado de interno foi parar no git
    app.py         este arquivo: só liga as rotas às partes acima

ATENÇÃO: o banco guarda dados pessoais sensíveis e NUNCA vai para o git (instance/ está
no .gitignore; na hospedagem o banco é externo, via DATABASE_URL — veja banco.py).
Toda tela e todo dado exigem login (o administrador cria os usuários em Cadastros > Funcionários;
veja autenticacao.py para o primeiro usuário e para as variáveis de ambiente da hospedagem) e, depois do login, a
permissão do nível de acesso da pessoa (permissoes.REGRAS: rota sem regra fica fechada). Em produção use HTTPS e um servidor de
verdade (gunicorn app:app) — `python app.py` é só para uso local.
"""

import os
from datetime import date, datetime

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file,
                   session, url_for)
from werkzeug.exceptions import HTTPException

import autenticacao
import banco
import cadastros as cadastros_
import catalogo
import copia_externa
import declaracoes
import documentos
import exclusao
import impressos
import painel
import permissoes
import relatorios
import servico_social
import servicos
from avisos import dias_de_espera, gerar_avisos, tempo_decorrido
from banco import arquivo_ultimo_backup
from modelos import (ENVELOPE_RECEBIDO, STATUS_INTERNACAO, STATUS_TRIAGEM, AvisoDispensado, Convenio, Funcionario,
                     Internacao, NivelAcesso, Parcela, Pessoa, db)
from migracoes import migrar
from prontuario import (calcular_idade, faixas_do_particular, fmt_data, fmt_reais, gerar_docx, montar_documento,
                        previsao_termino)
from validacao import avatar_da_pessoa, fmt_cep, fmt_cpf, fmt_hora, fmt_rg
from vagas import gerar_vagas, totais

app = Flask(__name__)
# o banco fica fora do git: SQLite local por padrão, ou o que estiver em DATABASE_URL (banco.py)
app.config["SQLALCHEMY_DATABASE_URI"] = banco.url_do_banco()
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = banco.opcoes_do_motor(app.config["SQLALCHEMY_DATABASE_URI"])
app.config["SECRET_KEY"] = autenticacao.chave_secreta(app.instance_path)  # assina a sessão do login
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,       # o JavaScript da página não lê o cookie
    SESSION_COOKIE_SAMESITE="Lax",      # o navegador não manda o cookie em POST vindo de outro site
    # só trafega por HTTPS, exceto em desenvolvimento e na rede interna do escritório, que usa http
    # (servidor.py liga SESSAO_SEM_HTTPS=1; em hospedagem com HTTPS a variável não existe)
    SESSION_COOKIE_SECURE=not app.debug and os.environ.get("SESSAO_SEM_HTTPS") != "1",
    SESSION_REFRESH_EACH_REQUEST=False,    # o login não se renova sozinho: vale 10 h e acabou
    PERMANENT_SESSION_LIFETIME=autenticacao.DURACAO_LOGIN,
)
db.init_app(app)

with app.app_context():
    db.create_all()   # cria as tabelas que ainda não existem
    migrar(db)        # acrescenta colunas novas em bancos antigos
    autenticacao.criar_usuario_inicial()

app.before_request(autenticacao.exigir_login)
app.before_request(permissoes.exigir_permissao)     # depois do login: a rota pede uma permissão e a pessoa tem? (permissoes.REGRAS)
app.after_request(autenticacao.cabecalhos_de_seguranca)
autenticacao.registrar_comandos(app)
def _e_administrador():
    """O usuário logado é o administrador? (cadastros.pode_gerenciar_acessos: enquanto nenhum administrador tem usuário
    vinculado, vale para quem está logado.) Guardado por requisição: as telas perguntam várias vezes."""
    return permissoes.e_administrador()


def _pode_servico_social():
    """O usuário logado lê e escreve o acolhimento social (ficha, relatório e parecer)? Só o Serviço Social e o
    administrador (cadastros.pode_servico_social). Guardado por requisição, como _e_administrador."""
    if "pode_servico_social" not in g:
        g.pode_servico_social = cadastros_.pode_servico_social(g.get("usuario"))
    return g.pode_servico_social


# pode('triagem') nos templates esconde o que a pessoa não pode usar; permissoes_js() leva o mesmo ao JavaScript das listas
app.context_processor(lambda: {"usuario_atual": g.get("usuario"), "e_administrador": _e_administrador(),
                               "pode_servico_social": _pode_servico_social(),
                               "pode": permissoes.pode, "permissoes_js": permissoes.do_usuario})

# filtros usados nos templates: {{ p.cpf | cpf }}, {{ i.inicio | data }} ...
app.jinja_env.filters.update(cpf=fmt_cpf, rg=fmt_rg, cep=fmt_cep, data=fmt_data, hora=fmt_hora,
                             reais=lambda v: fmt_reais(v or 0.0))


def _buscar(modelo, id):
    return db.session.get(modelo, id) or abort(404)


# Páginas de erro na mesma linguagem do resto do sistema (templates/erro.html). O que é de API (JSON) segue com a resposta padrão.
MENSAGENS_DE_ERRO = {
    400: ("Pedido inválido", "O sistema não entendeu o que foi enviado. Volte e tente de novo."),
    403: ("Sem permissão", "Você não tem permissão para abrir esta página."),
    404: ("Página não encontrada", "O endereço não existe, ou o registro foi excluído."),
    405: ("Ação não permitida", "Esta página não aceita essa ação."),
    500: ("Algo deu errado", "O sistema não conseguiu concluir. Tente de novo e, se continuar, avise o administrador."),
}


@app.errorhandler(HTTPException)
def pagina_de_erro(erro):
    if erro.code is None or erro.code < 400 or request.path.startswith("/api/") or request.is_json:     # redirecionamentos e API seguem como são
        return erro
    titulo, texto = MENSAGENS_DE_ERRO.get(erro.code, ("Não foi possível abrir", "Volte para o início e tente de novo."))
    return render_template("erro.html", codigo=erro.code, titulo=titulo, texto=texto), erro.code


@app.errorhandler(Exception)
def erro_interno(erro):
    """Erro de verdade (um bug): registra o que aconteceu e mostra a página, sem detalhe técnico. Em desenvolvimento
    (debug), deixa o depurador do Flask mostrar tudo."""
    if app.debug:
        raise erro
    app.logger.exception("Erro não tratado em %s", request.path)
    return render_template("erro.html", codigo=500, titulo=MENSAGENS_DE_ERRO[500][0], texto=MENSAGENS_DE_ERRO[500][1]), 500


def _dados_para_novo(pessoa_id):
    """Formulário novo; se veio ?pessoa=<id>, já traz os dados do paciente."""
    if not pessoa_id:
        return {}, None
    pessoa = _buscar(Pessoa, pessoa_id)
    dados = pessoa.como_formulario()
    dados["pessoa_id"] = str(pessoa.id)
    return dados, pessoa


# ==================================================================== login
@app.route("/login", methods=["GET", "POST"])
def login():
    if g.usuario:
        return redirect(url_for("home"))
    proximo = request.values.get("next", "")
    if request.method == "POST":
        usuario, erro = autenticacao.entrar(request.form.get("usuario"), request.form.get("senha"))
        if usuario and cadastros_.acesso_desativado(usuario):     # a senha confere, mas o funcionário foi desativado
            usuario, erro = None, "Este acesso foi desativado. Procure o administrador."
        if usuario:
            autenticacao.abrir_sessao(usuario)
            return redirect(autenticacao.destino_seguro(proximo, url_for("home")))
        return render_template("login.html", erro=erro, proximo=proximo), 401
    return render_template("login.html", erro=None, proximo=proximo)


@app.post("/sair")
def sair():
    session.clear()
    return redirect(url_for("login"))


@app.route("/senha", methods=["GET", "POST"])
def alterar_senha():
    erro = None
    if request.method == "POST":
        erro = autenticacao.trocar_senha(g.usuario, request.form.get("atual"),
                                         request.form.get("nova"), request.form.get("confirmacao"))
        if not erro:
            autenticacao.abrir_sessao(g.usuario)   # a sessão de agora continua valendo
            flash("Senha alterada.")
            return redirect(url_for("home"))
    return render_template("senha.html", erro=erro, minimo=autenticacao.SENHA_MINIMA)


# ===================================================================== home
@app.get("/")
def home():
    hoje = date.today()
    lista_de_vagas = gerar_vagas()
    return render_template("home.html", avisos=gerar_avisos(_pode_servico_social()), vagas=lista_de_vagas, vagas_total=totais(lista_de_vagas),
                           resumo=painel.resumo(), agenda=painel.agenda(hoje=hoje),
                           para_imprimir=painel.impressos_da_internacao(hoje=hoje) if permissoes.pode("documentos") else {"total": 0, "itens": []},
                           dias_da_agenda=painel.DIAS_DA_AGENDA, fim_do_tratamento=painel.tratamentos_a_finalizar(hoje=hoje),
                           hoje_por_extenso=painel.data_por_extenso(hoje),
                           na_lixeira=exclusao.quantos_excluidos() if _e_administrador() else 0)     # o que os operadores excluíram


@app.post("/avisos/ciente")
def aviso_ciente():
    chave = request.form["chave"]
    if not db.session.get(AvisoDispensado, chave):
        db.session.add(AvisoDispensado(chave=chave))
        db.session.commit()
    return redirect(url_for("home") + "#avisos")


@app.post("/pessoas/<int:manter>/unificar/<int:remover>")
def unificar_pessoas(manter, remover):
    servicos.unificar(_buscar(Pessoa, manter), _buscar(Pessoa, remover))
    flash("Cadastros unificados.")
    return redirect(url_for("home") + "#avisos")


@app.get("/api/pessoas")
def api_pessoas():
    return jsonify(servicos.buscar_pessoas(request.args.get("q", "")))


# ================================================================= triagens
@app.get("/triagens")
def lista_triagens():
    # novo = triagem recém-gravada (a linha é destacada); imprimir = 1 pergunta se imprime exames e enxoval dela
    return render_template("triagens.html", novo=request.args.get("novo", type=int),
                           imprimir=request.args.get("imprimir", type=int), **servicos.opcoes_formulario())


@app.get("/api/triagens")
def api_triagens():
    itens = db.session.execute(
        db.select(Internacao).filter(Internacao.status.in_(STATUS_TRIAGEM))
        .order_by(Internacao.primeiro_contato.desc().nulls_last(), Internacao.id.desc())).scalars()
    pode = _pode_servico_social()       # a classificação de risco é do sigilo do Serviço Social: só vai para quem pode vê-la
    return jsonify([{**i.para_triagem(), **({"classificacao": servico_social.classificacao(i.relatorio_social)} if pode else {})}
                    for i in itens])


@app.get("/triagens/nova")
def nova_triagem():
    dados, pessoa = _dados_para_novo(request.args.get("pessoa", type=int))
    dados.setdefault("primeiro_contato", servicos.opcoes_formulario()["hoje"])
    return render_template("triagem_form.html", d=dados, erros={}, pessoa=pessoa,
                           **servicos.opcoes_formulario())


@app.post("/triagens/salvar")
def salvar_triagem():
    internacao, erros = servicos.salvar_triagem(request.form)
    if erros:
        pessoa = db.session.get(Pessoa, request.form.get("pessoa_id", type=int) or 0)
        return render_template("triagem_form.html", d=request.form, erros=erros, pessoa=pessoa,
                               **servicos.opcoes_formulario(request.form.get("convenio", ""))), 400
    # internação marcada: a lista pergunta se é para imprimir o pedido de exames e o enxoval (até alguém imprimir)
    return redirect(url_for("lista_triagens", novo=internacao.id, imprimir=1 if _perguntar_impressao(internacao) else None))


def _perguntar_impressao(internacao):
    """Triagem com a internação marcada (hoje ou depois) cujo pedido de exames e enxoval ainda não foram impressos para essa
    data. Remarcar a data pergunta de novo; imprimir (impressos.py) anota a data e a pergunta para."""
    return bool(internacao.status in painel.NA_TRIAGEM and internacao.internacao_agendada
                and internacao.internacao_agendada >= date.today()
                and internacao.exames_impressos_para != internacao.internacao_agendada)


@app.post("/triagens/<int:id>/status")
def mudar_status(id):
    internacao = _buscar(Internacao, id)
    erros = servicos.mudar_status(internacao, request.get_json(force=True))
    if erros:
        return jsonify(ok=False, erros=erros), 400
    return jsonify(ok=True, status=internacao.status, ficha=url_for("ficha", id=id), editar=url_for("editar_internacao", id=id),
                   acolhimento=url_for("relatorio_social", id=id) if _pode_servico_social() else None)


# ================================================================== internos
@app.get("/internos")
def lista_internos():
    # novo = registro recém-gravado (a linha é destacada); baixar = 1 baixa o .docx dele
    return render_template("internos.html", novo=request.args.get("novo", type=int),
                           baixar=request.args.get("baixar", type=int), motivos=servicos.MOTIVOS)


@app.get("/api/internos")
def api_internos():
    itens = db.session.execute(
        db.select(Internacao).filter(Internacao.status.in_(STATUS_INTERNACAO))
        .order_by(Internacao.inicio.desc().nulls_last(), Internacao.id.desc())).scalars()
    return jsonify([i.para_lista() for i in itens])


@app.post("/internacoes/<int:id>/baixa")
def baixa_interno(id):
    internacao = _buscar(Internacao, id)
    erros = servicos.dar_baixa(internacao, request.get_json(force=True))
    if erros:
        return jsonify(ok=False, erros=erros), 400
    return jsonify(ok=True, status=internacao.status_txt, saida=fmt_data(internacao.termino),
                   envelope=internacao.envelope, ficha=url_for("ficha", id=id))


@app.post("/internacoes/<int:id>/envelope")
def registrar_envelope(id):
    """Onde está o prontuário em papel de quem recebeu baixa. Chamado pelo quadro de avisos (voltar=home)
    e pelo cartão da ficha."""
    internacao = _buscar(Internacao, id)
    erro = servicos.registrar_envelope(internacao, request.form.get("situacao"))
    if erro:
        flash(erro)
    elif internacao.envelope == ENVELOPE_RECEBIDO:
        flash(f"Prontuário de {internacao.pessoa.nome} registrado como recebido no escritório.")
    else:
        flash(f"Prontuário de {internacao.pessoa.nome} registrado como ainda na casa de acolhida.")
    if request.form.get("voltar") == "home":
        return redirect(url_for("home") + "#avisos")
    return redirect(url_for("ficha", id=id) + "#envelope")


@app.get("/prontuario/novo")
def formulario():
    dados, pessoa = _dados_para_novo(request.args.get("pessoa", type=int))
    anterior = pessoa.ultima_internacao if pessoa else None
    return render_template("formulario.html", d=dados, erros={}, pessoa=pessoa, anterior=anterior,
                           **servicos.opcoes_formulario())


@app.post("/prontuario/salvar")
def gerar():
    internacao, erros = servicos.salvar_prontuario(request.form)
    if erros:
        pessoa = db.session.get(Pessoa, request.form.get("pessoa_id", type=int) or 0)
        return render_template("formulario.html", d=request.form, erros=erros, pessoa=pessoa,
                               anterior=None, **servicos.opcoes_formulario(request.form.get("convenio", ""))), 400
    # Post/Redirect/Get: a lista destaca a linha e, se foi "Salvar e baixar", baixa o .docx
    baixar = 1 if request.form.get("acao") == "baixar" and permissoes.pode("documentos") else None
    return redirect(url_for("lista_internos", novo=internacao.id, baixar=baixar))


# ===================================================================== ficha
@app.get("/internacoes/<int:id>")
def ficha(id):
    internacao = _buscar(Internacao, id)
    dias, atrasado = dias_de_espera(internacao)
    p, hoje = internacao.pessoa, relatorios.hoje_no_brasil()
    permanencia = ((hoje if internacao.status == "ativo" else internacao.termino) - internacao.inicio).days \
        if internacao.inicio and (internacao.status == "ativo" or internacao.termino) else None
    return render_template("ficha.html", i=internacao, envelope_atrasado=atrasado,
                           envelope_tempo=tempo_decorrido(dias) if dias is not None else "",
                           acolhimento=_resumo_do_acolhimento(internacao),
                           idade=calcular_idade(p.nascimento, hoje),
                           previsao=previsao_termino(internacao.inicio, internacao.tratamento_ate) if internacao.inicio else None,
                           permanencia=_duracao(permanencia) if permanencia is not None and permanencia >= 0 else "",
                           avatar=avatar_da_pessoa(p.nome))


def _duracao(dias):
    """Quanto tempo, em palavras: '12 dias', '8 meses', '1 ano e 3 meses' (o cabeçalho da ficha mostra quanto ficou ou está internado)."""
    if dias < 60:
        return f"{dias} dia{'' if dias == 1 else 's'}"
    meses = round(dias / 30.44)
    if meses < 24:
        return f"{meses} meses"
    anos, resto = divmod(meses, 12)
    return f"{anos} anos" + (f" e {resto} mese{'s' if resto > 1 else ''}" if resto else "")


def _resumo_do_acolhimento(internacao):
    """O que a ficha mostra do acolhimento social. Quem não é do Serviço Social (nem administrador) só fica sabendo se
    foi feito e quando: a classificação, o parecer, quem escreveu e os adendos são do sigilo."""
    relatorio = internacao.relatorio_social
    situacao = servico_social.estado(relatorio)
    resumo = {"estado": situacao, "em": None}
    if situacao:
        resumo["em"] = relatorio.finalizado_em if situacao == "finalizado" else relatorio.atualizado_em
    if situacao and _pode_servico_social():
        resumo.update(por=(relatorio.assinatura or relatorio.finalizado_por) if situacao == "finalizado" else relatorio.atualizado_por,
                      risco=servico_social.classificacao(relatorio), parecer=servico_social.resposta(relatorio, "parecer"),
                      adendos=list(relatorio.adendos))
    return resumo


@app.get("/internacoes/<int:id>/editar")
def editar_internacao(id):
    internacao = _buscar(Internacao, id)
    dados = internacao.dados_completos() | {"internacao_id": str(internacao.id),
                                            "pessoa_id": str(internacao.pessoa_id),
                                            "status": internacao.status}
    modelo = "triagem_form.html" if internacao.e_triagem else "formulario.html"
    return render_template(modelo, d=dados, erros={}, pessoa=internacao.pessoa, anterior=None,
                           editando=internacao, **servicos.opcoes_formulario(internacao.convenio))


@app.get("/internacoes/<int:id>/prontuario")
def baixar_prontuario(id):
    arquivo, nome = gerar_docx(_buscar(Internacao, id).dados_completos())
    return send_file(arquivo, as_attachment=True, download_name=nome)


@app.post("/internacoes/<int:id>/parcelas")
def lancar_parcela(id):
    erro = servicos.lancar_parcela(_buscar(Internacao, id), request.form)
    flash(erro or "Parcela lançada.")
    return redirect(url_for("ficha", id=id) + "#parcelas")


@app.post("/parcelas/<int:id>/excluir")
def excluir_parcela(id):
    parcela = _buscar(Parcela, id)
    internacao_id = parcela.internacao_id
    db.session.delete(parcela)
    db.session.commit()
    flash("Parcela excluída.")
    return redirect(url_for("ficha", id=internacao_id) + "#parcelas")


# ============================================================== documentos
# Cada documento tem três saídas: ver no navegador (com botão de imprimir), imprimir direto (?imprimir=1)
# e baixar o .docx. Todos nascem do mesmo motor (documentos.py), com o mesmo timbre.
def _emissor():
    """Quem assina o documento: ?emissor=<id> na página, senão o funcionário do usuário logado, senão o padrão.
    Devolve (Emissor, id do funcionário)."""
    return cadastros_.emissor_para(g.get("usuario"), request.args.get("emissor", type=int))


def _escolha_de_emissor():
    """O ?emissor= que a pessoa escolheu na tela (None se não escolheu): é o que os botões e o download repetem."""
    return request.args.get("emissor", type=int)


def _barra(emissor_id, colunas=()):
    """Opções que aparecem acima do documento (só na tela): quem assina, se houver mais de um funcionário ativo,
    e os botões de colunas do relatório anual. `colunas` = [(convênio, ativa, endereço de quem clicar), ...]."""
    ativos = [f for f in cadastros_.funcionarios() if f.ativo]
    return {"emissor_id": emissor_id,
            "emissores": [(f.id, f"{f.nome} — {f.cargo}") for f in ativos] if len(ativos) > 1 else [],
            "colunas": [{"nome": c.nome_tela, "tipo": c.cor, "ativa": ativa, "url": url} for c, ativa, url in colunas],
            "manter": {k: v for k, v in request.args.items() if k == "colunas"}}


def _mostrar(doc, docx, voltar, avisos=(), barra=None):
    doc.voltar = voltar
    return render_template("documento.html", doc=doc, docx=docx, avisos=avisos, cabecalho=documentos.CABECALHO,
                           rodape=documentos.RODAPE, barra=barra or {})


def _baixar(doc):
    return send_file(documentos.para_docx(doc), as_attachment=True, download_name=doc.nome_arquivo + ".docx")


def _declaracao(id, emissor):
    internacao = _buscar(Internacao, id)
    if declaracoes.tipo_da_declaracao(internacao) is None:      # triagem ainda não é interno: não há o que declarar
        abort(404)
    return declaracoes.documento(internacao, relatorios.hoje_no_brasil(), emissor)


@app.get("/internacoes/<int:id>/prontuario/visualizar")
def ver_prontuario(id):
    doc = montar_documento(_buscar(Internacao, id).dados_completos())
    return _mostrar(doc, url_for("baixar_prontuario", id=id), url_for("ficha", id=id))


@app.get("/internacoes/<int:id>/declaracao")
def ver_declaracao(id):
    emissor, emissor_id = _emissor()
    return _mostrar(_declaracao(id, emissor), url_for("baixar_declaracao", id=id, emissor=_escolha_de_emissor()),
                    url_for("ficha", id=id), barra=_barra(emissor_id))


@app.get("/internacoes/<int:id>/declaracao.docx")
def baixar_declaracao(id):
    return _baixar(_declaracao(id, _emissor()[0]))


# Os impressos da triagem (pedido de exames, enxoval) e da internação (prontuário, ficha multiprofissional, capa do
# envelope, relatório do Serviço Social) saem num documento só; ?itens=a,b escolhe quais (veja impressos.py).
def _impresso(id):
    internacao = _buscar(Internacao, id)
    itens = impressos.ler_itens(request.args.get("itens"), internacao, _pode_servico_social())
    return internacao, itens, impressos.documento(internacao, itens, relatorios.hoje_no_brasil())


def _anotar_impressao(internacao, itens):
    """Pedido de exames ou enxoval impresso (ou baixado): anota para qual data de internação, e a pergunta ao salvar a
    triagem para de aparecer (a data mudando, ela volta)."""
    if ({"exames", "enxoval"} & set(itens)) and internacao.internacao_agendada \
            and internacao.exames_impressos_para != internacao.internacao_agendada:
        internacao.exames_impressos_para = internacao.internacao_agendada
        db.session.commit()


@app.get("/internacoes/<int:id>/impressos")
def ver_impressos(id):
    internacao, itens, doc = _impresso(id)
    if request.args.get("imprimir"):                      # só quem vai imprimir; ver o documento não conta como impresso
        _anotar_impressao(internacao, itens)
    barra = {"itens": impressos.barra(internacao, itens, lambda novos: url_for("ver_impressos", id=id, itens=",".join(novos)),
                                      _pode_servico_social())}
    return _mostrar(doc, url_for("baixar_impressos", id=id, itens=",".join(itens)), url_for("ficha", id=id), barra=barra)


@app.get("/internacoes/<int:id>/impressos.docx")
def baixar_impressos(id):
    internacao, itens, doc = _impresso(id)
    _anotar_impressao(internacao, itens)
    return _baixar(doc)


# ------------------------------------------------------- acolhimento social
# Ficha, relatório livre, classificação de risco e parecer da assistente social (servico_social.py). Sigiloso: só o
# Serviço Social e o administrador abrem; os outros veem na ficha se foi feito (e a folha-resumo nos impressos).
def _so_servico_social(id):
    """Quem não é do Serviço Social (nem administrador) volta para a ficha com o aviso, sem ver nada do conteúdo."""
    flash("O acolhimento social é sigiloso: só a assistente social e o administrador abrem.")
    return redirect(url_for("ficha", id=id))


def _tela_relatorio(internacao, form, erros, status=200):
    relatorio = internacao.relatorio_social
    acolhido, responsavel = servico_social.identificacao(internacao, relatorios.hoje_no_brasil())
    valores = servico_social.valores_do_formulario(form, servico_social.campos_para(internacao)) if form is not None \
        else servico_social.valores(internacao, relatorio, servico_social.campos_para(internacao))
    anterior = servico_social.anterior(internacao) if relatorio is None and form is None else None      # readmissão: de onde vieram as respostas
    return render_template("servico_social_form.html", i=internacao, secoes=servico_social.secoes_para(internacao), visual=servico_social.VISUAL, v=valores, erros=erros,
                           relatorio=relatorio, acolhido=acolhido, responsavel=responsavel, anterior=anterior), status


@app.route("/internacoes/<int:id>/relatorio-social", methods=["GET", "POST"])
def relatorio_social(id):
    internacao = _buscar(Internacao, id)
    if not _pode_servico_social():
        return _so_servico_social(id)
    relatorio = internacao.relatorio_social
    if relatorio is not None and relatorio.finalizado:          # finalizado não se edita: abre o documento (e o adendo é na ficha)
        if request.method == "POST":
            flash("Este acolhimento social já foi finalizado. Para corrigir ou acrescentar, escreva um adendo.")
            return redirect(url_for("ficha", id=id) + "#acolhimento")
        return redirect(url_for("ver_impressos", id=id, itens="relatorio-social"))
    if request.method == "POST":
        acao = request.form.get("acao")
        _, erros = servicos.salvar_relatorio_social(internacao, request.form, _nome_do_usuario(), finalizar=acao == "finalizar",
                                                    assinatura=cadastros_.assinatura_do_usuario(g.get("usuario")))
        if erros:
            return _tela_relatorio(internacao, request.form, erros, 400)
        if acao == "finalizar":
            flash("Acolhimento social finalizado." + (f" {internacao.pessoa.nome} foi marcado como rejeitado na triagem."
                                                      if internacao.status == "rejeitado" else ""))
            return redirect(url_for("ficha", id=id) + "#acolhimento")
        if acao == "imprimir":
            return redirect(url_for("ver_impressos", id=id, itens="relatorio-social", imprimir=1))
        flash("Rascunho salvo.")
        return redirect(url_for("relatorio_social", id=id))
    return _tela_relatorio(internacao, None, {})


@app.post("/internacoes/<int:id>/relatorio-social/adendo")
def adendo_social(id):
    internacao = _buscar(Internacao, id)
    if not _pode_servico_social():
        return _so_servico_social(id)
    erro = servicos.adicionar_adendo(internacao, request.form.get("texto"), cadastros_.assinatura_do_usuario(g.get("usuario")))
    flash(erro or "Adendo registrado.")
    return redirect(url_for("ficha", id=id) + "#acolhimento")


@app.get("/internacoes/<int:id>/rejeicao")
def relatorio_de_rejeicao(id):
    """O relatório de rejeição virou o parecer do acolhimento social: o endereço antigo continua levando para lá."""
    return redirect(url_for("relatorio_social", id=id))


# ----------------------------------------------------------- excluir registros
# Quem não é administrador só "exclui": o registro some das telas e continua no banco. O administrador vê o que foi
# excluído na lixeira (Cadastros), restaura ou apaga de vez, e também pode apagar de vez direto da ficha (exclusao.py).
def _nome_do_usuario():
    return g.usuario.nome if g.get("usuario") else ""


@app.post("/internacoes/<int:id>/excluir")
def excluir_registro(id):
    internacao = _buscar(Internacao, id)
    nome, volta = internacao.pessoa.nome, "lista_triagens" if internacao.e_triagem else "lista_internos"
    if request.form.get("acao") == "apagar":
        if not _e_administrador():
            flash("Só o administrador pode apagar um registro do banco.")
            return redirect(url_for("ficha", id=id))
        with exclusao.vendo_tudo():
            exclusao.apagar(internacao)
        flash(f"Registro de {nome} apagado do banco.")
    else:
        exclusao.excluir(internacao, _nome_do_usuario())
        flash(f"Registro de {nome} excluído.")
    return redirect(url_for(volta))


@app.get("/cadastros/lixeira")
def lixeira():
    if not _e_administrador():
        flash("Só o administrador vê a lixeira.")
        return redirect(url_for("home"))
    with exclusao.vendo_tudo():
        return render_template("lixeira.html", registros=exclusao.excluidos())


def _registro_excluido(id):
    """O registro que está na lixeira, ou volta para a lixeira com aviso (só o administrador mexe nela)."""
    if not _e_administrador():
        flash("Só o administrador restaura ou apaga registros da lixeira.")
        return None
    with exclusao.vendo_tudo():
        return db.session.get(Internacao, id) or abort(404)


@app.post("/internacoes/<int:id>/restaurar")
def restaurar_registro(id):
    if (internacao := _registro_excluido(id)) is None:
        return redirect(url_for("home"))
    with exclusao.vendo_tudo():
        nome = internacao.pessoa.nome
        exclusao.restaurar(internacao)
    flash(f"Registro de {nome} restaurado.")
    return redirect(url_for("lixeira"))


@app.post("/internacoes/<int:id>/apagar")
def apagar_registro(id):
    if (internacao := _registro_excluido(id)) is None:
        return redirect(url_for("home"))
    with exclusao.vendo_tudo():
        nome = internacao.pessoa.nome
        exclusao.apagar(internacao)
    flash(f"Registro de {nome} apagado do banco.")
    return redirect(url_for("lixeira"))


# ================================================================ relatórios
@app.get("/relatorios")
def pagina_relatorios():
    hoje = relatorios.hoje_no_brasil()
    anual = relatorios.resumo_anual(hoje)
    return render_template("relatorios.html", blocos=relatorios.painel(), hoje=hoje, anual=anual,
                           aviso_anual=relatorios.aviso_do_resumo(anual))


def _relatorio_do_convenio(slug, emissor):
    if relatorios.convenio_do_relatorio(slug) is None:
        abort(404)
    return relatorios.documento_convenio(slug, relatorios.hoje_no_brasil(), emissor)


@app.get("/relatorios/internos-ativos/<slug>")
def ver_relatorio(slug):
    emissor, emissor_id = _emissor()
    return _mostrar(_relatorio_do_convenio(slug, emissor), url_for("baixar_relatorio", slug=slug, emissor=_escolha_de_emissor()),
                    url_for("pagina_relatorios"), barra=_barra(emissor_id))


@app.get("/relatorios/internos-ativos/<slug>.docx")
def baixar_relatorio(slug):
    return _baixar(_relatorio_do_convenio(slug, _emissor()[0]))


def _colunas_do_relatorio_anual(hoje):
    """Os convênios pedidos em ?colunas=caps-ad,taruma (só os que existem, na ordem do cadastro) e todos os que
    podem ser pedidos. Um convênio novo cadastrado aparece aqui sozinho."""
    disponiveis = relatorios.colunas_disponiveis(hoje)
    pedidos = set(request.args.get("colunas", "").split(","))
    return [c for c in disponiveis if c.slug in pedidos], disponiveis


@app.get("/relatorios/passaram-pela-casa")
def ver_relatorio_anual():
    hoje = relatorios.hoje_no_brasil()
    emissor, emissor_id = _emissor()
    escolhidas, disponiveis = _colunas_do_relatorio_anual(hoje)
    ativas = {c.slug for c in escolhidas}

    def endereco(slugs, endpoint="ver_relatorio_anual"):
        # a ordem das colunas é sempre a do cadastro, qualquer que seja a ordem dos cliques
        ordenados = [c.slug for c in disponiveis if c.slug in slugs]
        return url_for(endpoint, colunas=",".join(ordenados) or None, emissor=_escolha_de_emissor())

    botoes = [(c, c.slug in ativas, endereco(ativas - {c.slug} if c.slug in ativas else ativas | {c.slug}))
              for c in disponiveis]
    return _mostrar(relatorios.documento_anual(hoje, escolhidas, emissor), endereco(ativas, "baixar_relatorio_anual"),
                    url_for("pagina_relatorios"), barra=_barra(emissor_id, botoes),
                    avisos=[t for t in (relatorios.aviso_do_resumo(relatorios.resumo_anual(hoje)),) if t])


@app.get("/relatorios/passaram-pela-casa.docx")
def baixar_relatorio_anual():
    hoje = relatorios.hoje_no_brasil()
    return _baixar(relatorios.documento_anual(hoje, _colunas_do_relatorio_anual(hoje)[0], _emissor()[0]))


# ================================================================= cadastros
@app.get("/cadastros")
def cadastros():
    return redirect(url_for("lista_convenios"))


@app.get("/cadastros/convenios")
def lista_convenios():
    ativos = {nome: n for nome, n in db.session.execute(
        db.select(Internacao.convenio, db.func.count()).filter(Internacao.status == "ativo").group_by(Internacao.convenio))}
    por_categoria = {v["categoria"]: v for v in gerar_vagas()}      # vagas e internos ativos de cada faixa do Particular
    faixas = [{"categoria": categoria, "valor": valor, **{k: por_categoria[categoria][k] for k in ("tipo", "limite", "ocupadas")}}
              for categoria, valor in faixas_do_particular()]
    return render_template("cadastro_convenios.html", convenios=cadastros_.convenios(), internos_ativos=ativos, faixas=faixas)


def _convenio_editavel(id):
    convenio = _buscar(Convenio, id)
    if not convenio.gratuito:       # o Particular é definido pelo valor da contribuição: não tem o que editar
        abort(404)
    return convenio


@app.route("/cadastros/convenios/novo", methods=["GET", "POST"])
def novo_convenio():
    if request.method == "POST":
        convenio, erros = cadastros_.salvar_convenio(request.form)
        if not erros:
            flash(f"Convênio {convenio.nome_tela} cadastrado. Ele já aparece nos formulários, nas vagas e nos relatórios.")
            return redirect(url_for("lista_convenios"))
        return render_template("cadastro_convenio_form.html", d=request.form, erros=erros, convenio=None,
                               cores=catalogo.CORES), 400
    return render_template("cadastro_convenio_form.html", d={"cor": cadastros_.cor_automatica(), "vagas": ""},
                           erros={}, convenio=None, cores=catalogo.CORES)


@app.route("/cadastros/convenios/<int:id>/editar", methods=["GET", "POST"])
def editar_convenio(id):
    convenio = _convenio_editavel(id)
    if request.method == "POST":
        _, erros = cadastros_.salvar_convenio(request.form, convenio)
        if not erros:
            flash(f"Convênio {convenio.nome_tela} atualizado.")
            return redirect(url_for("lista_convenios"))
        return render_template("cadastro_convenio_form.html", d=request.form, erros=erros, convenio=convenio,
                               cores=catalogo.CORES), 400
    dados = {"nome_tela": convenio.nome_tela, "vagas": "" if convenio.vagas is None else convenio.vagas,
             "cor": convenio.cor, "ativo": "1" if convenio.ativo else ""}
    return render_template("cadastro_convenio_form.html", d=dados, erros={}, convenio=convenio, cores=catalogo.CORES)


@app.get("/cadastros/funcionarios")
def lista_funcionarios():
    return render_template("cadastro_funcionarios.html", funcionarios=cadastros_.funcionarios())


def _tela_funcionario(funcionario, dados, erros, status=200):
    """Formulário de funcionário. Nunca devolve a senha digitada (um erro em outro campo não a mostra de volta)."""
    login = funcionario.usuario if funcionario is not None and autenticacao.buscar_usuario(funcionario.usuario) else ""
    nivel = funcionario.nivel.nome if funcionario is not None and funcionario.nivel else ""
    if funcionario is None:
        nivel = next((n for i, n in cadastros_.niveis_para_escolher() if i == cadastros_.nivel_para_novo_funcionario()), "")
    dados = {k: v for k, v in dados.items() if k not in ("senha", "confirmacao")}
    return render_template("cadastro_funcionario_form.html", d=dados, erros=erros, funcionario=funcionario,
                           usuarios=cadastros_.usuarios_para_vincular(funcionario), niveis=cadastros_.niveis_para_escolher(funcionario),
                           pode_acessos=cadastros_.pode_gerenciar_acessos(g.usuario), login_atual=login, nivel_atual=nivel), status


@app.route("/cadastros/funcionarios/novo", methods=["GET", "POST"])
def novo_funcionario():
    if request.method == "POST":
        pode = cadastros_.pode_gerenciar_acessos(g.usuario)
        funcionario, erros = cadastros_.salvar_funcionario(request.form, por=g.usuario)
        if not erros:
            flash(f"{funcionario.nome} cadastrado(a)." + cadastros_.frase_do_acesso(request.form, pode, funcionario.usuario))
            return redirect(url_for("lista_funcionarios"))
        return _tela_funcionario(None, request.form, erros, 400)
    return _tela_funcionario(None, {"ativo": "1", "nivel_id": cadastros_.nivel_para_novo_funcionario()}, {})


@app.route("/cadastros/funcionarios/<int:id>/editar", methods=["GET", "POST"])
def editar_funcionario(id):
    funcionario = _buscar(Funcionario, id)
    if request.method == "POST":
        pode = cadastros_.pode_gerenciar_acessos(g.usuario)
        _, erros = cadastros_.salvar_funcionario(request.form, funcionario, por=g.usuario)
        if not erros:
            if pode and request.form.get("senha") and funcionario.usuario == g.usuario.nome:
                autenticacao.abrir_sessao(g.usuario)    # trocou a própria senha: a sessão de agora continua valendo
            flash(f"{funcionario.nome} atualizado(a)." + cadastros_.frase_do_acesso(request.form, pode, funcionario.usuario))
            return redirect(url_for("lista_funcionarios"))
        return _tela_funcionario(funcionario, request.form, erros, 400)
    dados = {"nome": funcionario.nome, "cargo": funcionario.cargo, "usuario": funcionario.usuario,
             "nivel_id": str(funcionario.nivel_id or ""), "ativo": "1" if funcionario.ativo else "",
             "padrao": "1" if funcionario.padrao else "", "servico_social": "1" if funcionario.servico_social else "",
             "registro_profissional": funcionario.registro_profissional}
    return _tela_funcionario(funcionario, dados, {})


@app.get("/cadastros/niveis")
def lista_niveis():
    em_uso = {nivel_id: n for nivel_id, n in db.session.execute(
        db.select(Funcionario.nivel_id, db.func.count()).filter(Funcionario.ativo.is_(True)).group_by(Funcionario.nivel_id))}
    return render_template("cadastro_niveis.html", niveis=cadastros_.niveis(), funcionarios_por_nivel=em_uso,
                           pode_acessos=cadastros_.pode_gerenciar_acessos(g.usuario))


# A situação do backup (só o administrador): o do dia, os pen-drives em rodízio e o teste de restauração (copia_externa.py).
@app.get("/cadastros/backup")
def pagina_backup():
    try:
        ultimo = datetime.fromisoformat(arquivo_ultimo_backup(app.instance_path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        ultimo = None
    return render_template("cadastro_backup.html", externo=copia_externa.resumo(app.instance_path), ultimo_backup=ultimo, agora=datetime.now())


# O que cada nível pode fazer (permissoes.py). Quem tem "cadastros" vê; só o administrador ("acessos") altera.
@app.get("/cadastros/permissoes")
def lista_permissoes():
    niveis, grupos = permissoes.matriz()
    return render_template("cadastro_permissoes.html", niveis=niveis, grupos=grupos, pode_acessos=permissoes.pode("acessos"),
                           acolhimento_social=permissoes.ACOLHIMENTO_SOCIAL)


@app.post("/cadastros/permissoes")
def salvar_permissoes():
    erros, mudaram = permissoes.salvar_matriz(request.form, _nome_do_usuario())
    if erros:
        flash(" ".join(erros.values()))
    elif mudaram:
        flash(f"Permissões salvas ({mudaram} alterada{'s' if mudaram != 1 else ''}).")
    else:
        flash("Nada mudou.")
    return redirect(url_for("lista_permissoes"))


def _so_administrador(destino):
    """None se quem está logado pode mexer nos acessos; senão avisa e devolve o redirecionamento para `destino`."""
    if cadastros_.pode_gerenciar_acessos(g.usuario):
        return None
    flash("Só o administrador pode alterar os níveis de acesso.")
    return redirect(url_for(destino))


@app.route("/cadastros/niveis/novo", methods=["GET", "POST"])
def novo_nivel():
    if negado := _so_administrador("lista_niveis"):
        return negado
    if request.method == "POST":
        nivel, erros = cadastros_.salvar_nivel(request.form)
        if not erros:
            flash(f"Nível {nivel.nome} cadastrado, no fim da cascata (o de menos acesso).")
            return redirect(url_for("lista_niveis"))
        return render_template("cadastro_nivel_form.html", d=request.form, erros=erros, nivel=None), 400
    return render_template("cadastro_nivel_form.html", d={}, erros={}, nivel=None)


@app.route("/cadastros/niveis/<int:id>/editar", methods=["GET", "POST"])
def editar_nivel(id):
    nivel = _buscar(NivelAcesso, id)
    if negado := _so_administrador("lista_niveis"):
        return negado
    if request.method == "POST":
        _, erros = cadastros_.salvar_nivel(request.form, nivel)
        if not erros:
            flash(f"Nível {nivel.nome} atualizado.")
            return redirect(url_for("lista_niveis"))
        return render_template("cadastro_nivel_form.html", d=request.form, erros=erros, nivel=nivel), 400
    dados = {"nome": nivel.nome, "descricao": nivel.descricao, "ativo": "1" if nivel.ativo else ""}
    return render_template("cadastro_nivel_form.html", d=dados, erros={}, nivel=nivel)


@app.post("/cadastros/niveis/<int:id>/mover")
def mover_nivel(id):
    nivel = _buscar(NivelAcesso, id)
    if negado := _so_administrador("lista_niveis"):
        return negado
    if cadastros_.mover_nivel(nivel, request.form.get("sentido", "")):
        flash(f"{nivel.nome} {'subiu' if request.form['sentido'] == 'cima' else 'desceu'} na cascata.")
    return redirect(url_for("lista_niveis"))


if __name__ == "__main__":
    app.config["SESSION_COOKIE_SECURE"] = False   # uso local: http://localhost, sem HTTPS
    app.run(debug=True)
