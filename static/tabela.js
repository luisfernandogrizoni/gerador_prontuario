// Tabela dinâmica reutilizada pelas listas de internos e de triagens:
// busca dados em JSON, filtra pela busca, ordena ao clicar no cabeçalho
// e se atualiza sozinha de tempos em tempos.
//
// Uso:
//   const tabela = new TabelaDinamica({
//     url: "/api/internos",
//     colunas: [{ chave: "nome", celula: i => i.nome }, ...],  // mesma ordem dos <th>
//     camposBusca: i => [i.nome, i.cpf],                      // onde a busca procura
//     filtro: i => true,                                      // filtro extra (ex.: situação)
//   });

// "José" e "jose" devem achar o mesmo registro: tira acentos e caixa
const normalizar = t => String(t ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

class TabelaDinamica {
  constructor({ url, colunas, camposBusca, filtro = () => true, destacar = null,
                aoCarregar = () => {}, atualizarMs = 30000 }) {
    Object.assign(this, { url, colunas, camposBusca, filtro, destacar, aoCarregar });
    this.itens = [];
    this.ordem = { chave: null, crescente: true };
    this.corpo = document.getElementById("linhas");
    this.busca = document.getElementById("busca");
    this.vazio = document.getElementById("vazio");

    this.busca.addEventListener("input", () => this.desenhar());
    document.querySelectorAll("th[data-chave]").forEach(th => {
      th.addEventListener("click", () => {
        const mesma = this.ordem.chave === th.dataset.chave;
        this.ordem = { chave: th.dataset.chave, crescente: mesma ? !this.ordem.crescente : true };
        document.querySelectorAll("th").forEach(o => o.removeAttribute("aria-sort"));
        th.setAttribute("aria-sort", this.ordem.crescente ? "ascending" : "descending");
        this.desenhar();
      });
    });
    if (atualizarMs) setInterval(() => this.carregar(), atualizarMs);
  }

  async carregar() {
    this.itens = await (await fetch(this.url)).json();
    this.aoCarregar(this.itens);
    this.desenhar();
    document.getElementById("atualizado").textContent =
      "Atualizado às " + new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  }

  visiveis() {
    const termo = normalizar(this.busca.value.trim());
    return this.itens.filter(i => this.filtro(i) &&
      (!termo || normalizar(this.camposBusca(i).join(" ")).includes(termo)));
  }

  ordenar(lista) {
    const { chave, crescente } = this.ordem;
    if (!chave) return lista;                   // sem clique: ordem que veio do servidor
    const numero = document.querySelector(`th[data-chave="${chave}"]`).dataset.tipo === "numero";
    const vazio = v => v === null || v === "" || v === undefined;
    return lista.sort((a, b) => {
      const x = a[chave], y = b[chave];
      if (vazio(x) !== vazio(y)) return vazio(x) ? 1 : -1;   // vazios sempre no fim
      const r = numero ? x - y : String(x).localeCompare(String(y), "pt-BR");
      return crescente ? r : -r;
    });
  }

  desenhar() {
    const lista = this.ordenar(this.visiveis());
    this.corpo.replaceChildren();
    for (const item of lista) {
      const tr = document.createElement("tr");
      tr.id = "linha-" + item.id;
      if (this.destacar && item.id === this.destacar) tr.className = "novo";
      for (const col of this.colunas) {
        const td = document.createElement("td");
        const conteudo = col.celula(item);
        // texto vira textContent (nunca interpreta HTML vindo dos dados); nós são anexados
        if (conteudo instanceof Node) td.appendChild(conteudo);
        else td.textContent = conteudo ?? "";
        if (col.classe) td.className = col.classe;
        tr.appendChild(td);
      }
      this.corpo.appendChild(tr);
    }
    this.vazio.hidden = lista.length > 0;
    this.vazio.textContent = this.itens.length ? "Nada encontrado para essa busca/filtro." : "Nenhum registro ainda.";
  }
}

// pequenos construtores de células
function link(texto, href, classe) {
  const a = document.createElement("a");
  a.href = href; a.textContent = texto;
  if (classe) a.className = classe;
  return a;
}
function selo(texto, classe) {
  const s = document.createElement("span");
  s.className = "selo " + (classe || "");
  s.textContent = texto;
  return s;
}
