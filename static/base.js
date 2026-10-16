// Comportamentos do sistema inteiro que dependem da política de conteúdo do navegador (CSP, csrf.py). Carregado no <head> de todas as páginas.
//  1) token CSRF: todo fetch do próprio sistema que muda coisas leva o cabeçalho X-CSRF-Token, e todo formulário POST leva o campo csrf_token
//     (os formulários já vêm com ele do servidor; isto cobre os que um script cria e é a rede de segurança);
//  2) o que antes eram atributos nas tags (onclick, onsubmit, onchange), que a política não deixa rodar, agora são atributos de dados:
//     data-confirmar="texto"   no <form> ou no <button>: pergunta antes de enviar;
//     data-imprimir            no botão: abre a janela de impressão;
//     data-trocar-emissor      no <select>: recarrega o documento com quem assina (função trocarEmissor da própria página).
(function () {
  var meta = document.querySelector('meta[name="csrf-token"]');
  var token = meta ? meta.content : "";

  // ---- 1) CSRF nas chamadas do JavaScript
  var original = window.fetch;
  if (original && token) {
    window.fetch = function (entrada, opcoes) {
      opcoes = opcoes || {};
      var metodo = String(opcoes.method || (entrada && entrada.method) || "GET").toUpperCase();
      var url = typeof entrada === "string" ? entrada : ((entrada && entrada.url) || "");
      var proprio = !/^[a-z][a-z0-9+.\-]*:/i.test(url) || url.indexOf(location.origin) === 0;       // endereço sem "https:" é do próprio sistema
      if (proprio && metodo !== "GET" && metodo !== "HEAD" && metodo !== "OPTIONS") {
        var cabecalhos = new Headers(opcoes.headers || (entrada && entrada.headers) || {});
        if (!cabecalhos.has("X-CSRF-Token")) cabecalhos.set("X-CSRF-Token", token);
        opcoes = Object.assign({}, opcoes, { headers: cabecalhos });
      }
      return original.call(this, entrada, opcoes);
    };
  }

  // ---- 1) CSRF nos formulários e 2) confirmação antes de enviar
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (!f || !f.getAttribute) return;
    var pergunta = f.getAttribute("data-confirmar");
    if (pergunta && !window.confirm(pergunta)) { e.preventDefault(); return; }
    if (token && String(f.method).toLowerCase() === "post" && !f.querySelector('input[name="csrf_token"]')) {
      var campo = document.createElement("input");
      campo.type = "hidden"; campo.name = "csrf_token"; campo.value = token;
      f.appendChild(campo);
    }
  }, true);

  // ---- 2) botões
  document.addEventListener("click", function (e) {
    var alvo = e.target && e.target.closest ? e.target.closest("[data-imprimir], button[data-confirmar]") : null;
    if (!alvo) return;
    if (alvo.hasAttribute("data-imprimir")) { e.preventDefault(); window.print(); return; }
    if (!window.confirm(alvo.getAttribute("data-confirmar"))) e.preventDefault();
  }, true);

  // ---- 2) quem assina o documento
  document.addEventListener("change", function (e) {
    var s = e.target;
    if (s && s.hasAttribute && s.hasAttribute("data-trocar-emissor") && typeof window.trocarEmissor === "function") window.trocarEmissor(s.form);
  });
})();
