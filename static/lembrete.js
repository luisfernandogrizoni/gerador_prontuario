// Lembrete da troca semanal do pen-drive do backup (página inicial): abre uma vez por dia em cada navegador, até a troca ser feita.
// Quem fecha ("Entendi" ou Esc) não vê de novo no mesmo dia; no dia seguinte volta, se a troca ainda não aconteceu.
(function () {
  var janela = document.getElementById("lembrete-troca");
  if (!janela || !janela.showModal) return;
  var chave = "lembrete-troca:" + janela.dataset.chave;
  function visto() { try { return sessionStorage.getItem(chave) === "1"; } catch (e) { return false; } }
  function marcar() { try { sessionStorage.setItem(chave, "1"); } catch (e) { /* sem armazenamento: abre de novo na próxima visita */ } }
  if (visto()) return;
  document.getElementById("lembrete-ok").addEventListener("click", function () { marcar(); janela.close(); });
  janela.addEventListener("cancel", marcar);
  janela.showModal();
})();
