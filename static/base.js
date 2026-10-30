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

  // ---- 3) como nomes e endereços são escritos: data-forma="nome|local|frase|uf|email" no <input>. Ao sair do campo, FULANO FICTICIO DE TAL vira
  // Fulano Ficticio de Tal, para a pessoa ver como vai ficar. É o mesmo algoritmo de validacao.py (nome_proprio, frase): o servidor refaz ao
  // gravar e é quem decide. Acento o sistema não adivinha: JOSE pode ser José ou Jose, e o nome tem de ficar como está no documento.
  var PARTICULAS = ["de", "da", "do", "das", "dos", "e"];
  var ROMANO = /^X{0,3}(?:IX|IV|V?I{0,3})$/;
  var maiuscula = function (t) { return t === t.toUpperCase() && t !== t.toLowerCase(); };
  var minuscula = function (t) { return t === t.toLowerCase() && t !== t.toUpperCase(); };
  var umaLinha = function (t) { return String(t || "").normalize("NFC").split(/\s+/).filter(Boolean).join(" "); };
  var comInicialMaiuscula = function (pedaco) {
    var t = pedaco.toLowerCase(), i = t.search(/\p{L}/u);
    return i < 0 ? t : t.slice(0, i) + t[i].toUpperCase() + t.slice(i + 1);
  };
  var nomeProprio = function (texto, siglas) {
    texto = umaLinha(texto);
    var tudo = maiuscula(texto) || minuscula(texto);
    return texto.split(" ").filter(Boolean).map(function (palavra, i) {
      var alta = maiuscula(palavra), baixa = minuscula(palavra), solta = palavra.replace(/^[,;:]+|[,;:]+$/g, "");
      if (!(siglas ? (tudo || baixa) : (alta || baixa)) || /\p{Nd}/u.test(palavra)) return palavra;
      if (i && PARTICULAS.indexOf(solta.toLowerCase()) >= 0) return palavra.toLowerCase();
      if (alta && solta.length >= 2 && ROMANO.test(solta)) return palavra;
      return palavra.split(/([-'’\/.])/).map(function (p, j) { return j % 2 ? p : comInicialMaiuscula(p); }).join("");
    }).join(" ");
  };
  var frase = function (texto) {
    texto = umaLinha(texto);
    return maiuscula(texto) || minuscula(texto) ? comInicialMaiuscula(texto) : texto;
  };
  window.escreverBem = function (forma, texto) {
    switch (forma) {
      case "nome": return nomeProprio(texto, false);
      case "local": return nomeProprio(texto, true);
      case "frase": return frase(texto);
      case "uf": return umaLinha(texto).toUpperCase().slice(0, 2);
      case "email": return umaLinha(texto).toLowerCase();
      default: return String(texto || "").trim();
    }
  };
  document.addEventListener("focusout", function (e) {
    var c = e.target;
    if (!c || !c.getAttribute || !c.getAttribute("data-forma") || c.readOnly || typeof c.value !== "string") return;
    var novo = window.escreverBem(c.getAttribute("data-forma"), c.value);
    if (novo === c.value) return;
    c.value = novo;
    c.dispatchEvent(new Event("input", { bubbles: true }));         // o salvamento automático (rascunho.js) e as máscaras enxergam a mudança
  });
})();
