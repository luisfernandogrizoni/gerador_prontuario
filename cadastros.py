"""
Cadastros: convênios e funcionários.

  * Convênios (Cadastros > Convênios): nome, vagas, cor. Um convênio novo aparece sozinho nos formulários, no quadro
    de vagas, na página de relatórios e entre as colunas do relatório anual (veja catalogo.py).
  * Funcionários (Cadastros > Funcionários): quem pode assinar como responsável pela emissão dos documentos, o login
    de cada um (o administrador cria o usuário e a senha aqui mesmo) e o nível de acesso. Quem é do Serviço Social
    (marca 'Assina o Serviço Social' e registro profissional, o CRESS) lê e escreve o acolhimento social, que é sigiloso:
    pode_servico_social.
  * Níveis de acesso (Cadastros > Níveis de acesso): uma cascata, do que tem mais acesso para o que tem menos. O
    primeiro da cascata é o do administrador. A regra do próprio acesso é pode_gerenciar_acessos (criar usuário e senha,
    vincular login, mudar o nível de alguém, mexer nos níveis e nas permissões). O que cada nível pode fazer no resto do
    sistema está em permissoes.py (Cadastros > Permissões); nivel_do_usuario diz em que nível a pessoa está.

Cada função de gravação devolve (objeto, erros), como em servicos.py: com `erros` preenchido, nada foi gravado e o
formulário volta com a mensagem ao lado de cada campo.
"""

import re
import unicodedata

from sqlalchemy.exc import IntegrityError

import autenticacao
import catalogo
from catalogo import CATEGORIAS_RESERVADAS, CORES
from documentos import Emissor
from modelos import Convenio, Funcionario, NivelAcesso, Usuario, db
from validacao import normalizar_nome

NOMES_DE_CONVENIO_RESERVADOS = ["A definir", "Particular"]    # valores que o sistema já usa para outra coisa


# ====================================================================== convênios
def convenios():
    return db.session.execute(db.select(Convenio).order_by(Convenio.ordem, Convenio.id)).scalars().all()


