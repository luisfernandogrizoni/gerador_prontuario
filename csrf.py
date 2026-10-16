"""
Defesa do navegador (plano de segurança, fase 7: docs/plano-de-seguranca.md): token CSRF, política de conteúdo (CSP) e cabeçalhos.

**Token CSRF.** Um site de outra pessoa pode fazer o navegador de quem está logado mandar um formulário para este sistema (o cookie de
login vai junto). O cookie `SameSite=Lax` já barra a maior parte, mas não é a garantia: aqui, **todo envio que muda coisas** (POST e
afins) só vale com o token que a página do próprio sistema recebeu.

  * o token vai na sessão (assinada) e é gerado na primeira página; `abrir_sessao` limpa a sessão, então ele muda a cada entrada;
  * os formulários levam `<input type="hidden" name="csrf_token">` e as chamadas do JavaScript levam o cabeçalho `X-CSRF-Token`
    (static/base.js põe o cabeçalho em todo `fetch` do próprio sistema e cobre formulário criado por script);
  * envio sem token, ou com token que não confere: 400, uma tela explicando (ou JSON, nas chamadas do JavaScript) e o fato vai para a
    auditoria (`csrf.recusado`, só a rota, nunca o que foi digitado). A comparação é em tempo constante;
  * a única exceção é o relatório do navegador sobre a política de conteúdo (`csp_relatorio`), que o navegador manda sozinho.

**Política de conteúdo (CSP).** Diz ao navegador de onde a página pode carregar script, estilo e imagem, e o que pode chamar:
só do próprio sistema (e o ViaCEP, que preenche o endereço pelo CEP). Script ou estilo escrito dentro da página só roda com o **nonce** da
resposta (um código novo a cada página, que o servidor põe nas suas próprias tags): quem conseguir injetar um `<script>` na página
não leva nada para rodar. Atributos de evento (`onclick=`) não existem mais; o comportamento vem de `data-*` + static/base.js.
`CSP_SOMENTE_RELATORIO=1` põe a política em modo "só avisar" (o navegador não bloqueia, só manda o relatório para `/csp-relatorio`,
que escreve uma linha curta em logs/servidor.log): serve para achar o que a política barraria, sem derrubar nenhuma tela.
"""

import hmac
import logging
import secrets
import time

from flask import current_app, g, jsonify, render_template, request, session

import auditoria
from modelos import Usuario, db

log = logging.getLogger(__name__)

CAMPO = "csrf_token"
CABECALHO = "X-CSRF-Token"
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}
ROTAS_SEM_TOKEN = {"static", "csp_relatorio"}        # o relatório da CSP vem do navegador, sem o token; arquivos estáticos não mudam nada
MENSAGEM = ("Por segurança, o sistema não aceitou este envio: a página ficou aberta por muito tempo, a sessão terminou ou o pedido não veio "
            "do próprio sistema. Recarregue a página (ou entre de novo) e tente outra vez.")

# de onde cada coisa pode vir. `connect-src` leva o ViaCEP (static/formularios.js); o resto é só o próprio sistema.
POLITICA = {
    "default-src": "'self'",
    "img-src": "'self' data:",
    "font-src": "'self'",
    "connect-src": "'self' https://viacep.com.br",
    "form-action": "'self'",
    "frame-ancestors": "'none'",
    "base-uri": "'self'",
    "object-src": "'none'",
    "style-src-attr": "'unsafe-inline'",     # style="..." dentro das tags (só estilo, não roda código); os blocos <style> exigem o nonce
    "report-uri": "/csp-relatorio",
}


def token():
    """O token desta sessão (criado na primeira vez que alguém pede)."""
    valor = session.get("csrf")
    if not valor:
        valor = session["csrf"] = secrets.token_urlsafe(32)
    return valor


def nonce():
    """O código desta resposta para as tags <script> e <style> escritas dentro da página."""
    if "csp_nonce" not in g:
        g.csp_nonce = secrets.token_urlsafe(16)
    return g.csp_nonce


def _quer_json():
    return request.path.startswith("/api/") or request.is_json or "application/json" in (request.headers.get("Accept") or "")


def verificar():
    """before_request (o primeiro de todos): recusa o envio que muda coisas sem o token certo."""
    if not current_app.config.get("CSRF_ATIVO", True):
        return None
    if request.method in METODOS_SEGUROS or request.endpoint in ROTAS_SEM_TOKEN:
        return None
    esperado = session.get("csrf") or ""
    enviado = request.headers.get(CABECALHO) or request.form.get(CAMPO) or ""
    if esperado and enviado and hmac.compare_digest(esperado.encode("utf-8"), enviado.encode("utf-8")):
        return None
    quem = db.session.get(Usuario, session["usuario_id"]) if session.get("usuario_id") else None        # (este gancho vem antes do login: ainda não há g.usuario)
    auditoria.registrar("csrf.recusado", detalhe=f"{request.method} {request.endpoint or request.path}"[:100], usuario=quem.nome if quem else "")
    if _quer_json():
        return jsonify(ok=False, erros={"csrf": MENSAGEM}), 400
    return render_template("erro.html", codigo=400, titulo="A página venceu", texto=MENSAGEM), 400


def politica():
    """O texto do cabeçalho Content-Security-Policy desta resposta (com o nonce dela)."""
    n = nonce()
    partes = dict(POLITICA)
    partes["script-src"] = f"'self' 'nonce-{n}'"
    partes["style-src"] = f"'self' 'nonce-{n}'"
    return "; ".join(f"{k} {v}" for k, v in partes.items())


def cabecalhos(resposta):
    """after_request: a política de conteúdo (nas páginas) e os cabeçalhos que fecham o que o navegador não precisa."""
    resposta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
    resposta.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resposta.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if request.endpoint != "static" and (resposta.mimetype or "") == "text/html" and current_app.config.get("CSP_ATIVA", True):
        nome = "Content-Security-Policy-Report-Only" if current_app.config.get("CSP_SOMENTE_RELATORIO") else "Content-Security-Policy"
        resposta.headers[nome] = politica()
    return resposta


# ---------------------------------------------------------------- o relatório que o navegador manda quando a política barra algo
_recentes = []                 # instantes dos últimos relatórios aceitos (limita o que um aparelho mal-intencionado consegue escrever no registro)
LIMITE_POR_MINUTO = 20


def relatorio():
    """POST /csp-relatorio: uma linha curta no registro do servidor (diretiva, o que foi barrado e em qual página, sem consulta nem conteúdo)."""
    agora = time.time()
    _recentes[:] = [t for t in _recentes if agora - t < 60]
    if len(_recentes) >= LIMITE_POR_MINUTO or (request.content_length or 0) > 8192:
        return "", 204
    _recentes.append(agora)
    try:
        dados = request.get_json(force=True, silent=True) or {}
        corpo = dados.get("csp-report") or dados
        if not isinstance(corpo, dict):
            corpo = {}
    except Exception:                                   # noqa: BLE001
        corpo = {}

    def curto(chave, tamanho=80):
        valor = str(corpo.get(chave) or corpo.get(chave.replace("-", "")) or "")
        return valor.split("?")[0].split("#")[0][:tamanho]          # sem consulta: pode ter nome de gente
    log.warning("CSP: a política barrou %s (%s) em %s", curto("blocked-uri") or "um conteúdo", curto("violated-directive") or curto("effective-directive") or "?",
                curto("document-uri", 120))
    return "", 204
