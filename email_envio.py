"""
Envio de e-mail pelo sistema (plano de segurança, fase 3: docs/plano-de-seguranca.md).

Usa a caixa da própria casa (a de envio, por exemplo sistema@restauracao.org.br, na Hostinger) por SMTP com usuário e senha:
servidor, porta (465 com SSL, ou 587 com STARTTLS) e a senha ficam em instance/email.json, que só o SISTEMA e os administradores do
Windows leem. **A senha nunca vai para o código nem para o repositório**: quem a digita é o administrador, uma vez, no servidor
(`flask --app app configurar-email`, ou implantacao\\configurar-email.ps1), e o terminal não a mostra.

    {"servidor": "smtp.hostinger.com", "porta": 465, "seguranca": "ssl", "usuario": "sistema@restauracao.org.br",
     "senha": "...", "remetente": "Sistema de prontuários", "endereco_do_sistema": "http://192.168.15.19:8000",
     "avisos_para": ["financeiro@restauracao.org.br"]}

Em hospedagem sem terminal as mesmas coisas vêm de variáveis de ambiente (SMTP_SERVIDOR, SMTP_PORTA, SMTP_SEGURANCA, SMTP_USUARIO,
SMTP_SENHA, SMTP_REMETENTE, ENDERECO_DO_SISTEMA, AVISOS_PARA).

  * O certificado do servidor é sempre conferido (nada de "aceitar qualquer certificado").
  * `endereco_do_sistema` é o endereço que vai nos links dos e-mails (o do "esqueci minha senha"). Ele vem da configuração e **nunca do
    pedido** que chegou: quem pode mandar o cabeçalho Host poderia, senão, fazer o link do e-mail apontar para outro site.
  * O texto dos e-mails (que traz códigos e links) e a senha **nunca** vão para o registro do servidor.
  * Enviar pode demorar (a rede, o servidor de e-mail): o sistema envia em segundo plano, para a tela responder igual com ou sem e-mail.
"""

import json
import logging
import os
import re
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

log = logging.getLogger(__name__)

ARQUIVO = "email.json"
SEGURANCAS = ("ssl", "starttls", "nenhuma")
SINCRONO = False        # os testes ligam: envia na hora, em vez de em segundo plano
PADRAO_HOSTINGER = {"servidor": "smtp.hostinger.com", "porta": 465, "seguranca": "ssl"}
_PADRAO_DE_ENDERECO = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]{2,}$")


class ErroDeEmail(Exception):
    """Falha esperada no envio (sem configuração, servidor fora, senha recusada): a mensagem é para a pessoa ler, sem segredo nenhum."""


def endereco_valido(texto):
    """Um endereço de e-mail com cara de e-mail (não prova que existe: quem prova é o código que chega nele)."""
    texto = (texto or "").strip()
    return bool(len(texto) <= 120 and _PADRAO_DE_ENDERECO.fullmatch(texto))


def mascarar(email):
    """financeiro@restauracao.org.br -> f*******@restauracao.org.br"""
    nome, _, dominio = (email or "").partition("@")
    return (nome[:1] + "*" * max(len(nome) - 1, 2) + "@" + dominio) if dominio else ""


# ====================================================================== a configuração
def arquivo_da_configuracao(instance):
    return Path(instance) / ARQUIVO


def _do_ambiente():
    dados = {}
    for chave, variavel in (("servidor", "SMTP_SERVIDOR"), ("porta", "SMTP_PORTA"), ("seguranca", "SMTP_SEGURANCA"), ("usuario", "SMTP_USUARIO"),
                            ("senha", "SMTP_SENHA"), ("remetente", "SMTP_REMETENTE"), ("endereco_do_sistema", "ENDERECO_DO_SISTEMA")):
        if os.environ.get(variavel):
            dados[chave] = os.environ[variavel]
    if os.environ.get("AVISOS_PARA"):
        dados["avisos_para"] = [e.strip() for e in os.environ["AVISOS_PARA"].split(",") if e.strip()]
    return dados


def carregar(instance):
    """A configuração (arquivo e depois variáveis de ambiente), já com os tipos certos, ou None se falta algo para enviar."""
    dados = {}
    try:
        dados.update(json.loads(arquivo_da_configuracao(instance).read_text(encoding="utf-8-sig")))
    except (OSError, ValueError):
        pass
    dados.update(_do_ambiente())
    try:
        dados["porta"] = int(dados.get("porta") or 0)
    except (TypeError, ValueError):
        dados["porta"] = 0
    dados["seguranca"] = (dados.get("seguranca") or "ssl").lower()
    if not (dados.get("servidor") and dados["porta"] and dados.get("usuario") and dados.get("senha") and dados["seguranca"] in SEGURANCAS):
        return None
    dados.setdefault("remetente", "Sistema de prontuários")
    dados["avisos_para"] = [e for e in dados.get("avisos_para") or [] if endereco_valido(e)]
    dados["endereco_do_sistema"] = (dados.get("endereco_do_sistema") or "").rstrip("/")
    return dados


