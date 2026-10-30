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
    const sem = document.createElement("span");
    sem.className = "icone-vazio"; sem.appendChild(icone(this.itens.length ? "busca" : "prancheta"));
    this.vazio.replaceChildren(sem, texto("span", this.itens.length ? "Nada encontrado para essa busca/filtro." : "Nenhum registro ainda."));
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

// ------------------------------------------------------------------ lista com busca, filtros, ordem e páginas no servidor
// Como a TabelaDinamica, mas o navegador NÃO baixa a lista inteira: pede ao servidor só a página que mostra (lista de internos: busca_de_internos.py), e é o
// servidor que busca, filtra e ordena. A resposta é { itens, total, pagina, paginas, por, de, ate, contagens }. O que a pessoa escolhe (busca, filtros,
// ordem, página, tamanho) fica na URL, como na TabelaDinamica.
//   precisa de: <nav id="paginador">, <select id="por-pagina">, <button id="limpar-filtros"> e, em `campos`, os controles de filtro. O de nome `aba`
//   (padrão "situacao") é o segmentado "Ativos | Inativos | Todos": o primeiro botão é o padrão e o valor vazio é "todos".
class TabelaPaginada extends TabelaDinamica {
  constructor({ aba = "situacao", ...opcoes }) {
    super({ ...opcoes, filtro: () => true });
    this.aba = aba;
    this.sequencia = 0;
    this.dados = null;
    this.paginador = document.getElementById("paginador");
    this.porPagina = document.getElementById("por-pagina");
    this.limpar = document.getElementById("limpar-filtros");
    this.moldura = this.corpo.closest(".moldura");
    this.porPagina.addEventListener("change", () => this.aoMudar());
    this.limpar.addEventListener("click", () => this.limparFiltros());
  }

  // ---------------------------------------------------------------- estado na URL
  restaurarEstado() {
    super.restaurarEstado();
    const p = new URLSearchParams(location.search);
    this.pagina = Math.max(1, parseInt(p.get("pagina"), 10) || 1);
    const por = document.getElementById("por-pagina");
    if (p.has("por") && [...por.options].some(o => o.value === p.get("por"))) por.value = p.get("por");
  }

  salvarEstado() {
    super.salvarEstado();
    const p = new URLSearchParams(location.search);
    for (const [nome, controle] of Object.entries(this.campos)) if (!controle.value && nome !== this.aba) p.delete(nome);   // só o que está escolhido
    this.pagina > 1 ? p.set("pagina", this.pagina) : p.delete("pagina");
    const padrao = [...this.porPagina.options].find(o => o.defaultSelected)?.value;
    this.porPagina.value !== padrao ? p.set("por", this.porPagina.value) : p.delete("por");
    this.trocarEndereco(p);
  }

  // mudou a busca, um filtro, a ordem ou o tamanho: volta para a primeira página e pergunta de novo ao servidor (sem pedir a cada tecla)
  aoMudar() {
    this.pagina = 1;
    clearTimeout(this.esperaBusca);
    this.esperaBusca = setTimeout(() => this.carregar(), 250);
    clearTimeout(this.esperaEstado);
    this.esperaEstado = setTimeout(() => this.salvarEstado(), 250);
  }

