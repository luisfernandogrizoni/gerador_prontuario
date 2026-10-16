// Tempo de inatividade da sessão (autenticacao.OCIOSO): sem uso, a sessão acaba. Aos 25 minutos abre um aviso com a contagem;
// "Manter conectado" (ou qualquer uso do sistema antes disso) mantém a sessão; no fim do tempo a pessoa volta para a entrada.
// Digitar, clicar, rolar e tocar contam como uso; a cada ~2 minutos de uso o navegador avisa o servidor (POST /sessao/ping).
// A atividade é compartilhada entre as abas do mesmo navegador (localStorage): usar uma aba segura as outras.
(function () {
  var script = document.currentScript;
  var janela = document.getElementById("aviso-ocioso");
  if (!script || !janela || !janela.showModal) return;
  var LIMITE = parseInt(script.dataset.ocioso, 10) * 1000;
  var AVISO = parseInt(script.dataset.aviso, 10) * 1000;
  var ENTRE_PINGS = 2 * 60 * 1000;
  var CHAVE = "prontuario:ultimo-uso";
  var contagem = document.getElementById("ocioso-contagem");
  var ultimoUso = Date.now();
  var ultimoPing = Date.now();
  var encerrando = false;

  function guardar(t) { try { localStorage.setItem(CHAVE, String(t)); } catch (e) { /* sem armazenamento: vale só esta aba */ } }
  function lerGuardado() { try { return parseInt(localStorage.getItem(CHAVE), 10) || 0; } catch (e) { return 0; } }
  function maisRecente() { return Math.max(ultimoUso, lerGuardado()); }

  guardar(ultimoUso);                              // abrir uma página também é uso (vale para as outras abas)

  function usou() {
    if (encerrando || janela.open) return;          // com o aviso aberto, só os botões contam
    ultimoUso = Date.now();
    if (ultimoUso - lerGuardado() > 1000) guardar(ultimoUso);
  }
  ["keydown", "click", "scroll", "touchstart", "pointerdown", "wheel"].forEach(function (nome) {
    document.addEventListener(nome, usou, { passive: true, capture: true });
  });
  // mexer o mouse também conta, mas sem gravar a cada pixel
  var mexeu = 0;
  document.addEventListener("mousemove", function () { var t = Date.now(); if (t - mexeu > 5000) { mexeu = t; usou(); } }, { passive: true });

  function avisarServidor() {
    ultimoPing = Date.now();
    return fetch(script.dataset.ping, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: "{}" })
      .then(function (r) { if (r.status === 401) encerrar(); return r.ok; })
      .catch(function () { return false; });             // sem rede agora: tenta de novo no próximo ciclo
  }

  function encerrar() {
    if (encerrando) return;
    encerrando = true;
    // a sessão já acabou no servidor (ou acaba agora); a entrada explica o motivo
    window.location.replace(script.dataset.sair);
  }

  function formatar(ms) {
    var s = Math.max(0, Math.ceil(ms / 1000));
    return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2);
  }

  function fechar() { if (janela.open) janela.close(); }

  document.getElementById("ocioso-continuar").addEventListener("click", function () {
    ultimoUso = Date.now(); guardar(ultimoUso);
    fechar();
    avisarServidor();
  });
  document.getElementById("ocioso-sair").addEventListener("click", function () {
    var f = document.createElement("form");
    f.method = "post"; f.action = script.dataset.sairAgora;
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) { var campo = document.createElement("input"); campo.type = "hidden"; campo.name = "csrf_token"; campo.value = meta.content; f.appendChild(campo); }
    document.body.appendChild(f);
    f.submit();
  });
  janela.addEventListener("cancel", function (e) { e.preventDefault(); });      // Esc não fecha: só "Manter conectado" mantém a sessão

  setInterval(function () {
    if (encerrando) return;
    var parado = Date.now() - maisRecente();
    if (parado >= LIMITE) { encerrar(); return; }
    if (parado >= AVISO) {
      if (!janela.open) janela.showModal();
      if (contagem) contagem.textContent = formatar(LIMITE - parado);
      return;
    }
    // voltou a ser usado (nesta ou em outra aba) com o aviso aberto: some sozinho
    if (janela.open) fechar();
    if (Date.now() - ultimoPing >= ENTRE_PINGS && maisRecente() > ultimoPing) avisarServidor();
  }, 1000);
})();