def configurado(instance):
    return carregar(instance) is not None


def gravar_configuracao(instance, dados):
    """Grava instance/email.json (por um arquivo provisório). Quem chama é o comando do administrador no servidor."""
    arquivo = arquivo_da_configuracao(instance)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    provisorio = arquivo.with_name(arquivo.name + ".tmp")
    provisorio.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(provisorio, 0o600)
    except OSError:
        pass
    os.replace(provisorio, arquivo)


def endereco_do_sistema(instance):
    """O endereço do sistema para os links dos e-mails, ou '' se ainda não foi informado (sem ele, o "esqueci minha senha" não sai)."""
    config = carregar(instance)
    return config["endereco_do_sistema"] if config else ""


def avisos_para(instance):
    config = carregar(instance)
    return config["avisos_para"] if config else []


# ====================================================================== enviar
def montar(config, destinos, assunto, texto):
    mensagem = EmailMessage()
    mensagem["From"] = formataddr((config["remetente"], config["usuario"]))
    mensagem["To"] = ", ".join(destinos)
    mensagem["Subject"] = " ".join(str(assunto).split())      # (uma quebra de linha no assunto criaria um cabeçalho novo)
    mensagem["Date"] = formatdate(localtime=True)
    mensagem["Message-ID"] = make_msgid(domain=config["usuario"].partition("@")[2] or None)
    mensagem["Auto-Submitted"] = "auto-generated"            # resposta automática de alguém não deve gerar outra
    mensagem.set_content(texto, charset="utf-8")
    return mensagem


def enviar(instance, destinos, assunto, texto, contexto=None, timeout=20):
    """Envia agora e espera. Levanta ErroDeEmail (com texto seguro) se não deu."""
    config = carregar(instance)
    if config is None:
        raise ErroDeEmail("O envio de e-mail ainda não foi configurado neste servidor.")
    destinos = [d.strip() for d in ([destinos] if isinstance(destinos, str) else destinos) if endereco_valido(d)]
    if not destinos:
        raise ErroDeEmail("Não há um endereço de e-mail válido para enviar.")
    mensagem = montar(config, destinos, assunto, texto)
    contexto = contexto or ssl.create_default_context()
    servidor = None
    try:
        if config["seguranca"] == "ssl":
            servidor = smtplib.SMTP_SSL(config["servidor"], config["porta"], timeout=timeout, context=contexto)
        else:
            servidor = smtplib.SMTP(config["servidor"], config["porta"], timeout=timeout)
            servidor.ehlo()
            if config["seguranca"] == "starttls":
                servidor.starttls(context=contexto)
                servidor.ehlo()
        servidor.login(config["usuario"], config["senha"])
        servidor.send_message(mensagem)
        servidor.quit()
    except smtplib.SMTPAuthenticationError as erro:
        raise ErroDeEmail("O servidor de e-mail recusou o usuário e a senha da caixa de envio.") from erro
    except smtplib.SMTPRecipientsRefused as erro:
        raise ErroDeEmail("O servidor de e-mail recusou o endereço de destino.") from erro
    except ssl.SSLError as erro:
        raise ErroDeEmail("Não consegui confirmar o certificado do servidor de e-mail (conexão segura recusada).") from erro
    except (smtplib.SMTPException, OSError) as erro:
        raise ErroDeEmail(f"Não consegui falar com o servidor de e-mail ({type(erro).__name__}).") from erro
    finally:
        if servidor is not None:
            try:
                servidor.close()
            except OSError:
                pass


def enviar_em_segundo_plano(instance, destinos, assunto, texto, depois=None):
    """Envia sem fazer a tela esperar. Falha vai para o registro do servidor (sem o texto nem segredo); `depois(erro_ou_None)` é chamado
    ao terminar (usado nos testes e para anotar o resultado)."""
    def trabalho():
        erro = None
        try:
            enviar(instance, destinos, assunto, texto)
        except ErroDeEmail as e:
            erro = str(e)
            log.warning("E-mail \"%s\" não enviado: %s", assunto, e)
        except Exception:                                    # noqa: BLE001
            erro = "erro inesperado"
            log.exception("Falha inesperada ao enviar o e-mail \"%s\"", assunto)
        if depois:
            depois(erro)
    if SINCRONO:
        trabalho()
        return None
    fio = threading.Thread(target=trabalho, name="envio-de-email", daemon=True)
    fio.start()
    return fio