  irPara(pagina) {
    this.pagina = pagina;
    this.carregar();
    this.salvarEstado();
    this.moldura.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  filtrosAtivos() {
    return this.busca.value.trim() !== "" || Object.entries(this.campos).some(([nome, c]) => nome !== this.aba && c.value);
  }

  // volta ao começo: sem busca, sem filtros, na aba padrão
  limparFiltros({ recarregar = true } = {}) {
    this.busca.value = "";
    for (const [nome, controle] of Object.entries(this.campos)) controle.value = nome === this.aba ? controle.options[0].value : "";
    this.pagina = 1;
    if (recarregar) this.aoMudar();
  }

  // ---------------------------------------------------------------- dados
  // `foco`: o número de um registro que precisa aparecer; o servidor devolve a página em que ele está
  async carregar({ foco = null } = {}) {
    if (this.jaCarregou && document.hidden) return;          // aba escondida: a atualização automática espera
    const sequencia = ++this.sequencia;
    this.pedido?.abort();
    this.pedido = new AbortController();
    const p = new URLSearchParams();
    if (this.busca.value.trim()) p.set("q", this.busca.value.trim());
    for (const [nome, controle] of Object.entries(this.campos)) if (controle.value) p.set(nome, controle.value);
    if (this.ordem.chave) { p.set("ordem", this.ordem.chave); p.set("dir", this.ordem.crescente ? "asc" : "desc"); }
    p.set("por", this.porPagina.value);
    p.set("pagina", this.pagina);
    if (foco) p.set("foco", foco);
    clearTimeout(this.demora);
    this.demora = setTimeout(() => this.moldura.setAttribute("aria-busy", "true"), 300);       // só escurece se a resposta demorar
    let resposta;
    try {
      resposta = await fetch(this.url + "?" + p, { signal: this.pedido.signal });
      if (resposta.status === 401) { location.reload(); return; }       // login expirou: o servidor leva à tela de entrar
      const dados = await resposta.json();
      if (sequencia !== this.sequencia) return;                         // já saiu uma pergunta mais nova: esta resposta ficou velha
      this.dados = dados;
      this.itens = dados.itens;
      this.pagina = dados.pagina;
    } catch (erro) {
      if (erro.name === "AbortError") return;
      document.getElementById("atualizado").textContent = "Sem conexão com o servidor: tentando de novo…";
      return;
    } finally {
      if (sequencia === this.sequencia) { clearTimeout(this.demora); this.moldura.removeAttribute("aria-busy"); }
    }
    this.aoCarregar(this.dados);
    this.desenhar();
    this.desenharPaginador();
    if (!this.jaCarregou) { this.jaCarregou = true; this.restaurarRolagem(); }
    document.getElementById("atualizado").textContent =
      "Atualizado às " + new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  }

  // o servidor já filtrou e ordenou
  visiveis() { return this.itens; }
  ordenar(lista) { return lista; }

  desenhar() {
    super.desenhar();                                   // as linhas
    const d = this.dados;
    if (!d) return;
    const n = x => x.toLocaleString("pt-BR");
    document.getElementById("mostrando").textContent =
      d.total ? `Mostrando ${n(d.de)}–${n(d.ate)} de ${n(d.total)} registro${d.total === 1 ? "" : "s"}` : "Nenhum registro";
    this.vazio.hidden = d.total > 0;
    if (!d.total) {
      const buscando = this.filtrosAtivos();
      const mensagem = buscando ? "Nada encontrado para essa busca/filtro." : d.contagens.todos ? "Nenhum registro nesta situação." : "Nenhum registro ainda.";
      const sem = document.createElement("span");
      sem.className = "icone-vazio"; sem.appendChild(icone(buscando ? "busca" : "prancheta"));
      this.vazio.replaceChildren(sem, texto("span", mensagem));
    }
    this.limpar.hidden = !this.filtrosAtivos();
  }

  // « Anterior  1 … 4 5 [6] 7 8 … 25  Próxima »
  desenharPaginador() {
    const { pagina, paginas } = this.dados;
    this.paginador.replaceChildren();
    this.paginador.hidden = paginas <= 1;
    if (paginas <= 1) return;
    const botaoDaPagina = (rotulo, destino, { atual = false, desligado = false, nome = "" } = {}) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = rotulo;
      if (nome) b.setAttribute("aria-label", nome);
      if (atual) b.setAttribute("aria-current", "page");
      b.disabled = desligado;
      b.addEventListener("click", () => { if (!atual) this.irPara(destino); });
      return b;
    };
    const mostrar = new Set([1, paginas]);
    for (let n = pagina - 2; n <= pagina + 2; n++) if (n >= 1 && n <= paginas) mostrar.add(n);
    const numeros = [...mostrar].sort((a, b) => a - b);
    this.paginador.append(botaoDaPagina("‹ Anterior", pagina - 1, { desligado: pagina === 1 }));
    let anterior = 0;
    for (const n of numeros) {
      if (n - anterior === 2) this.paginador.append(botaoDaPagina(String(n - 1), n - 1, { nome: `Página ${n - 1}` }));    // uma página só faltando: mostra o número
      else if (n - anterior > 2) this.paginador.append(texto("span", "…", "reticencias"));
      this.paginador.append(botaoDaPagina(String(n), n, { atual: n === pagina, nome: `Página ${n}` }));
      anterior = n;
    }
    this.paginador.append(botaoDaPagina("Próxima ›", pagina + 1, { desligado: pagina === paginas }));
  }
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
