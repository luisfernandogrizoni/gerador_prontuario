// Salvamento automático dos formulários (rascunhos.py). A página que tem um <input type="hidden" name="rascunho" data-rascunho-tipo="..."> manda
// uma cópia do que foi digitado para o servidor a cada pausa na digitação (e antes de a aba fechar), para uma queda de energia, uma aba fechada
// sem querer ou a rede que cai não custarem o trabalho. A cópia é um RASCUNHO: não valida nem grava no prontuário; só o botão Salvar grava.
//  - o texto da barra de salvar (.estado-form) diz em que pé está: alterações a caminho, rascunho salvo às HH:MM, ou o que deu errado;
//  - o navegador só avisa antes de sair se há texto que NÃO chegou ao servidor (digitou agora há pouco, ou a rede/sessão falhou);
//  - senha, token da página e o botão apertado nunca vão (o servidor também descarta).
(function () {
  var marca = document.querySelector('input[name="rascunho"][data-rascunho-tipo]');
  if (!marca || !marca.form || !window.fetch) return;

  var form = marca.form;
  var tipo = marca.dataset.rascunhoTipo;
  var alvo = marca.dataset.rascunhoAlvo ? parseInt(marca.dataset.rascunhoAlvo, 10) : null;
  var token = marca.value;
  var ESPERA = 2500;          // ms parados até guardar
  var TETO = 20000;           // ms digitando sem parar até guardar assim mesmo
  var NOS_FORA = { csrf_token: 1, rascunho: 1, acao: 1 };

  // ---- o que mostrar na barra de salvar
  var estado = form.querySelector(".estado-form");
  if (!estado) {
    var barra = form.querySelector(".barra-salvar");
    if (barra) { estado = document.createElement("span"); estado.className = "estado-form"; estado.hidden = true; barra.appendChild(estado); }
  }
  if (estado) estado.setAttribute("role", "status");
  function mostrar(situacao, texto) {
    if (!estado) return;
    estado.dataset.estado = situacao;
    estado.textContent = texto;
    estado.hidden = false;
  }

  // ---- o conteúdo do formulário, como o servidor guarda: pares [nome, valor]
  var fora = {};
  Array.prototype.forEach.call(form.querySelectorAll('input[type="password"], [data-sem-rascunho]'), function (el) { if (el.name) fora[el.name] = 1; });
  function campos() {
    var pares = [];
    new FormData(form).forEach(function (valor, nome) {
      if (typeof valor !== "string" || NOS_FORA[nome] || fora[nome]) return;
      pares.push([nome, valor]);
    });
    return pares;
  }
  function foto() { return JSON.stringify(campos()); }

  var inicial = foto();       // o que a tela tinha ao abrir (máscaras já aplicadas): sem mudança, não há o que guardar
  var tocou = false;
  setTimeout(function () { if (!tocou) inicial = foto(); }, 800);
  var guardado = null;        // o que o servidor já tem
  var enviando = false, parado = false, saindo = false;
  var espera = null, desde = 0, falhas = 0, horaDoUltimo = "";

  function referencia() { return guardado !== null ? guardado : inicial; }
  function naoGuardado() { return foto() !== referencia(); }

  function agendar() {
    if (parado) return;
    var agora = Date.now();
    if (!desde) desde = agora;
    clearTimeout(espera);
    espera = setTimeout(function () { enviar(false); }, Math.max(0, Math.min(ESPERA, TETO - (agora - desde))));
  }

  function parar(texto) {
    parado = true;
    clearTimeout(espera);
    mostrar("erro", texto);
  }

  function falhou(texto) {
    falhas += 1;
    mostrar("erro", texto);
    clearTimeout(espera);
    espera = setTimeout(function () { enviar(false); }, Math.min(30000, 3000 * Math.pow(2, falhas - 1)));
  }

  function enviar(ultima) {
    clearTimeout(espera); espera = null; desde = 0;
    if (parado) return;
    if (enviando) return;                  // a resposta confere se sobrou algo e agenda de novo
    var agora = foto();
    if (agora === referencia()) return;
    enviando = true;
    var corpo = JSON.stringify({ tipo: tipo, token: token, alvo: alvo, campos: JSON.parse(agora) });
    fetch("/rascunhos/salvar", {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: corpo,
      keepalive: !!ultima && corpo.length < 60000      // ao fechar a aba o navegador termina o envio; o limite dele é 64 KB
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { return { status: r.status, d: d }; });
    }).then(function (res) {
      enviando = false;
      var erro = res.d && res.d.erros ? (res.d.erros.rascunho || res.d.erros.sessao || res.d.erros.csrf || "") : "";
      if (res.status === 200 && res.d.ok) {
        if (res.d.concluido) { parar("Este formulário já foi gravado. Abra-o de novo para continuar."); return; }
        guardado = agora; falhas = 0; horaDoUltimo = res.d.quando;
        if (naoGuardado()) { mostrar("pendente", "Alterações não salvas"); agendar(); }
        else mostrar("salvo", "Rascunho salvo às " + res.d.quando + " · ainda não gravado");
      } else if (res.status === 401 || (res.status === 400 && res.d && res.d.erros && res.d.erros.csrf)) {
        // o login terminou (ou a página venceu: sem a sessão, o servidor responde primeiro que o token não confere)
        parar("Sua sessão terminou ou esta página venceu. " + (horaDoUltimo
          ? "O rascunho está salvo até as " + horaDoUltimo + ": recarregue a página e entre de novo, ele fica em Rascunhos."
          : "Nada foi guardado ainda: copie o que digitou antes de recarregar."));
      } else if (res.status >= 400 && res.status < 500) {
        parar(erro || "Não foi possível guardar o rascunho.");
      } else {
        falhou("O servidor não guardou o rascunho. Tentando de novo…");
      }
    }).catch(function () {
      enviando = false;
      falhou("Sem conexão com o servidor: o rascunho não foi guardado. Tentando de novo…");
    });
  }

  function mudou() {
    tocou = true;
    if (parado || saindo) return;
    if (foto() === referencia()) {
      if (guardado !== null && horaDoUltimo) mostrar("salvo", "Rascunho salvo às " + horaDoUltimo + " · ainda não gravado");
      return;
    }
    mostrar("pendente", "Alterações não salvas");
    agendar();
  }
  form.addEventListener("input", mudou);
  form.addEventListener("change", mudou);

  // ao gravar de verdade o rascunho deixa de importar (o servidor o encerra): não pergunta nada ao sair. Se o envio for desfeito por outro
  // código da página, a guarda volta em 1,5 s.
  form.addEventListener("submit", function () {
    saindo = true; clearTimeout(espera);
    setTimeout(function () { saindo = false; }, 1500);
  });

  // trocou de aba ou está fechando: guarda agora o que ainda estiver esperando
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden" && naoGuardado() && !saindo) enviar(true); });
  window.addEventListener("pagehide", function () { if (naoGuardado() && !saindo) enviar(true); });
  window.addEventListener("online", function () { if (!parado && naoGuardado()) enviar(false); });
  window.addEventListener("beforeunload", function (e) {
    if (!saindo && naoGuardado()) { e.preventDefault(); e.returnValue = ""; }
  });
})();
