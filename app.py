"""
Sistema de Prontuários — Casa de Acolhida Restauração

Telas:
    /login, /sair, /senha           entrar, sair e alterar a própria senha (todo o resto exige login)
    /                               home: atalhos + vagas por categoria + quadro de avisos
    /triagens                       lista de triagens (muda a situação pelo navegador)
    /triagens/nova                  formulário de triagem (?pessoa=<id> = paciente já cadastrado)
    /internos                       lista de internos (ativos / inativos)
    /prontuario/novo                formulário do prontuário (?pessoa=<id> = paciente já cadastrado)
    /internacoes/<id>               ficha: dados, parcelas, outras internações, ações
    /internacoes/<id>/editar        abre o formulário certo (triagem ou prontuário) já preenchido
    /internacoes/<id>/prontuario    baixa o .docx

Organização:
    validacao.py   CPF, RG, CEP, telefone, hora
    prontuario.py  regras do documento e geração do .docx
    modelos.py     tabelas (pessoas, internacoes, parcelas)
    servicos.py    regras de negócio: validar, gravar, mudar status, parcelas
    avisos.py      quadro de avisos
    vagas.py       ocupação das vagas por categoria
    autenticacao.py  login: usuários, senhas, sessão e proteção das rotas
    banco.py       onde fica o banco (SQLite local ou Postgres da hospedagem)
    copiar_banco.py  leva os dados do SQLite local para o banco da hospedagem
    verificar_vazamento.py  confere se algum dado de interno foi parar no git
    app.py         este arquivo: só liga as rotas às partes acima

ATENÇÃO: o banco guarda dados pessoais sensíveis e NUNCA vai para o git (instance/ está
no .gitignore; na hospedagem o banco é externo, via DATABASE_URL — veja banco.py).
Toda tela e todo dado exigem login (veja autenticacao.py para criar usuários e para
as variáveis de ambiente da hospedagem). Em produção use HTTPS e um servidor de
verdade (gunicorn app:app) — `python app.py` é só para uso local.
"""

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file,
                   session, url_for)

import autenticacao
import banco
import servicos
from avisos import gerar_avisos
from modelos import STATUS_INTERNACAO, STATUS_TRIAGEM, AvisoDispensado, Internacao, Parcela, Pessoa, db
from migracoes import migrar
from prontuario import fmt_data, fmt_reais, gerar_docx
from validacao import fmt_cep, fmt_cpf, fmt_hora, fmt_rg
from vagas import gerar_vagas

# DADOS_DIR: onde ficam o banco e a chave da sessão (o programa iniciar.py usa a pasta do
# usuário no Windows); sem ela, a pasta instance/ ao lado deste arquivo
app = Flask(__name__, instance_path=os.environ.get("DADOS_DIR") or None)
# o banco fica fora do git: SQLite local por padrão, ou o que estiver em DATABASE_URL (banco.py)
app.config["SQLALCHEMY_DATABASE_URI"] = banco.url_do_banco()
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = banco.opcoes_do_motor(app.config["SQLALCHEMY_DATABASE_URI"])
app.config["SECRET_KEY"] = autenticacao.chave_secreta(app.instance_path)  # assina a sessão do login
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,       # o JavaScript da página não lê o cookie
    SESSION_COOKIE_SAMESITE="Lax",      # o navegador não manda o cookie em POST vindo de outro site
    # só trafega por HTTPS — menos em desenvolvimento e no modo local (http://127.0.0.1, que
    # nunca sai deste computador)
    SESSION_COOKIE_SECURE=not (app.debug or autenticacao.modo_local()),
    SESSION_REFRESH_EACH_REQUEST=False,    # o login não se renova sozinho: vale 10 h e acabou
    PERMANENT_SESSION_LIFETIME=autenticacao.DURACAO_LOGIN,
)
if autenticacao.modo_local():
    # só atende pedidos endereçados a este computador (barra ataques de "DNS rebinding", em que
    # um site de fora faz o navegador falar com o sistema local)
    app.config["TRUSTED_HOSTS"] = ["127.0.0.1", "localhost"]
db.init_app(app)

