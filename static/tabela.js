// Tabela dinâmica reutilizada pelas listas de internos e de triagens:
// busca dados em JSON, filtra pela busca, ordena ao clicar no cabeçalho
// e se atualiza sozinha de tempos em tempos.
//
// O que o usuário escolheu (filtro, busca, ordem) fica na URL, e a posição da rolagem na sessão
// da aba: ao entrar numa ficha e voltar, a lista reaparece como estava.
//
// Uso:
//   const tabela = new TabelaDinamica({
//     url: "/api/internos",
//     colunas: [{ chave: "nome", celula: i => i.nome }, ...],  // mesma ordem dos <th>
//     camposBusca: i => [i.nome, i.cpf],                      // onde a busca procura
//     filtro: i => true,                                      // filtro extra (ex.: situação)
//     campos: { situacao: seletorDaSituacao },                // controles lembrados na URL
//   });

// "José" e "jose" devem achar o mesmo registro: tira acentos e caixa
const normalizar = t => String(t ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

class TabelaDinamica {
  constructor({ url, colunas, camposBusca, filtro = () => true, destacar = null,
                aoCarregar = () => {}, atualizarMs = 30000, campos = {} }) {
    Object.assign(this, { url, colunas, camposBusca, filtro, destacar, aoCarregar, campos });
    this.itens = [];
    this.ordem = { chave: null, crescente: true };
    this.corpo = document.getElementById("linhas");
    this.busca = document.getElementById("busca");
    this.vazio = document.getElementById("vazio");
    this.jaCarregou = false;

    this.restaurarEstado();                     // antes do 1º desenho: o que estava na URL vale
    this.busca.addEventListener("input", () => this.aoMudar());
    for (const controle of Object.values(campos)) controle.addEventListener("change", () => this.aoMudar());
    document.querySelectorAll("th[data-chave]").forEach(th => {
      th.addEventListener("click", () => {
        const mesma = this.ordem.chave === th.dataset.chave;
        this.ordem = { chave: th.dataset.chave, crescente: mesma ? !this.ordem.crescente : true };
        this.marcarOrdem();
        this.aoMudar();
      });
    });
    if (atualizarMs) setInterval(() => this.carregar(), atualizarMs);

    // a rolagem é restaurada por aqui (o conteúdo chega depois da página, o navegador não acerta)
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";
    addEventListener("pagehide", () => this.guardarRolagem());
  }

  // ---------------------------------------------------------------- estado na URL
  marcarOrdem() {
    document.querySelectorAll("th").forEach(o => o.removeAttribute("aria-sort"));
    const { chave, crescente } = this.ordem;
    document.querySelector(`th[data-chave="${chave}"]`)?.setAttribute("aria-sort", crescente ? "ascending" : "descending");
  }

  restaurarEstado() {
    const p = new URLSearchParams(location.search);
    if (p.has("q")) this.busca.value = p.get("q");
    for (const [nome, controle] of Object.entries(this.campos)) {
      const valor = p.get(nome);
      // só aceita valor que o controle realmente oferece (URL antiga ou mexida na mão não quebra)
      if (valor !== null && (!controle.options || [...controle.options].some(o => o.value === valor))) controle.value = valor;
    }
    const chave = p.get("ordem");
    if (chave && document.querySelector(`th[data-chave="${chave}"]`)) {
      this.ordem = { chave, crescente: p.get("dir") !== "desc" };
      this.marcarOrdem();
    }
  }

  // grava no endereço o que está escolhido (sem criar passo no histórico: o "voltar" continua levando
  // à página anterior de verdade)
  salvarEstado() {
    const p = new URLSearchParams(location.search);
    const termo = this.busca.value.trim();
    termo ? p.set("q", this.busca.value) : p.delete("q");
    for (const [nome, controle] of Object.entries(this.campos)) p.set(nome, controle.value);
    if (this.ordem.chave) { p.set("ordem", this.ordem.chave); p.set("dir", this.ordem.crescente ? "asc" : "desc"); }
    this.trocarEndereco(p);
  }

  // tira parâmetros que só valem uma vez (ex.: ?novo=12) e mantém o resto
  limparParametros(...nomes) {
    const p = new URLSearchParams(location.search);
    nomes.forEach(n => p.delete(n));
    this.trocarEndereco(p);
  }

  trocarEndereco(p) {
    const qs = p.toString();
    history.replaceState(history.state, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
  }

  aoMudar() {
    this.desenhar();
    clearTimeout(this.esperaEstado);            // não grava a cada tecla
    this.esperaEstado = setTimeout(() => this.salvarEstado(), 250);
  }

  // ---------------------------------------------------------------- rolagem
  chaveRolagem() { return "rolagem:" + location.pathname; }

  guardarRolagem() {
    try { sessionStorage.setItem(this.chaveRolagem(), JSON.stringify({ busca: location.search, y: scrollY })); } catch {}
  }

  // só ao VOLTAR (ou avançar) no histórico; ao abrir pelo menu a lista começa no topo
  restaurarRolagem() {
    const nav = performance.getEntriesByType("navigation")[0];
    if (!nav || nav.type !== "back_forward") return;
    try {
      const salvo = JSON.parse(sessionStorage.getItem(this.chaveRolagem()) || "null");
      if (salvo && salvo.busca === location.search) scrollTo(0, salvo.y);
    } catch {}
  }

  async carregar() {
    const resposta = await fetch(this.url);
    if (resposta.status === 401) { location.reload(); return; }   // login expirou: o servidor leva à tela de entrar
    this.itens = await resposta.json();
    this.aoCarregar(this.itens);
    this.desenhar();
    if (!this.jaCarregou) { this.jaCarregou = true; this.restaurarRolagem(); }
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
    // no celular a linha vira um cartão e cada valor ganha o nome da coluna (CSS: td[data-rotulo]::before)
    const rotulos = [...document.querySelectorAll("thead th")].map(th => th.textContent.trim());
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
        const rotulo = rotulos[tr.children.length];
        if (rotulo) td.dataset.rotulo = rotulo;
        tr.appendChild(td);
      }
      this.corpo.appendChild(tr);
    }
    this.vazio.hidden = lista.length > 0;
    this.vazio.textContent = this.itens.length ? "Nada encontrado para essa busca/filtro." : "Nenhum registro ainda.";
    const mostrando = document.getElementById("mostrando");   // opcional: "Mostrando 25 de 34"
    if (mostrando) mostrando.textContent = `Mostrando ${lista.length} de ${this.itens.length} registros`;
  }
}

