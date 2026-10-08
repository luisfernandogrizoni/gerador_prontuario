"""
Sistema de Prontuários — Casa de Acolhida Restauração

Telas:
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
    app.py        este arquivo: só liga as rotas às partes acima

ATENÇÃO: o banco (instance/internos.db) guarda dados pessoais sensíveis.
Rodar só na máquina local; para publicar na internet, antes é preciso login.
"""

from flask import (Flask, abort, flash, jsonify, redirect, render_template, request, send_file,
                   url_for)

import servicos
from avisos import gerar_avisos
from modelos import STATUS_INTERNACAO, STATUS_TRIAGEM, AvisoDispensado, Internacao, Parcela, Pessoa, db
from migracoes import migrar
from prontuario import fmt_data, fmt_reais, gerar_docx
from validacao import fmt_cep, fmt_cpf, fmt_hora, fmt_rg
from vagas import gerar_vagas

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///internos.db"  # relativo à pasta instance/
app.config["SECRET_KEY"] = "troque-esta-chave"  # necessário para as mensagens flash
db.init_app(app)

with app.app_context():
    db.create_all()   # cria as tabelas que ainda não existem
    migrar(db)        # acrescenta colunas novas em bancos antigos

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
        .order_by(Internacao.primeiro_contato.desc(), Internacao.id.desc())).scalars()
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
        .order_by(Internacao.inicio.desc(), Internacao.id.desc())).scalars()
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
    app.run(debug=True)
