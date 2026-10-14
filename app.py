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
    /internacoes/<id>/prontuario    baixa o .docx
    /internacoes/<id>/impressos     os impressos da triagem (pedido de exames, enxoval) e da internação (prontuário, manual
                                    de orientação, ficha multiprofissional, capa do envelope, relatório do Serviço Social)
                                    num documento só
    /internacoes/<id>/relatorio-social   a assistente social escreve o relatório do Serviço Social no sistema
    /internacoes/<id>/rejeicao      relatório de por que a triagem rejeitou a pessoa (situação "Rejeitado na triagem")
    /internacoes/<id>/excluir       exclui o registro: o operador só tira de circulação; o administrador também apaga de vez
    /cadastros/lixeira              (administrador) o que foi excluído: restaurar ou apagar do banco

Organização:
    validacao.py   CPF, RG, CEP, telefone, hora
    prontuario.py  regras do documento e geração do .docx
    modelos.py     tabelas (pessoas, internacoes, parcelas)
    servicos.py    regras de negócio: validar, gravar, mudar status, parcelas
    avisos.py      quadro de avisos
    catalogo.py    o que o sistema sabe de cada convênio (lido do cadastro, uma vez por requisição)
    cadastros.py   cadastros de convênios e de funcionários
    fichas.py      pedido de exames, enxoval, capa do envelope e ficha multiprofissional (em branco)
    manual_de_orientacao.py  o manual que a família recebe na internação (o texto fica lá)
    servico_social.py  o relatório do Serviço Social: perguntas, gravação e documento
    rejeicao.py    o relatório de rejeição na triagem (mesmas peças do relatório acima)
    exclusao.py    excluir em duas etapas: some de tudo sem sair do banco, até o administrador apagar de vez
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
veja autenticacao.py para o primeiro usuário e para as variáveis de ambiente da hospedagem). Em produção use HTTPS e um servidor de
verdade (gunicorn app:app) — `python app.py` é só para uso local.
"""

import os
from datetime import date

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file,
                   session, url_for)

import autenticacao
import banco
import cadastros as cadastros_
import catalogo
import declaracoes
import documentos
import exclusao
import impressos
import painel
import rejeicao
import relatorios
import servico_social
import servicos
from avisos import dias_de_espera, gerar_avisos, tempo_decorrido
from modelos import (ENVELOPE_RECEBIDO, STATUS_INTERNACAO, STATUS_TRIAGEM, AvisoDispensado, Convenio, Funcionario,
                     Internacao, NivelAcesso, Parcela, Pessoa, db)
from migracoes import migrar
from prontuario import faixas_do_particular, fmt_data, fmt_reais, gerar_docx, montar_documento
from validacao import fmt_cep, fmt_cpf, fmt_hora, fmt_rg
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
app.after_request(autenticacao.cabecalhos_de_seguranca)
autenticacao.registrar_comandos(app)
def _e_administrador():
    """O usuário logado é o administrador? (cadastros.pode_gerenciar_acessos: enquanto nenhum administrador tem usuário
    vinculado, vale para quem está logado.) Guardado por requisição: as telas perguntam várias vezes."""
    if "e_administrador" not in g:
        g.e_administrador = cadastros_.pode_gerenciar_acessos(g.get("usuario"))
    return g.e_administrador


app.context_processor(lambda: {"usuario_atual": g.get("usuario"), "e_administrador": _e_administrador()})

# filtros usados nos templates: {{ p.cpf | cpf }}, {{ i.inicio | data }} ...
app.jinja_env.filters.update(cpf=fmt_cpf, rg=fmt_rg, cep=fmt_cep, data=fmt_data, hora=fmt_hora,
                             reais=lambda v: fmt_reais(v or 0.0))


def _buscar(modelo, id):
    return db.session.get(modelo, id) or abort(404)


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
    return render_template("home.html", avisos=gerar_avisos(), vagas=lista_de_vagas, vagas_total=totais(lista_de_vagas),
                           resumo=painel.resumo(), agenda=painel.agenda(hoje=hoje), para_imprimir=painel.impressos_da_internacao(hoje=hoje),
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
    return jsonify([i.para_triagem() for i in itens])


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
                   rejeicao=url_for("relatorio_de_rejeicao", id=id))


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
    baixar = 1 if request.form.get("acao") == "baixar" else None
    return redirect(url_for("lista_internos", novo=internacao.id, baixar=baixar))


# ===================================================================== ficha
@app.get("/internacoes/<int:id>")
def ficha(id):
    internacao = _buscar(Internacao, id)
    dias, atrasado = dias_de_espera(internacao)
    return render_template("ficha.html", i=internacao, envelope_atrasado=atrasado,
                           envelope_tempo=tempo_decorrido(dias) if dias is not None else "",
                           relatorio_preenchido=servico_social.preenchido(internacao.relatorio_social),
                           rejeicao_preenchida=rejeicao.preenchido(internacao.rejeicao))


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
    itens = impressos.ler_itens(request.args.get("itens"), internacao)
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
    barra = {"itens": impressos.barra(internacao, itens, lambda novos: url_for("ver_impressos", id=id, itens=",".join(novos)))}
    return _mostrar(doc, url_for("baixar_impressos", id=id, itens=",".join(itens)), url_for("ficha", id=id), barra=barra)


@app.get("/internacoes/<int:id>/impressos.docx")
def baixar_impressos(id):
    internacao, itens, doc = _impresso(id)
    _anotar_impressao(internacao, itens)
    return _baixar(doc)


# ------------------------------------------------- relatório do Serviço Social
def _tela_relatorio(internacao, form, erros, status=200):
    relatorio = internacao.relatorio_social
    acolhido, responsavel = servico_social.identificacao(internacao, relatorios.hoje_no_brasil())
    valores = servico_social.valores_do_formulario(form) if form is not None else servico_social.valores(internacao, relatorio)
    return render_template("servico_social_form.html", i=internacao, secoes=servico_social.SECOES, v=valores, erros=erros,
                           relatorio=relatorio, acolhido=acolhido, responsavel=responsavel), status


@app.route("/internacoes/<int:id>/relatorio-social", methods=["GET", "POST"])
def relatorio_social(id):
    internacao = _buscar(Internacao, id)
    if request.method == "POST":
        _, erros = servicos.salvar_relatorio_social(internacao, request.form, g.usuario.nome if g.get("usuario") else "")
        if erros:
            return _tela_relatorio(internacao, request.form, erros, 400)
        if request.form.get("acao") == "imprimir":
            return redirect(url_for("ver_impressos", id=id, itens="relatorio-social", imprimir=1))
        flash("Relatório do Serviço Social salvo.")
        return redirect(url_for("relatorio_social", id=id))
    return _tela_relatorio(internacao, None, {})


# ----------------------------------------- relatório de rejeição na triagem
def _tela_rejeicao(internacao, form, erros, status=200):
    relatorio = internacao.rejeicao
    acolhido = rejeicao.identificacao(internacao, relatorios.hoje_no_brasil())
    valores = rejeicao.valores_do_formulario(form) if form is not None else rejeicao.valores(internacao, relatorio)
    return render_template("servico_social_form.html", i=internacao, titulo="Relatório de rejeição na triagem", secoes=rejeicao.SECOES, v=valores,
                           erros=erros, relatorio=relatorio, acolhido=acolhido, responsavel=None), status


@app.route("/internacoes/<int:id>/rejeicao", methods=["GET", "POST"])
def relatorio_de_rejeicao(id):
    internacao = _buscar(Internacao, id)
    if not internacao.e_triagem:                          # quem já foi internado não tem rejeição na triagem
        abort(404)
    if request.method == "POST":
        _, erros = servicos.salvar_rejeicao(internacao, request.form, g.usuario.nome if g.get("usuario") else "")
        if erros:
            return _tela_rejeicao(internacao, request.form, erros, 400)
        if request.form.get("acao") == "imprimir":
            return redirect(url_for("ver_impressos", id=id, itens="rejeicao", imprimir=1))
        flash("Relatório de rejeição salvo.")
        return redirect(url_for("relatorio_de_rejeicao", id=id))
    return _tela_rejeicao(internacao, None, {})


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
             "padrao": "1" if funcionario.padrao else ""}
    return _tela_funcionario(funcionario, dados, {})


@app.get("/cadastros/niveis")
def lista_niveis():
    em_uso = {nivel_id: n for nivel_id, n in db.session.execute(
        db.select(Funcionario.nivel_id, db.func.count()).filter(Funcionario.ativo.is_(True)).group_by(Funcionario.nivel_id))}
    return render_template("cadastro_niveis.html", niveis=cadastros_.niveis(), funcionarios_por_nivel=em_uso,
                           pode_acessos=cadastros_.pode_gerenciar_acessos(g.usuario))


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