with app.app_context():
    db.create_all()   # cria as tabelas que ainda não existem
    migrar(db)        # acrescenta colunas novas em bancos antigos
    autenticacao.criar_usuario_inicial()

app.before_request(autenticacao.exigir_login)
app.after_request(autenticacao.cabecalhos_de_seguranca)
autenticacao.registrar_comandos(app)
app.context_processor(lambda: {"usuario_atual": g.get("usuario")})

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
    if autenticacao.primeiro_acesso_liberado():
        return redirect(url_for("primeiro_acesso"))
    proximo = request.values.get("next", "")
    if request.method == "POST":
        usuario, erro = autenticacao.entrar(request.form.get("usuario"), request.form.get("senha"))
        if usuario:
            autenticacao.abrir_sessao(usuario)
            return redirect(autenticacao.destino_seguro(proximo, url_for("home")))
        return render_template("login.html", erro=erro, proximo=proximo), 401
    return render_template("login.html", erro=None, proximo=proximo)


@app.route("/primeiro-acesso", methods=["GET", "POST"])
def primeiro_acesso():
    """Só no programa local, e só até existir o primeiro usuário (autenticacao.py)."""
    if not autenticacao.primeiro_acesso_liberado():
        abort(404)
    erro = None
    if request.method == "POST":
        if request.form.get("senha") != request.form.get("confirmacao"):
            erro = "A confirmação não é igual à senha."
        else:
            usuario, erro = autenticacao.criar_usuario(request.form.get("usuario"), request.form.get("senha"))
            if usuario:
                autenticacao.abrir_sessao(usuario)
                flash(f"Usuário {usuario.nome} criado. Da próxima vez, entre com ele.")
                return redirect(url_for("home"))
    return render_template("primeiro_acesso.html", erro=erro, minimo=autenticacao.SENHA_MINIMA), \
        (400 if erro else 200)


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
    return render_template("home.html", avisos=gerar_avisos(), vagas=gerar_vagas())


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
    return render_template("triagens.html", novo=request.args.get("novo", type=int),
                           **servicos.opcoes_formulario())


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
                               **servicos.opcoes_formulario()), 400
    return redirect(url_for("lista_triagens", novo=internacao.id))


@app.post("/triagens/<int:id>/status")
def mudar_status(id):
    internacao = _buscar(Internacao, id)
    erros = servicos.mudar_status(internacao, request.get_json(force=True))
    if erros:
        return jsonify(ok=False, erros=erros), 400
    return jsonify(ok=True, status=internacao.status,
                   ficha=url_for("ficha", id=id), editar=url_for("editar_internacao", id=id))


# ================================================================== internos
@app.get("/internos")
def lista_internos():
    return render_template("internos.html", novo=request.args.get("novo", type=int))


@app.get("/api/internos")
def api_internos():
    itens = db.session.execute(
        db.select(Internacao).filter(Internacao.status.in_(STATUS_INTERNACAO))
        .order_by(Internacao.inicio.desc().nulls_last(), Internacao.id.desc())).scalars()
    return jsonify([i.para_lista() for i in itens])


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
                               anterior=None, **servicos.opcoes_formulario()), 400
    # Post/Redirect/Get: a lista baixa o .docx e destaca a linha
    return redirect(url_for("lista_internos", novo=internacao.id))


# ===================================================================== ficha
@app.get("/internacoes/<int:id>")
def ficha(id):
    return render_template("ficha.html", i=_buscar(Internacao, id))


@app.get("/internacoes/<int:id>/editar")
def editar_internacao(id):
    internacao = _buscar(Internacao, id)
    dados = internacao.dados_completos() | {"internacao_id": str(internacao.id),
                                            "pessoa_id": str(internacao.pessoa_id),
                                            "status": internacao.status}
    modelo = "triagem_form.html" if internacao.e_triagem else "formulario.html"
    return render_template(modelo, d=dados, erros={}, pessoa=internacao.pessoa, anterior=None,
                           editando=internacao, **servicos.opcoes_formulario())


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


if __name__ == "__main__":
    app.config["SESSION_COOKIE_SECURE"] = False   # uso local: http://localhost, sem HTTPS
    app.run(debug=True)