// ------------------------------------------------------------------ controle de abas
// Faz o papel de um <select> (value, options, "change") para os botões de situação
// "Ativos | Inativos | Todos", para a tabela guardar e restaurar a escolha da mesma forma.
//   <div id="filtro"><button type="button" data-valor="ativo">Ativos</button> ...</div>
class ControleSegmentado {
  constructor(raiz) {
    this.botoes = [...raiz.querySelectorAll("button[data-valor]")];
    this.options = this.botoes.map(b => ({ value: b.dataset.valor }));
    this.ouvintes = [];
    this.atual = this.botoes[0].dataset.valor;      // o primeiro botão é o padrão
    for (const b of this.botoes) {
      b.addEventListener("click", () => {
        if (this.atual === b.dataset.valor) return;
        this.value = b.dataset.valor;
        this.ouvintes.forEach(f => f());
      });
    }
    this.marcar();
  }
  get value() { return this.atual; }
  set value(v) { this.atual = v; this.marcar(); }
  marcar() {
    for (const b of this.botoes) {
      const ligado = b.dataset.valor === this.atual;
      b.classList.toggle("ativo", ligado);
      b.setAttribute("aria-pressed", ligado);
    }
  }
  addEventListener(tipo, funcao) { if (tipo === "change") this.ouvintes.push(funcao); }
}

// ------------------------------------------------------------------ pequenos construtores de células
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
function texto(tag, conteudo, classe) {
  const e = document.createElement(tag);
  e.textContent = conteudo;
  if (classe) e.className = classe;
  return e;
}
// ícone do sprite desenhado no base.html: icone("busca") -> <svg><use href="#i-busca"></svg>
function icone(nome) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "icone");
  const uso = document.createElementNS(NS, "use");
  uso.setAttribute("href", "#i-" + nome);
  svg.appendChild(uso);
  return svg;
}
function botao(rotulo, aoClicar, classe = "botao pequeno secundario", nomeIcone = null) {
  const b = document.createElement("button");
  b.type = "button"; b.className = classe;
  if (nomeIcone) b.appendChild(icone(nomeIcone));
  b.append(rotulo);
  b.addEventListener("click", aoClicar);
  return b;
}
// etiqueta colorida da categoria (a cor vem do servidor: categoria_tipo = caps, taruma, social, ...)
function chipCategoria(categoria, tipo) {
  return texto("span", categoria || "—", "chip " + (tipo || "outro"));
}
// bolinha com as iniciais; a cor é sempre a mesma para a mesma pessoa
function avatar(nome) {
  const particulas = ["de", "da", "do", "das", "dos", "e"];
  const p = String(nome || "?").trim().split(/\s+/).filter(w => !particulas.includes(w.toLowerCase()));
  const iniciais = ((p[0] || "?")[0] + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase();
  let soma = 0;
  for (const c of normalizar(nome)) soma += c.charCodeAt(0);
  return texto("span", iniciais, "avatar av" + (soma % 8));
}

// ------------------------------------------------------------------ células usadas pelas listas de pessoas
// avatar + nome (link para a ficha) e, embaixo, "CPF · 34 anos"
function celulaPessoa(i) {
  const dados = [i.cpf || "sem CPF", i.idade != null ? `${i.idade} anos` : ""].filter(Boolean).join(" · ");
  const nome = document.createElement("div");
  nome.append(link(i.nome, `/internacoes/${i.id}`), texto("small", dados));
  const caixa = document.createElement("div");
  caixa.className = "pessoa";
  caixa.append(avatar(i.nome), nome);
  return caixa;
}
// nome do responsável (parentesco) e, embaixo, o contato
function celulaResponsavel(i) {
  const caixa = document.createElement("div");
  caixa.append(i.parentesco ? `${i.responsavel} (${i.parentesco})` : (i.responsavel || "—"));
  if (i.contato) caixa.append(texto("span", i.contato, "sub"));
  return caixa;
}
// data formatada; sem data, mostra `vazio` em cinza (ou nada)
function dataOuMudo(fmt, vazio = "") {
  return fmt ? fmt : (vazio ? texto("span", vazio, "mudo") : "");
}
