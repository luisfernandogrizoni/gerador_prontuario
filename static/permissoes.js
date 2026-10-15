// Cadastros > Permissões: ao escolher o nível mínimo de uma permissão, a linha mostra na hora até onde ela vale (do nível
// escolhido para cima). Sem JavaScript tudo continua funcionando: o servidor refaz a tela ao salvar.
(function () {
  document.querySelectorAll(".matriz tr[data-linha]").forEach(function (linha) {
    var radios = Array.prototype.slice.call(linha.querySelectorAll("input[type=radio]"));
    if (!radios.length) return;
    function pintar() {
      var escolhido = radios.findIndex(function (r) { return r.checked; });
      if (escolhido < 0) return;
      radios.forEach(function (r, n) {
        var sinal = r.nextElementSibling;
        var tem = n <= escolhido;
        sinal.className = "sinal " + (tem ? "sim" : "nao");
        sinal.textContent = tem ? "✓" : "–";
      });
    }
    radios.forEach(function (r) { r.addEventListener("change", pintar); });
  });
})();
