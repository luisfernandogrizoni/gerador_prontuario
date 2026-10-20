// Paginação do documento na tela e na impressão (templates/documento.html).
//
// O servidor entrega uma "folha" (.papel) por quebra de página do documento, e uma folha com mais texto do que cabe numa página A4 ficaria como uma
// folha só, comprida: o cabeçalho (timbre) só no começo e o rodapé só no fim, logo depois do texto. Aqui cada folha comprida é dividida em várias
// folhas A4 de verdade, cada uma com o timbre no alto e o rodapé embaixo da própria página, e a impressão do navegador usa essas mesmas folhas.
//
// Como: mede quanto cabe no corpo de uma folha vazia e vai pondo os blocos (parágrafos, tabelas, linhas de escrever...) um depois do outro; o que
// não cabe vai para uma folha nova, igual à anterior (o timbre vem junto). Um bloco "unido ao próximo" (título, pergunta) não fica sozinho no pé da
// página; uma tabela comprida continua na folha seguinte com a linha de títulos repetida; as linhas de escrever (pauta) também se dividem.
// Só na tela larga (a folha é A4 de verdade); no celular a folha rola como antes. O texto não muda: só muda em qual folha cada bloco fica.
(function () {
  "use strict";

  var LARGURA_MINIMA = 900;          // px: abaixo disso a folha encolhe e a medida de uma folha A4 não vale
  var FOLGA = 3;                     // px que sobram no pé da página, para não estourar por arredondamento
  var mesa = document.querySelector(".mesa");
  if (!mesa || !window.matchMedia("(min-width: " + LARGURA_MINIMA + "px)").matches) return;

  function cabe(corpo) { return corpo.scrollHeight <= corpo.clientHeight + 1; }
  function ehTabela(no) { return no.tagName === "TABLE" && no.classList.contains("doc-tabela"); }
  function ehPauta(no) { return no.classList && no.classList.contains("pauta"); }
  function unido(no) { return no.classList && no.classList.contains("unido"); }

  function corpoDaFolha(papel) { return papel.querySelector("table.folha > tbody > tr > td.doc-corpo"); }

  // quanto cabe, em px, no corpo de uma folha vazia (a altura da folha menos o timbre do alto e do rodapé)
  function capacidade(td) {
    var estilo = getComputedStyle(td);
    return Math.floor(td.clientHeight - parseFloat(estilo.paddingTop) - parseFloat(estilo.paddingBottom)) - FOLGA;
  }

  function Pagina(papel, td, alto) {
    var corpo = document.createElement("div");
    corpo.className = "pagina-corpo";
    corpo.style.cssText = "height:" + alto + "px; overflow:hidden;";
    td.appendChild(corpo);
    this.papel = papel;
    this.corpo = corpo;
  }

  function paginarFolha(papel) {
    var td = corpoDaFolha(papel);
    if (!td) return;
    var nos = Array.prototype.slice.call(td.children);
    if (!nos.length) return;
    nos.forEach(function (no) { td.removeChild(no); });
    var alto = capacidade(td);
    if (alto < 100) { nos.forEach(function (no) { td.appendChild(no); }); return; }        // folha sem espaço medido: deixa como veio

    var paginas = [new Pagina(papel, td, alto)];
    var atual = paginas[0];

    function novaPagina() {
      var ultimo = paginas[paginas.length - 1].papel;
      var copia = ultimo.cloneNode(true);
      var tdCopia = corpoDaFolha(copia);
      tdCopia.textContent = "";
      ultimo.parentNode.insertBefore(copia, ultimo.nextSibling);
      var pagina = new Pagina(copia, tdCopia, alto);
      paginas.push(pagina);
      return pagina;
    }

    // o primeiro bloco de uma folha de continuação começa no alto da página: sem o espaço de antes
    function noAlto(no) { no.style.marginTop = "0"; }

    // `no` não coube na página atual: ele (e os blocos "unidos ao próximo" que vinham antes dele) vão para uma página nova
    function quebrar(no) {
      var levar = [no];
      atual.corpo.removeChild(no);
      while (atual.corpo.children.length > 1 && unido(atual.corpo.lastElementChild)) levar.unshift(atual.corpo.removeChild(atual.corpo.lastElementChild));
      if (!atual.corpo.children.length) { atual.corpo.appendChild(no); return false; }      // já era o primeiro da página e não cabe: fica assim mesmo
      atual = novaPagina();
      levar.forEach(function (x, i) { atual.corpo.appendChild(x); if (i === 0) noAlto(x); });
      return true;
    }

    // a tabela não coube: fica nesta página com as linhas que couberem e o resto continua na página seguinte, com os títulos repetidos
    function dividirTabela(tabela) {
      var corpoDaTabela = tabela.tBodies[0], resto = [];
      while (!cabe(atual.corpo) && corpoDaTabela.rows.length > 1) resto.unshift(corpoDaTabela.removeChild(corpoDaTabela.lastElementChild));
      if (!cabe(atual.corpo)) {                  // nem os títulos e uma linha cabem aqui: a tabela inteira vai para a página seguinte
        resto.forEach(function (linha) { corpoDaTabela.appendChild(linha); });
        if (quebrar(tabela) && !cabe(atual.corpo)) dividirTabela(tabela);
        return;
      }
      if (!resto.length) return;
      atual = novaPagina();
      var nova = tabela.cloneNode(false);
      Array.prototype.forEach.call(tabela.children, function (filho) { if (filho.tagName === "COLGROUP" || filho.tagName === "THEAD") nova.appendChild(filho.cloneNode(true)); });
      var novoCorpo = document.createElement("tbody");
      resto.forEach(function (linha) { novoCorpo.appendChild(linha); });
      nova.appendChild(novoCorpo);
      nova.style.marginTop = "0";
      atual.corpo.appendChild(nova);
      if (!cabe(atual.corpo)) dividirTabela(nova);
    }

    // as linhas de escrever se dividem como as de uma tabela
    function dividirPauta(pauta) {
      var resto = [];
      while (!cabe(atual.corpo) && pauta.children.length > 1) resto.unshift(pauta.removeChild(pauta.lastElementChild));
      if (!cabe(atual.corpo)) {
        resto.forEach(function (linha) { pauta.appendChild(linha); });
        if (quebrar(pauta) && !cabe(atual.corpo)) dividirPauta(pauta);
        return;
      }
      if (!resto.length) return;
      atual = novaPagina();
      var nova = pauta.cloneNode(false);
      resto.forEach(function (linha) { nova.appendChild(linha); });
      nova.style.marginTop = "0";
      atual.corpo.appendChild(nova);
      if (!cabe(atual.corpo)) dividirPauta(nova);
    }

    nos.forEach(function (no) {
      atual.corpo.appendChild(no);
      if (cabe(atual.corpo)) return;
      if (ehTabela(no) && no.tBodies.length) dividirTabela(no);
      else if (ehPauta(no)) dividirPauta(no);
      else quebrar(no);                      // um bloco que não cabe nem numa página vazia fica como está (a folha cresce)
    });

    paginas.forEach(function (pagina) { pagina.corpo.style.height = ""; pagina.corpo.style.overflow = ""; });
  }

  function paginar() {
    Array.prototype.slice.call(mesa.querySelectorAll(":scope > .papel")).forEach(paginarFolha);
    mesa.setAttribute("data-paginado", "1");
  }

  // espera o timbre (as duas imagens) carregar: a altura dele entra na conta
  function imagensProntas() {
    var imagens = Array.prototype.slice.call(mesa.querySelectorAll("img"));
    return Promise.all(imagens.map(function (img) {
      return img.complete ? Promise.resolve() : new Promise(function (resolve) { img.addEventListener("load", resolve); img.addEventListener("error", resolve); });
    }));
  }

  function iniciar() { imagensProntas().then(function () { return document.fonts && document.fonts.ready; }).then(paginar); }
  if (document.readyState === "complete") iniciar(); else window.addEventListener("load", iniciar);
})();