def slugificar(texto):
    """'Prefeitura de São João' -> 'prefeitura-de-sao-joao' (o endereço do relatório do convênio)."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-") or "convenio"


def _slug_livre(base):
    existentes = set(db.session.execute(db.select(Convenio.slug)).scalars())
    slug, n = base, 2
    while slug in existentes:
        slug, n = f"{base}-{n}", n + 1
    return slug


def cor_automatica():
    """A primeira cor ainda não usada por um convênio (se todas estiverem em uso, recomeça pela primeira)."""
    usadas = {c.cor for c in convenios()}
    return next((chave for chave, _ in CORES if chave not in usadas), CORES[0][0])


def validar_convenio(form, convenio=None):
    """`convenio` = o que está sendo editado (o nome guardado nunca muda depois de criado)."""
    erros = {}
    outros = [c for c in convenios() if not convenio or c.id != convenio.id]
    if convenio is None:
        nome = (form.get("nome") or "").strip()
        if not nome:
            erros["nome"] = "Informe o nome do convênio."
        elif len(nome) > 50:
            erros["nome"] = "O nome pode ter até 50 caracteres."
        elif normalizar_nome(nome) in {normalizar_nome(n) for n in NOMES_DE_CONVENIO_RESERVADOS} | {normalizar_nome(c.nome) for c in outros}:
            erros["nome"] = "Já existe um convênio com esse nome."
    else:
        nome = convenio.nome
    nome_tela = (form.get("nome_tela") or "").strip() or nome
    if len(nome_tela) > 50:
        erros["nome_tela"] = "O nome nas telas pode ter até 50 caracteres."
    elif normalizar_nome(nome_tela) in {normalizar_nome(n) for n in CATEGORIAS_RESERVADAS} | {normalizar_nome(c.nome_tela) for c in outros}:
        erros["nome_tela"] = "Esse nome já é usado por outro convênio ou categoria. Escolha outro."
    try:
        vagas = int((form.get("vagas") or "").strip())
        if not 0 <= vagas <= 999:
            raise ValueError
    except ValueError:
        erros["vagas"] = "Informe o número de vagas (de 0 a 999)."
    if form.get("cor") and form["cor"] not in dict(CORES):
        erros["cor"] = "Escolha uma das cores."
    return erros


def salvar_convenio(form, convenio=None):
    erros = validar_convenio(form, convenio)
    if erros:
        return None, erros
    nome_tela = (form.get("nome_tela") or "").strip()
    if convenio is None:
        nome = form["nome"].strip()
        convenio = Convenio(nome=nome, slug=_slug_livre(slugificar(nome)), gratuito=True,
                            ordem=max((c.ordem for c in convenios()), default=0) + 1)
        db.session.add(convenio)
        convenio.nome_tela = nome_tela or nome
        convenio.cor = form.get("cor") or cor_automatica()
        convenio.ativo = True
    else:
        convenio.nome_tela = nome_tela or convenio.nome
        if form.get("cor"):
            convenio.cor = form["cor"]
        convenio.ativo = form.get("ativo") == "1"
    convenio.vagas = int(form["vagas"].strip())
    db.session.commit()
    catalogo.esquecer()
    return convenio, {}


# =================================================================== funcionários
def funcionarios():
    return db.session.execute(db.select(Funcionario).order_by(Funcionario.ativo.desc(), Funcionario.nome)).scalars().all()


def usuarios_para_vincular(funcionario=None):
    """Logins que ainda não pertencem a nenhum funcionário (mais o do próprio funcionário, se estiver editando)."""
    usados = {f.usuario for f in funcionarios() if f.usuario and (not funcionario or f.id != funcionario.id)}
    nomes = db.session.execute(db.select(Usuario.nome).order_by(Usuario.nome)).scalars().all()
    return [n for n in nomes if n not in usados]


def _administradores_em(linhas, topo, logins):
    """Quantos dos `linhas` ((ativo, nivel_id, login) de cada funcionário) são administradores: ativos, no nível do
    topo da cascata e com um usuário de `logins` (os que existem e estão ativos)."""
    return sum(1 for ativo, nivel_id, login in linhas if ativo and nivel_id == topo.id and login in logins)


def _logins_ativos():
    return set(db.session.execute(db.select(Usuario.nome).filter_by(ativo=True)).scalars())


def nivel_de_topo():
    """O primeiro da cascata: é o nível do administrador (por isso fica sempre no topo e sempre ativo)."""
    lista = niveis()
    return lista[0] if lista else None


def administradores():
    """Funcionários ativos, no nível do topo da cascata, com um usuário que existe e está ativo."""
    topo, logins = nivel_de_topo(), _logins_ativos()
    return [f for f in funcionarios() if topo and f.ativo and f.nivel_id == topo.id and f.usuario in logins]


def pode_gerenciar_acessos(usuario):
    """Quem pode criar usuário e senha, vincular o login de um funcionário, mudar o nível de acesso de alguém e mexer
    nos níveis: só o administrador. Enquanto NENHUM administrador tem usuário vinculado (o sistema recém-instalado),
    quem está logado pode: é assim que o primeiro administrador vincula o próprio usuário. Depois disso vale a regra."""
    admins = administradores()
    if not admins:
        return True
    return usuario is not None and any(a.usuario == usuario.nome for a in admins)


def _validar_acesso(form, funcionario, ativo):
    """Os campos de acesso do formulário do funcionário (só o administrador chega aqui)."""
    erros = {}
    if (form.get("nivel_id") or "") not in {i for i, _ in niveis_para_escolher(funcionario)}:
        erros["nivel_id"] = "Escolha o nível de acesso."
    escolhido, novo = (form.get("usuario") or "").strip(), (form.get("novo_usuario") or "").strip().lower()
    senha, confirmacao = form.get("senha") or "", form.get("confirmacao") or ""
    if escolhido and escolhido not in usuarios_para_vincular(funcionario):
        erros["usuario"] = "Esse usuário não existe ou já pertence a outro funcionário."
    if novo:
        atual = funcionario.usuario if funcionario is not None else ""
        if atual and autenticacao.buscar_usuario(atual):      # (o formulário nem mostra o campo nesse caso; o erro aparece no usuário dela)
            erros["usuario"] = f"Esta pessoa já tem o usuário {atual}. Para mudar a senha dele, use o campo da senha."
        elif escolhido:
            erros["novo_usuario"] = "Escolha um usuário que já existe ou crie um novo, não os dois."
        elif erro := autenticacao.validar_nome_de_usuario(novo):
            erros["novo_usuario"] = erro
    if senha or confirmacao or novo:
        if not (novo or escolhido):
            erros["senha"] = "Escolha ou crie um usuário para essa senha."
        elif "usuario" not in erros and "novo_usuario" not in erros:
            if erro := autenticacao.validar_senha(senha):
                erros["senha"] = erro
            elif senha != confirmacao:
                erros["confirmacao"] = "A confirmação não é igual à senha."
    # nunca deixar o sistema sem administrador (senão qualquer um voltaria a poder tudo, ou ninguém mais)
    topo = nivel_de_topo()
    if topo and "nivel_id" not in erros and administradores():
        linhas = [(f.ativo, f.nivel_id, f.usuario) for f in funcionarios() if funcionario is None or f.id != funcionario.id]
        linhas.append((ativo, int(form["nivel_id"]), novo or escolhido))
        if not _administradores_em(linhas, topo, _logins_ativos() | ({novo} if novo else set())):
            erros["nivel_id"] = (f"Esta pessoa é a única com o nível {topo.nome} e um usuário ativo. Mantenha ela ativa, "
                                 f"nesse nível e com o usuário, ou deixe outra pessoa como {topo.nome} antes.")
    return erros


def validar_funcionario(form, funcionario=None, pode_acessos=True):
    """`pode_acessos` = quem está salvando é o administrador: só ele muda nível, usuário e senha (para os outros, esses
    campos nem são lidos)."""
    erros = {}
    nome, cargo = (form.get("nome") or "").strip(), (form.get("cargo") or "").strip()
    if not nome:
        erros["nome"] = "Informe o nome."
    elif len(nome) > 200:
        erros["nome"] = "O nome pode ter até 200 caracteres."
    if not cargo:
        erros["cargo"] = "Informe o cargo (ele aparece na assinatura dos documentos)."
    elif len(cargo) > 100:
        erros["cargo"] = "O cargo pode ter até 100 caracteres."
    ativo, padrao = form.get("ativo") == "1", form.get("padrao") == "1"
    if padrao and not ativo:
        erros["padrao"] = "Quem assina por padrão precisa estar ativo."
    if funcionario is not None and funcionario.padrao and not padrao:
        erros["padrao"] = "Para trocar quem assina por padrão, marque a outra pessoa como padrão."
    registro = (form.get("registro_profissional") or "").strip()
    # quem é (ou vai ser) assistente social: o administrador decide pela marca; para os outros vale a que já está no cadastro
    eh_social = form.get("servico_social") == "1" if pode_acessos else bool(funcionario is not None and funcionario.servico_social)
    if len(registro) > 30:
        erros["registro_profissional"] = "O registro pode ter até 30 caracteres."
    elif eh_social and not registro:
        erros["registro_profissional"] = "Informe o registro profissional (CRESS): ele assina os documentos e o relatório da assistente social."
    if pode_acessos:
        erros.update(_validar_acesso(form, funcionario, ativo))
    return erros


def salvar_funcionario(form, funcionario=None, por=None):
    """`por` = o usuário que está salvando. Se ele é o administrador, o formulário também cria o usuário e a senha
    (campos `novo_usuario`, `senha`, `confirmacao`), vincula um usuário que já existe (`usuario`), troca a senha dele
    e escolhe o nível (`nivel_id`); para os outros, nível, usuário e senha ficam como estavam."""
    pode = pode_gerenciar_acessos(por)
    erros = validar_funcionario(form, funcionario, pode)
    if erros:
        return None, erros
    if funcionario is None:
        funcionario = Funcionario()
        db.session.add(funcionario)
    funcionario.nome, funcionario.cargo = form["nome"].strip(), form["cargo"].strip()
    funcionario.ativo = form.get("ativo") == "1"
    funcionario.registro_profissional = (form.get("registro_profissional") or "").strip()
    try:
        if pode:
            funcionario.servico_social = form.get("servico_social") == "1"     # dar acesso ao sigilo é coisa do administrador
            funcionario.nivel_id = int(form["nivel_id"])
            erro_de_acesso = _gravar_acesso(form, funcionario)
            if erro_de_acesso:
                db.session.rollback()
                return None, erro_de_acesso
        elif funcionario.nivel_id is None:
            padrao_de_nivel = nivel_para_novo_funcionario()
            funcionario.nivel_id = int(padrao_de_nivel) if padrao_de_nivel else None
        if form.get("padrao") == "1":
            for outro in funcionarios():
                outro.padrao = False
            funcionario.padrao = True
        db.session.commit()
    except IntegrityError:       # alguém criou o mesmo usuário no mesmo instante
        db.session.rollback()
        return None, {"novo_usuario": "Esse usuário acabou de ser criado por outra pessoa. Escolha outro nome."}
    return funcionario, {}


def _gravar_acesso(form, funcionario):
    """Usuário e senha do funcionário (sem confirmar a gravação: quem chama grava tudo junto). Devolve os erros, se houver."""
    escolhido, novo = (form.get("usuario") or "").strip(), (form.get("novo_usuario") or "").strip().lower()
    senha = form.get("senha") or ""
    if novo:
        usuario, erro = autenticacao.criar_usuario(novo, senha, confirmar=False)
        if erro:
            return {"novo_usuario": erro}
        funcionario.usuario = usuario.nome
        return {}
    funcionario.usuario = escolhido
    if escolhido and senha:
        autenticacao.definir_senha(autenticacao.buscar_usuario(escolhido), senha, confirmar=False)
    return {}


def frase_do_acesso(form, pode, login):
    """O que o formulário fez com o acesso, para a mensagem de confirmação ('' se nada)."""
    if not pode or not login:
        return ""
    if (form.get("novo_usuario") or "").strip():
        return f" Usuário {login} criado: já pode entrar no sistema."
    if form.get("senha"):
        return f" Senha de {login} alterada."
    return ""


class ErroDeAssinatura(Exception):
    """Quem ia assinar é assistente social e está sem o CRESS no cadastro: o documento não sai sem ele."""


MENSAGEM_SEM_CRESS = ("O seu CRESS não está no cadastro de funcionários, e a assistente social assina com ele. "
                      "Peça ao administrador para preenchê-lo em Cadastros > Funcionários.")


def sem_registro(funcionario):
    """Assistente social (marca 'Assina o Serviço Social') sem o registro profissional (CRESS) no cadastro."""
    return bool(funcionario is not None and funcionario.servico_social and not (funcionario.registro_profissional or "").strip())


def registro_pendente(usuario):
    """Quem está logado é assistente social e está sem o CRESS no cadastro (não pode finalizar nem escrever adendo)."""
    return sem_registro(funcionario_do_usuario(usuario))


def rotulo_do_emissor(funcionario):
    """Como a pessoa aparece na lista de quem assina: 'Nome — cargo · CRESS' (e o aviso, se for assistente social sem o CRESS)."""
    texto = f"{funcionario.nome} — {funcionario.cargo}"
    if (funcionario.registro_profissional or "").strip():
        texto += f" · {funcionario.registro_profissional.strip()}"
    return texto + (" (falta o CRESS)" if sem_registro(funcionario) else "")


def emissor_para(usuario=None, escolhido_id=None):
    """Quem assina o documento: o escolhido na tela; senão o funcionário do usuário que está logado; senão o
    padrão; senão o primeiro ativo; senão o de fábrica. Devolve (Emissor, id do funcionário ou None). Quem tem registro
    profissional assina com ele; assistente social sem o CRESS no cadastro não assina (ErroDeAssinatura)."""
    ativos = db.session.execute(db.select(Funcionario).filter_by(ativo=True).order_by(Funcionario.id)).scalars().all()
    escolhido = next((f for f in ativos if f.id == escolhido_id), None) if escolhido_id else None
    if escolhido is None and usuario is not None:
        escolhido = next((f for f in ativos if f.usuario and f.usuario == usuario.nome), None)
    if escolhido is None:
        escolhido = next((f for f in ativos if f.padrao), ativos[0] if ativos else None)
    if escolhido is None:
        return Emissor(), None
    if sem_registro(escolhido):
        raise ErroDeAssinatura(f"O cadastro de {escolhido.nome} (Serviço Social) está sem o CRESS, que assina junto do nome. "
                               "Preencha em Cadastros > Funcionários (o administrador) ou escolha outra pessoa para assinar.")
    return Emissor(escolhido.nome, escolhido.cargo, (escolhido.registro_profissional or "").strip()), escolhido.id


# ================================================================ níveis de acesso
def niveis():
    return db.session.execute(db.select(NivelAcesso).order_by(NivelAcesso.ordem, NivelAcesso.id)).scalars().all()


def niveis_para_escolher(funcionario=None):
    """(id como texto, nome) para o select do funcionário: os ativos, na ordem da cascata, mais o nível atual dele
    se foi desativado depois."""
    atual = funcionario.nivel_id if funcionario else None
    return [(str(n.id), n.nome) for n in niveis() if n.ativo or n.id == atual]


def nivel_para_novo_funcionario():
    """O nível que já vem escolhido para quem entra: o de menos acesso (o último da cascata, entre os ativos)."""
    ativos = [n for n in niveis() if n.ativo]
    return str(ativos[-1].id) if ativos else ""


def funcionario_do_usuario(usuario):
    """O funcionário ativo que tem o login de quem está logado (None se não houver)."""
    if usuario is None:
        return None
    return db.session.execute(db.select(Funcionario).filter_by(usuario=usuario.nome, ativo=True)).scalars().first()


def nivel_do_usuario(usuario):
    """O nível de acesso de quem está logado: o do funcionário ativo que tem o login dele (None se não houver).
    É com ele que permissoes.py decide o que a pessoa pode fazer."""
    funcionario = funcionario_do_usuario(usuario)
    return funcionario.nivel if funcionario else None


def acesso_desativado(usuario):
    """O login pertence a um funcionário que foi desativado (e a nenhum ativo): quem saiu da casa não entra mais, nem com
    a sessão que já estava aberta. Login sem funcionário nenhum não conta (vale o nível de menos acesso)."""
    if usuario is None:
        return False
    donos = db.session.execute(db.select(Funcionario.ativo).filter_by(usuario=usuario.nome)).scalars().all()
    return bool(donos) and not any(donos)


def pode_servico_social(usuario):
    """Quem lê e escreve o acolhimento social (ficha, relatório e parecer da assistente social), que traz dados muito
    sensíveis: o administrador e quem tem a marca 'Assina o Serviço Social' no cadastro de funcionários. Os outros só
    sabem se foi feito. (Enquanto nenhum administrador tem usuário vinculado, o sistema está recém-instalado e quem está
    logado conta como administrador: veja pode_gerenciar_acessos.)"""
    if pode_gerenciar_acessos(usuario):
        return True
    funcionario = funcionario_do_usuario(usuario)
    return bool(funcionario and funcionario.servico_social)


def assinatura_do_usuario(usuario):
    """Como quem está logado assina o que finaliza: 'Nome — cargo — registro profissional' do funcionário dele (só o
    login, se não há funcionário vinculado). Quem finaliza leva isso gravado, como estava naquele momento."""
    funcionario = funcionario_do_usuario(usuario)
    if funcionario is None:
        return usuario.nome if usuario is not None else ""
    return " — ".join(parte for parte in (funcionario.nome, funcionario.cargo, funcionario.registro_profissional) if parte)


def validar_nivel(form, nivel=None):
    erros = {}
    nome, descricao = (form.get("nome") or "").strip(), (form.get("descricao") or "").strip()
    outros = [n for n in niveis() if not nivel or n.id != nivel.id]
    if not nome:
        erros["nome"] = "Informe o nome do nível."
    elif len(nome) > 50:
        erros["nome"] = "O nome pode ter até 50 caracteres."
    elif normalizar_nome(nome) in {normalizar_nome(n.nome) for n in outros}:
        erros["nome"] = "Já existe um nível com esse nome."
    if len(descricao) > 200:
        erros["descricao"] = "A descrição pode ter até 200 caracteres."
    if nivel is not None and nivel.ativo and form.get("ativo") != "1":                 # desativando
        em_uso = sum(1 for f in funcionarios() if f.ativo and f.nivel_id == nivel.id)
        if em_uso:
            erros["ativo"] = (f"Este nível é de {em_uso} funcionário{'s' if em_uso != 1 else ''} ativo{'s' if em_uso != 1 else ''}: "
                              "troque o nível dele" + ("s" if em_uso != 1 else "") + " antes de desativar.")
        elif nivel.id == nivel_de_topo().id:
            erros["ativo"] = "O primeiro nível da cascata é o do administrador: precisa continuar ativo."
        elif not any(n.ativo for n in outros):
            erros["ativo"] = "Precisa haver pelo menos um nível ativo."
    return erros


def salvar_nivel(form, nivel=None):
    erros = validar_nivel(form, nivel)
    if erros:
        return None, erros
    if nivel is None:
        nivel = NivelAcesso(ordem=max((n.ordem for n in niveis()), default=0) + 1, ativo=True)   # entra no fim: o de menos acesso
        db.session.add(nivel)
    else:
        nivel.ativo = form.get("ativo") == "1"
    nivel.nome, nivel.descricao = form["nome"].strip(), (form.get("descricao") or "").strip()
    db.session.commit()
    return nivel, {}


def mover_nivel(nivel, sentido):
    """Sobe ('cima': mais acesso) ou desce ('baixo': menos acesso) um nível na cascata. False se já está na ponta.
    A primeira posição é a do administrador e não troca de lugar com ninguém."""
    lista = niveis()
    i = next(k for k, n in enumerate(lista) if n.id == nivel.id)
    j = i - 1 if sentido == "cima" else i + 1
    if sentido not in ("cima", "baixo") or not 0 <= j < len(lista) or 0 in (i, j):
        return False
    lista[i], lista[j] = lista[j], lista[i]
    for posicao, n in enumerate(lista, 1):
        n.ordem = posicao
    db.session.commit()
    return True
