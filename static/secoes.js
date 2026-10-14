// Formulários longos (padrões de interface): índice das seções ao lado (no celular vira uma barra de seções presa no topo),
// seção com erro marcada, "alterações não salvas" na barra de salvar. O formulário avisa com `data-indice`; cada seção é um
// <fieldset> cuja <legend> tem o ícone (macro legenda, em templates/_cartao.html). Sem JavaScript o formulário continua inteiro.
(function () {
  var raiz = document.documentElement;
  var topo = document.querySelector(".topo");

  // altura do cabeçalho quando ele fica preso no topo (nos celulares ele rola com a página): o índice e as âncoras descontam isso
  function medirTopo() {
    var preso = topo && getComputedStyle(topo).position === "sticky";
    raiz.style.setProperty("--topo-h", (preso ? topo.offsetHeight : 0) + "px");
  }
  medirTopo();
  window.addEventListener("resize", medirTopo);

  var form = document.querySelector("form[data-indice]");
  if (!form) return;
  var reduzido = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var secoes = Array.prototype.filter.call(form.querySelectorAll("fieldset"), function (f) {
    return f.querySelector(":scope > legend .icone-secao") && !f.classList.contains("busca-paciente");
  });
  var links = [];

  if (secoes.length > 1) {
    var nav = document.createElement("nav");
    nav.className = "indice";
    nav.setAttribute("aria-label", "Seções do formulário");
    secoes.forEach(function (f, n) {
      f.id = f.id || "secao-" + (n + 1);
      var legenda = f.querySelector(":scope > legend");
      var a = document.createElement("a");
      a.href = "#" + f.id;
      a.appendChild(legenda.querySelector(".icone-secao").cloneNode(true));
      a.appendChild(document.createTextNode(legenda.textContent.trim()));
      var estilo = getComputedStyle(f);          // a cor do ícone e do destaque é a da própria seção
      ["--tom", "--tom-suave", "--tom-borda"].forEach(function (v) { a.style.setProperty(v, estilo.getPropertyValue(v)); });
      a._secao = f;
      if (f.querySelector(".com-erro, small.erro")) a.classList.add("com-erro");
      a.addEventListener("click", function (e) {
        e.preventDefault();
        var d = f.closest("details");
        if (d) d.open = true;                    // seção opcional recolhida: abre ao ser escolhida
        f.scrollIntoView({ behavior: reduzido ? "auto" : "smooth", block: "start" });
      });
      nav.appendChild(a);
      links.push(a);
    });
    form.parentNode.insertBefore(nav, form);

    var pendente = false;
    function marcar() {
      pendente = false;
      var limite = (parseInt(raiz.style.getPropertyValue("--topo-h"), 10) || 0) + 150;
      var visiveis = secoes.filter(function (f) { return f.offsetParent !== null; });
      var atual = visiveis[0];
      visiveis.forEach(function (f) { if (f.getBoundingClientRect().top <= limite) atual = f; });
      if (window.innerHeight + window.scrollY >= raiz.scrollHeight - 4) atual = visiveis[visiveis.length - 1];
      links.forEach(function (l) {
        var ativo = l._secao === atual;
        l.classList.toggle("ativo", ativo);
        if (ativo && nav.scrollWidth > nav.clientWidth) l.scrollIntoView({ inline: "center", block: "nearest" });   // no celular, a barra acompanha
      });
    }
    window.addEventListener("scroll", function () { if (!pendente) { pendente = true; requestAnimationFrame(marcar); } }, { passive: true });
    window.addEventListener("resize", marcar);
    marcar();
  }

  // voltou com erro: abre o que estiver recolhido e leva ao primeiro campo marcado
  var erro = form.querySelector(".com-erro");
  if (erro) {
    var d = erro.closest("details");
    if (d) d.open = true;
    setTimeout(function () { erro.scrollIntoView({ block: "center" }); }, 80);
  }

  // "alterações não salvas": compara com o que o formulário tinha logo depois de abrir (as máscaras e a busca de CEP
  // mexem nos campos ao abrir, e isso não conta)
  var estado = form.querySelector(".estado-form");
  if (estado) {
    var foto = function () { return Array.from(new FormData(form)).map(function (par) { return par[0] + "=" + par[1]; }).join("&"); };
    var inicial = null;
    setTimeout(function () { inicial = foto(); }, 700);
    var conferir = function () { estado.hidden = inicial === null || foto() === inicial; };
    form.addEventListener("input", conferir);
    form.addEventListener("change", conferir);
  }
})();
