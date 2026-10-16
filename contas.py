"""
Contas mais fortes: e-mail confirmado, "esqueci minha senha" e segundo fator (plano de segurança, fase 3: docs/plano-de-seguranca.md).

  * **E-mail**: cada funcionário tem um e-mail institucional no cadastro (só o administrador o altera) e ele só vale depois de a
    própria pessoa digitar o código de 6 dígitos que o sistema mandou para ele (30 minutos, 5 tentativas).
  * **Esqueci minha senha**: a pessoa informa o usuário; se ele existe e tem e-mail confirmado, recebe um link de uso único que vale
    30 minutos. **A tela responde igual exista ou não o usuário** (não revela quem tem cadastro) e o envio é em segundo plano (o tempo
    de resposta também não revela). O link vai guardado só como resumo; usá-lo derruba as outras sessões. Quem tem segundo fator
    ligado precisa do código do autenticador (ou de um de recuperação) para redefinir; **administrador sem segundo fator não redefine
    pelo e-mail** (quem invadir a caixa de e-mail não vira administrador).
  * **Segundo fator** (totp.py): ativar (QR code e um código para provar que funcionou), códigos de recuperação, desativar.
  * Avisos por e-mail de coisa de segurança: senha trocada, segundo fator ligado ou desligado.
  * Limites: 1 e-mail por minuto e 5 por hora, por pessoa e finalidade.

Comandos do administrador no servidor (terminal): `flask --app app configurar-email`, `testar-email`, `desativar-segundo-fator`.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta

import click
from flask import current_app, request

import auditoria
import autenticacao
import cadastros
import email_envio
import totp
from modelos import CodigoSeguranca, Funcionario, Usuario, db

log = logging.getLogger(__name__)

VALIDADE_DO_CODIGO_DE_EMAIL = timedelta(minutes=30)
VALIDADE_DO_LINK_DA_SENHA = timedelta(minutes=30)
MAX_TENTATIVAS = 5
MAX_ENVIOS_POR_HORA = 5
ESPERA_ENTRE_ENVIOS = timedelta(seconds=60)
MAX_PEDIDOS_POR_ENDERECO = 10               # "esqueci minha senha" por hora, vindos do mesmo computador

MENSAGEM_ENVIO_NAO_CONFIGURADO = "O envio de e-mail ainda não foi configurado neste servidor. Avise o administrador."


def _agora(agora):
    return agora or datetime.now()


def _resumo(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _instance():
    return current_app.instance_path


def _chave_mestra():
    return current_app.config["SECRET_KEY"]


def funcionario_de(usuario):
    return cadastros.funcionario_do_usuario(usuario)


def email_confirmado(funcionario):
    return bool(funcionario is not None and funcionario.email and funcionario.email_confirmado_em)


def e_administrador(usuario):
    """O login é de um administrador (funcionário ativo, no nível do topo): o que decide se o e-mail pode redefinir a senha dele."""
    return usuario is not None and any(a.usuario == usuario.nome for a in cadastros.administradores())


# ====================================================================== limites de envio
def _limite_de_envios(usuario_id, finalidade, agora):
    """None se pode enviar agora; senão a mensagem. Conta só o que foi criado: tentar de novo não fura o limite."""
    ultimos = db.session.execute(db.select(CodigoSeguranca).filter_by(usuario_id=usuario_id, finalidade=finalidade)
                                 .filter(CodigoSeguranca.criado_em > agora - timedelta(hours=1)).order_by(CodigoSeguranca.criado_em.desc())).scalars().all()
    if ultimos and agora - ultimos[0].criado_em < ESPERA_ENTRE_ENVIOS:
        return "Acabamos de enviar um e-mail. Espere um minuto para pedir outro."
    if len(ultimos) >= MAX_ENVIOS_POR_HORA:
        return "Muitos pedidos de e-mail na última hora. Tente de novo mais tarde."
    return None


def _invalidar_anteriores(usuario_id, finalidade, agora):
    for antigo in db.session.execute(db.select(CodigoSeguranca).filter_by(usuario_id=usuario_id, finalidade=finalidade, usado_em=None)).scalars():
        antigo.usado_em = agora


def _avisar(funcionario, assunto, texto):
    """E-mail de aviso de segurança para o e-mail confirmado da pessoa (sem e-mail ou sem envio configurado, não faz nada)."""
    if email_confirmado(funcionario) and email_envio.configurado(_instance()):
        email_envio.enviar_em_segundo_plano(_instance(), funcionario.email, assunto, texto)


def _assinatura_do_email():
    return "\n\n—\nCasa de Acolhida Restauração · Sistema de prontuários\nMensagem automática: não responda."


# ====================================================================== confirmar o e-mail
def enviar_codigo_de_email(usuario, agora=None):
    """Manda o código de 6 dígitos para o e-mail do cadastro. Devolve o erro (texto) ou None."""
    agora = _agora(agora)
    funcionario = funcionario_de(usuario)
    if funcionario is None or not funcionario.email:
        return "O seu cadastro ainda não tem um e-mail. Peça ao administrador para informá-lo em Cadastros > Funcionários."
    if not email_envio.configurado(_instance()):
        return MENSAGEM_ENVIO_NAO_CONFIGURADO
    if erro := _limite_de_envios(usuario.id, "email", agora):
        return erro
    codigo = f"{secrets.randbelow(10 ** 6):06d}"
    _invalidar_anteriores(usuario.id, "email", agora)
    db.session.add(CodigoSeguranca(usuario_id=usuario.id, finalidade="email", resumo=_resumo(codigo), destino=funcionario.email,
                                   criado_em=agora, expira_em=agora + VALIDADE_DO_CODIGO_DE_EMAIL))
    db.session.commit()
    email_envio.enviar_em_segundo_plano(_instance(), funcionario.email, "Código para confirmar o seu e-mail",
                                        f"Seu código de confirmação é: {codigo}\n\nEle vale por 30 minutos. Digite-o no sistema, em Minha segurança."
                                        f"\nSe não foi você que pediu, ignore esta mensagem." + _assinatura_do_email())
    auditoria.registrar("email.codigo_enviado", "funcionario", funcionario.id, detalhe=email_envio.mascarar(funcionario.email))
    return None


def confirmar_email(usuario, digitado, agora=None):
    """Confere o código. Devolve o erro (texto) ou None (o e-mail ficou confirmado)."""
    agora = _agora(agora)
    funcionario = funcionario_de(usuario)
    if funcionario is None or not funcionario.email:
        return "O seu cadastro ainda não tem um e-mail."
    codigo = db.session.execute(db.select(CodigoSeguranca).filter_by(usuario_id=usuario.id, finalidade="email", usado_em=None, destino=funcionario.email)
                                .filter(CodigoSeguranca.expira_em > agora).order_by(CodigoSeguranca.criado_em.desc())).scalars().first()
    if codigo is None:
        return "Não há um código válido. Peça um código novo."
    codigo.tentativas += 1
    if codigo.tentativas > MAX_TENTATIVAS:
        codigo.usado_em = agora
        db.session.commit()
        return "Muitas tentativas erradas. Peça um código novo."
    limpo = "".join(c for c in (digitado or "") if c.isdigit())
    if len(limpo) != 6 or _resumo(limpo) != codigo.resumo:
        db.session.commit()
        return "Esse código não confere."
    codigo.usado_em = agora
    funcionario.email_confirmado_em = agora
    usuario.exigir_email = False                 # (acesso novo: com o e-mail confirmado, o sistema abre)
    db.session.commit()
    auditoria.registrar("email.confirmado", "funcionario", funcionario.id, detalhe=email_envio.mascarar(funcionario.email))
    return None


def avisar_senha_trocada(usuario):
    """A própria pessoa trocou a senha: e-mail de aviso para o endereço confirmado dela (se houver)."""
    _avisar(funcionario_de(usuario), "A sua senha foi alterada", f"A senha do usuário {usuario.nome} foi alterada agora.\n\n"
            "Se não foi você, avise o administrador agora." + _assinatura_do_email())


# ====================================================================== entrar por um aparelho novo
def aparelho_novo(usuario, endereco=None):
    """True se a pessoa já entrou antes, mas nunca por este endereço de rede (com o Tailscale cada aparelho tem o seu endereço 100.x). A
    primeira entrada de uma conta não conta (não há com o que comparar), e o endereço local do servidor também não."""
    endereco = request.remote_addr if endereco is None else endereco
    if not endereco or endereco in autenticacao.ENDERECOS_LOCAIS:
        return False
    consulta = db.select(db.func.count()).select_from(auditoria.Evento).filter(auditoria.Evento.acao == "login.ok", auditoria.Evento.usuario == usuario.nome)
    if not db.session.execute(consulta).scalar():
        return False
    return not db.session.execute(consulta.filter(auditoria.Evento.endereco == endereco)).scalar()


def registrar_entrada(usuario, detalhe=""):
    """Registra que a pessoa entrou e, se foi por um aparelho novo, avisa por e-mail (a própria pessoa; se for administrador, também quem recebe
    os avisos da casa) e deixa isso na auditoria. Nunca atrapalha a entrada."""
    novo = False
    try:
        novo = aparelho_novo(usuario)
    except Exception:                                  # noqa: BLE001 — o aviso é cortesia
        log.exception("Não consegui conferir se o aparelho é novo")
    auditoria.registrar("login.ok", usuario=usuario.nome, detalhe=detalhe)
    if not novo:
        return
    auditoria.registrar("login.aparelho_novo", usuario=usuario.nome)
    if not email_envio.configurado(_instance()):
        return
    funcionario = funcionario_de(usuario)
    texto = (f"O usuário {usuario.nome} entrou no sistema agora ({datetime.now():%d/%m/%Y às %H:%M}) por um aparelho que ainda não tinha usado "
             f"(endereço {request.remote_addr}).\n\nSe foi você (computador ou celular novo), pode ignorar esta mensagem. Se não foi, avise o "
             "administrador agora e troque a sua senha." + _assinatura_do_email())
    _avisar(funcionario, "Entrada por um aparelho novo", texto)
    if e_administrador(usuario) and (casa := email_envio.avisos_para(_instance())):
        destinos = [e for e in casa if not (funcionario is not None and e.lower() == (funcionario.email or "").lower())]
        if destinos:
            email_envio.enviar_em_segundo_plano(_instance(), destinos, "Administrador entrou por um aparelho novo", texto)


# ====================================================================== esqueci minha senha
def _pedidos_do_endereco(endereco, agora):
    return db.session.execute(db.select(db.func.count()).select_from(auditoria.Evento).filter(
        auditoria.Evento.acao == "senha.pedido_reset", auditoria.Evento.endereco == endereco, auditoria.Evento.quando >= agora - timedelta(hours=1))).scalar()


def pedir_redefinicao(nome, endereco="", agora=None):
    """O pedido de "esqueci minha senha". NUNCA diz se o usuário existe: devolve None sempre, e a tela responde igual. Se há como enviar
    (usuário ativo, funcionário ativo, e-mail confirmado, envio e endereço do sistema configurados), cria o link e envia em segundo plano.
    Devolve o texto de um problema que vale para QUALQUER pessoa (envio não configurado), ou None."""
    agora = _agora(agora)
    config = email_envio.carregar(_instance())
    usuario = autenticacao.buscar_por_login(nome)
    auditoria.registrar("senha.pedido_reset", usuario=usuario.nome if usuario else "")
    if config is None or not config["endereco_do_sistema"]:
        return MENSAGEM_ENVIO_NAO_CONFIGURADO
    if endereco and endereco not in autenticacao.ENDERECOS_LOCAIS and _pedidos_do_endereco(endereco, agora) > MAX_PEDIDOS_POR_ENDERECO:
        return None
    if usuario is None or not usuario.ativo or cadastros.acesso_desativado(usuario):
        return None
    funcionario = funcionario_de(usuario)
    if not email_confirmado(funcionario) or _limite_de_envios(usuario.id, "senha", agora):
        return None
    if e_administrador(usuario) and not usuario.totp_ativo:
        email_envio.enviar_em_segundo_plano(
            _instance(), funcionario.email, "Redefinir a senha de administrador",
            "Alguém pediu para redefinir a senha deste usuário de administrador.\n\nPor segurança, a senha de administrador só pode ser redefinida "
            "por e-mail quando o segundo fator (aplicativo autenticador) está ativado, e ele ainda não está. Peça a quem cuida do servidor para "
            "redefinir a senha pelo terminal.\nSe não foi você que pediu, ignore esta mensagem." + _assinatura_do_email())
        return None
    token = secrets.token_urlsafe(32)
    _invalidar_anteriores(usuario.id, "senha", agora)
    db.session.add(CodigoSeguranca(usuario_id=usuario.id, finalidade="senha", resumo=_resumo(token), destino=funcionario.email,
                                   criado_em=agora, expira_em=agora + VALIDADE_DO_LINK_DA_SENHA))
    db.session.commit()
    email_envio.enviar_em_segundo_plano(
        _instance(), funcionario.email, "Redefinir a sua senha",
        f"Alguém pediu para redefinir a senha do usuário {usuario.nome}.\n\nPara escolher uma senha nova, abra este link (vale por 30 minutos e só pode ser usado uma vez):\n"
        f"{config['endereco_do_sistema']}/senha/redefinir/{token}\n\nSe não foi você que pediu, ignore esta mensagem: a sua senha não muda."
        + _assinatura_do_email())
    return None


def link_valido(token, agora=None):
    """(registro do código, usuário) se o link vale (existe, não foi usado, não venceu, usuário ativo); senão None."""
    agora = _agora(agora)
    if not token or len(token) > 100:
        return None
    codigo = db.session.execute(db.select(CodigoSeguranca).filter_by(resumo=_resumo(token), finalidade="senha", usado_em=None)
                                .filter(CodigoSeguranca.expira_em > agora)).scalars().first()
    usuario = db.session.get(Usuario, codigo.usuario_id) if codigo else None
    if codigo is None or usuario is None or not usuario.ativo or cadastros.acesso_desativado(usuario):
        return None
    return codigo, usuario


def concluir_redefinicao(token, nova, confirmacao, segundo_fator="", agora=None):
    """Troca a senha pelo link. Devolve o erro (texto) ou None. Senha fraca ou código errado não gastam o link (até 5 códigos errados)."""
    agora = _agora(agora)
    achado = link_valido(token, agora)
    if achado is None:
        return "Este link não vale mais. Peça um novo em \"Esqueci minha senha\"."
    codigo, usuario = achado
    if e_administrador(usuario) and not usuario.totp_ativo:
        return "A senha de administrador só pode ser redefinida por e-mail com o segundo fator ativado."
    if nova != confirmacao:
        return "A confirmação não é igual à senha nova."
    if usuario.totp_ativo:
        codigo.tentativas += 1
        if codigo.tentativas > MAX_TENTATIVAS:
            codigo.usado_em = agora
            db.session.commit()
            return "Muitos códigos errados. Este link foi cancelado: peça um novo."
        if verificar_segundo_fator(usuario, segundo_fator, agora) is None:
            db.session.commit()
            return "Informe o código do aplicativo autenticador (ou um código de recuperação)."
    funcionario = funcionario_de(usuario)
    if erro := autenticacao.definir_senha(usuario, nova, nomes=[funcionario.nome] if funcionario else (), confirmar=False):
        db.session.rollback()
        return erro
    codigo.usado_em = agora
    db.session.commit()
    auditoria.registrar("senha.redefinida_por_email", "funcionario", funcionario.id if funcionario else None, usuario=usuario.nome)
    _avisar(funcionario, "A sua senha foi alterada", f"A senha do usuário {usuario.nome} foi alterada agora, pelo link de \"Esqueci minha senha\".\n\n"
            "Se não foi você, avise o administrador agora." + _assinatura_do_email())
    return None


# ====================================================================== segundo fator
def iniciar_ativacao(usuario):
    """Gera um segredo novo (guardado cifrado, ainda inativo) e devolve o que a tela mostra: o QR em SVG, o segredo para digitar e o endereço."""
    segredo = totp.novo_segredo()
    usuario.totp_segredo, usuario.totp_ativo, usuario.totp_ultimo_passo = totp.cifrar(segredo, _chave_mestra()), False, 0
    db.session.commit()
    return _para_mostrar(usuario, segredo)


def _para_mostrar(usuario, segredo):
    endereco = totp.endereco_otpauth(segredo, usuario.nome)
    try:
        svg = totp.qr_em_svg(endereco)
    except ImportError:                                  # sem a biblioteca do QR, a pessoa digita o segredo no aplicativo
        svg = ""
    return {"segredo": totp.segredo_para_digitar(segredo), "endereco": endereco, "qr": svg}


def ativacao_pendente(usuario):
    """O que mostrar de novo se a pessoa recarregar a página de ativação (o segredo guardado, ainda inativo), ou None."""
    if usuario.totp_ativo or not usuario.totp_segredo:
        return None
    segredo = totp.decifrar(usuario.totp_segredo, _chave_mestra())
    return _para_mostrar(usuario, segredo) if segredo else None


def confirmar_ativacao(usuario, digitado, agora=None):
    """Confere o primeiro código do aplicativo. Devolve os 8 códigos de recuperação (mostrados uma só vez) ou None se o código não confere."""
    segredo = totp.decifrar(usuario.totp_segredo, _chave_mestra()) if usuario.totp_segredo else None
    passo = totp.verificar(segredo, digitado, 0, None if agora is None else agora.timestamp()) if segredo else None
    if passo is None:
        return None
    codigos, resumos = totp.gerar_codigos_de_recuperacao()
    usuario.totp_ativo, usuario.totp_ultimo_passo, usuario.totp_recuperacao = True, passo, resumos
    db.session.commit()
    auditoria.registrar("totp.ativado", usuario=usuario.nome)
    _avisar(funcionario_de(usuario), "Segundo fator ativado", f"O segundo fator (aplicativo autenticador) foi ativado no usuário {usuario.nome}."
            "\n\nSe não foi você, avise o administrador agora." + _assinatura_do_email())
    return codigos


def desativar(usuario, por=""):
    """Desliga o segundo fator (a própria pessoa, com a senha, ou o administrador, quando o celular se perdeu)."""
    usuario.totp_segredo, usuario.totp_ativo, usuario.totp_ultimo_passo, usuario.totp_recuperacao = "", False, 0, ""
    db.session.commit()
    auditoria.registrar("totp.desativado", usuario=por or usuario.nome, detalhe=f"usuário {usuario.nome}")
    _avisar(funcionario_de(usuario), "Segundo fator desativado", f"O segundo fator (aplicativo autenticador) foi desativado no usuário {usuario.nome}."
            "\n\nSe não foi você, avise o administrador agora." + _assinatura_do_email())


def verificar_segundo_fator(usuario, digitado, agora=None):
    """Confere o código do aplicativo ou um de recuperação. Devolve "app", "recuperacao" ou None. Um código só vale uma vez."""
    segredo = totp.decifrar(usuario.totp_segredo, _chave_mestra()) if usuario.totp_segredo else None
    if segredo:
        passo = totp.verificar(segredo, digitado, usuario.totp_ultimo_passo, None if agora is None else agora.timestamp())
        if passo is not None:
            usuario.totp_ultimo_passo = passo
            db.session.commit()
            return "app"
    aceito, restantes = totp.usar_codigo_de_recuperacao(usuario.totp_recuperacao, digitado)
    if aceito:
        usuario.totp_recuperacao = restantes
        db.session.commit()
        auditoria.registrar("totp.recuperacao_usada", usuario=usuario.nome, detalhe=f"restam {totp.quantos_codigos_de_recuperacao(restantes)}")
        return "recuperacao"
    return None


# ====================================================================== o que a conta ainda pede (para o quadro de avisos)
def pendencias_da_conta(usuario):
    """O que a própria pessoa ainda precisa fazer na segurança da conta: lista de (chave, texto)."""
    if usuario is None:
        return []
    funcionario = funcionario_de(usuario)
    lista = []
    if funcionario is not None and funcionario.email and not funcionario.email_confirmado_em:
        lista.append(("conta:email", "O seu e-mail ainda não foi confirmado: sem ele você não consegue redefinir a senha sozinho."))
    if e_administrador(usuario) and not usuario.totp_ativo:
        lista.append(("conta:totp", "Ative o segundo fator (aplicativo autenticador no celular): o administrador pode ver e apagar tudo."))
    elif usuario.totp_ativo and totp.quantos_codigos_de_recuperacao(usuario.totp_recuperacao) <= 2:
        lista.append(("conta:recuperacao", "Restam poucos códigos de recuperação do segundo fator. Desative e ative de novo para gerar códigos novos."))
    return lista


# ====================================================================== comandos do administrador no servidor
def registrar_comandos(app):
    @app.cli.command("configurar-email")
    @click.option("--servidor", default=email_envio.PADRAO_HOSTINGER["servidor"], show_default=True)
    @click.option("--porta", default=email_envio.PADRAO_HOSTINGER["porta"], type=int, show_default=True)
    @click.option("--seguranca", type=click.Choice(email_envio.SEGURANCAS), default=email_envio.PADRAO_HOSTINGER["seguranca"], show_default=True)
    @click.option("--usuario", prompt="Caixa de envio (o endereço completo, ex.: sistema@restauracao.org.br)")
    @click.option("--senha", prompt="Senha da caixa de envio (não aparece na tela)", hide_input=True, confirmation_prompt=True)
    @click.option("--endereco-do-sistema", prompt="Endereço do sistema para os links dos e-mails (ex.: http://192.168.15.19:8000)")
    @click.option("--avisos-para", prompt="Quem recebe os avisos do sistema (e-mails separados por vírgula)", default="")
    def configurar_email_cmd(servidor, porta, seguranca, usuario, senha, endereco_do_sistema, avisos_para):
        """Guarda em instance/email.json a caixa que o sistema usa para enviar e-mail (a senha é digitada aqui, nunca no código)."""
        if not email_envio.endereco_valido(usuario):
            raise click.ClickException("A caixa de envio precisa ser um e-mail completo.")
        destinos = [e.strip() for e in avisos_para.split(",") if e.strip()]
        invalidos = [e for e in destinos if not email_envio.endereco_valido(e)]
        if invalidos:
            raise click.ClickException(f"E-mail inválido em quem recebe os avisos: {', '.join(invalidos)}")
        if not endereco_do_sistema.lower().startswith(("http://", "https://")):
            raise click.ClickException("O endereço do sistema precisa começar com http:// ou https://")
        email_envio.gravar_configuracao(current_app.instance_path, {"servidor": servidor, "porta": porta, "seguranca": seguranca, "usuario": usuario, "senha": senha,
                                                                    "remetente": "Sistema de prontuários", "endereco_do_sistema": endereco_do_sistema.rstrip("/"),
                                                                    "avisos_para": destinos})
        click.echo("Configuração guardada em instance\\email.json. Teste o envio com:  flask --app app testar-email SEU@EMAIL")

    @app.cli.command("testar-email")
    @click.argument("destino")
    def testar_email_cmd(destino):
        """Manda um e-mail de teste para conferir a configuração."""
        try:
            email_envio.enviar(current_app.instance_path, destino, "Teste do sistema de prontuários",
                               "Se você recebeu esta mensagem, o envio de e-mail do sistema está funcionando." + _assinatura_do_email())
        except email_envio.ErroDeEmail as erro:
            raise click.ClickException(str(erro)) from erro
        click.echo(f"E-mail de teste enviado para {destino}.")

    @app.cli.command("endereco-do-sistema")
    @click.argument("endereco", required=False)
    def endereco_do_sistema_cmd(endereco):
        """Mostra ou muda o endereço que vai nos links dos e-mails (instance/email.json), por exemplo depois de ligar o HTTPS."""
        atual = email_envio.endereco_do_arquivo(current_app.instance_path)
        if not endereco:
            click.echo(atual or "Ainda não há endereço: configure o e-mail (implantacao\\configurar-email.ps1).")
            return
        if not endereco.lower().startswith(("http://", "https://")):
            raise click.ClickException("O endereço precisa começar com http:// ou https://")
        try:
            email_envio.mudar_endereco_do_sistema(current_app.instance_path, endereco)
        except email_envio.ErroDeEmail as erro:
            raise click.ClickException(str(erro)) from erro
        click.echo(f"Os links dos e-mails agora usam {endereco.rstrip('/')}")

    @app.cli.command("confirmar-email")
    @click.argument("nome")
    def confirmar_email_cmd(nome):
        """Marca como confirmado o e-mail de um usuário (emergência: o envio de e-mail está fora do ar e uma pessoa nova precisa entrar)."""
        usuario = autenticacao.buscar_usuario(nome)
        dono = db.session.execute(db.select(Funcionario).filter_by(usuario=usuario.nome)).scalars().first() if usuario else None
        if usuario is None or dono is None:
            raise click.ClickException(f"Não achei um funcionário com o usuário {nome}.")
        if not dono.email:
            raise click.ClickException("Esse funcionário ainda não tem e-mail cadastrado (Cadastros > Funcionários).")
        dono.email_confirmado_em = datetime.now()
        usuario.exigir_email = False
        db.session.commit()
        auditoria.registrar("email.confirmado", "funcionario", dono.id, usuario="terminal", detalhe=f"pelo terminal ({email_envio.mascarar(dono.email)})")
        click.echo(f"E-mail de {usuario.nome} marcado como confirmado.")

    @app.cli.command("desativar-segundo-fator")
    @click.argument("nome")
    def desativar_totp_cmd(nome):
        """Desliga o segundo fator de um usuário (celular perdido e sem os códigos de recuperação)."""
        usuario = autenticacao.buscar_usuario(nome)
        if usuario is None:
            raise click.ClickException(f"O usuário {nome} não existe.")
        desativar(usuario, por="terminal")
        click.echo(f"Segundo fator de {usuario.nome} desativado. Ele entra só com a senha e pode ativar de novo em Minha segurança.")
