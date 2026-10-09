// Comportamento dos formulários de triagem e prontuário.
//  1. máscaras (CPF, RG, CEP, telefone, Cartão SUS) pelo atributo data-mascara
//  2. validação de CPF e RG enquanto digita (o servidor valida de novo ao salvar)
//  3. CEP -> rua, bairro, cidade e UF pela API pública ViaCEP
//  4. busca de "paciente já cadastrado"
//  5. convênio -> categoria / valor travado em R$ 0,00
//  6. botão "usar o mesmo responsável"

const soDigitos = t => (t || "").replace(/\D/g, "");

// ------------------------------------------------------------ 1. máscaras
// Cada máscara recebe o texto digitado e devolve o texto formatado.
const MASCARAS = {
  cpf(v) {
    const d = soDigitos(v).slice(0, 11);
    return d.replace(/^(\d{3})(\d)/, "$1.$2").replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
            .replace(/\.(\d{3})(\d{1,2})$/, ".$1-$2");
  },
  rg(v) {
    // dígitos e um X opcional no final; com 9 caracteres vira 00.000.000-0
    let r = v.toUpperCase().replace(/[^0-9X]/g, "").replace(/X(?=.)/g, "").slice(0, 13);
    if (r.length === 9) r = `${r.slice(0, 2)}.${r.slice(2, 5)}.${r.slice(5, 8)}-${r[8]}`;
    return r;
  },
  cep(v) {
    const d = soDigitos(v).slice(0, 8);
    return d.length > 5 ? `${d.slice(0, 5)}-${d.slice(5)}` : d;
  },
  telefone(v) {
    const d = soDigitos(v).slice(0, 11);
    if (d.length <= 2) return d;
    if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
    if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
    return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  },
  sus(v) {
    const d = soDigitos(v).slice(0, 15);
    return [d.slice(0, 3), d.slice(3, 7), d.slice(7, 11), d.slice(11)].filter(Boolean).join(" ");
  },
};

// ------------------------------------------------------------ 2. validação
function cpfValido(cpf) {
  const d = soDigitos(cpf);
  if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false;
  for (const n of [9, 10]) {
    let soma = 0;
    for (let i = 0; i < n; i++) soma += Number(d[i]) * (n + 1 - i);
    if ((soma * 10) % 11 % 10 !== Number(d[n])) return false;
  }
  return true;
}

const VALIDADORES = {
  cpf: v => !v || cpfValido(v) ? "" : "CPF inválido (dígito verificador não confere).",
  rg: v => !v || /^\d{5,13}X?$/.test(v.replace(/[.\-\s]/g, "")) ? "" : "RG inválido: só números (e X no final).",
  cep: v => !v || soDigitos(v).length === 8 ? "" : "CEP deve ter 8 dígitos.",
};

function mostrarErro(campo, mensagem) {
  campo.setCustomValidity(mensagem);            // impede o envio enquanto houver erro
  const label = campo.closest("label");
  let aviso = label.querySelector("small.erro-js");
  if (!aviso) {
    aviso = document.createElement("small");
    aviso.className = "erro erro-js";
    label.appendChild(aviso);
  }
  aviso.textContent = mensagem;
  label.classList.toggle("com-erro", Boolean(mensagem));
}

document.querySelectorAll("[data-mascara]").forEach(campo => {
  const tipo = campo.dataset.mascara;
  const aplicar = () => { campo.value = MASCARAS[tipo](campo.value); };
  aplicar();                                    // formata o que já veio do banco
  campo.addEventListener("input", aplicar);
  if (VALIDADORES[tipo]) {
    // valida ao sair do campo; depois do primeiro erro, valida a cada tecla
    campo.addEventListener("blur", () => mostrarErro(campo, VALIDADORES[tipo](campo.value)));
    campo.addEventListener("input", () => {
      if (campo.validationMessage) mostrarErro(campo, VALIDADORES[tipo](campo.value));
    });
  }
});

// ------------------------------------------------------------ 3. CEP
const campoCep = document.getElementById("f-cep");
if (campoCep) {
  let ultimoCep = soDigitos(campoCep.value);
  campoCep.addEventListener("input", async () => {
    const cep = soDigitos(campoCep.value);
    if (cep.length !== 8 || cep === ultimoCep) return;
    ultimoCep = cep;
    const rotulo = campoCep.closest("label");
    let ajuda = rotulo.querySelector("small:not(.erro-js)");     // linha de status embaixo do campo
    if (!ajuda) { ajuda = document.createElement("small"); rotulo.appendChild(ajuda); }
    try {
      ajuda.textContent = "Buscando endereço…";
      const r = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
      const dados = await r.json();
      if (dados.erro) throw new Error("não encontrado");
      const preencher = (id, valor) => { if (valor) document.getElementById(id).value = valor; };
      preencher("f-endereco", dados.logradouro);
      preencher("f-bairro", dados.bairro);
      preencher("f-cidade", dados.localidade);
      preencher("f-estado", dados.uf);
      ajuda.textContent = "";                                    // deu certo: nada a explicar
      document.getElementById("f-numero").focus();
    } catch (e) {
      ajuda.textContent = "CEP não encontrado (ou sem internet).";
    }
  });
}

// ------------------------------------------------------------ 4. paciente existente
const busca = document.getElementById("busca-pessoa");
if (busca) {
  const lista = document.getElementById("resultado-pessoas");
  let espera;
  busca.addEventListener("input", () => {
    clearTimeout(espera);
    espera = setTimeout(async () => {          // espera parar de digitar (300 ms)
      const q = busca.value.trim();
      if (q.length < 2) { lista.hidden = true; return; }
      const resposta = await fetch(`/api/pessoas?q=${encodeURIComponent(q)}`);
      if (resposta.status === 401) { location.reload(); return; }   // login expirou
      const pessoas = await resposta.json();
      lista.replaceChildren();
      if (!pessoas.length) {
        const li = document.createElement("li");
        li.textContent = "Ninguém encontrado.";
        lista.appendChild(li);
      }
      for (const p of pessoas) {
        const li = document.createElement("li");
        li.tabIndex = 0;
        li.textContent = p.nome;
        const det = document.createElement("small");
        det.textContent = [p.cpf && `CPF ${p.cpf}`, p.nascimento && `nasc. ${p.nascimento}`, p.cidade, p.ultima]
          .filter(Boolean).join(" · ");
        li.appendChild(det);
        const ir = () => { location.href = `${busca.dataset.destino}?pessoa=${p.id}`; };
        li.addEventListener("click", ir);
        li.addEventListener("keydown", e => { if (e.key === "Enter") ir(); });
        lista.appendChild(li);
      }
      lista.hidden = false;
    }, 300);
  });
}

// ------------------------------------------------------------ 5. convênio
const R = window.REGRAS_CONVENIO;
const convenio = document.getElementById("f-convenio");
if (R && convenio) {
  const valor = document.getElementById("f-contribuicao_valor");
  const condicoes = document.getElementById("f-contribuicao_condicoes");
  const categoria = document.getElementById("categoria");
  function atualizar() {
    const gratuito = R.gratuitos.includes(convenio.value);
    if (gratuito) valor.value = "0.00";
    valor.readOnly = condicoes.readOnly = gratuito;
    let txt = "";
    if (gratuito) txt = "Contribuição R$ 0,00 (convênio)";
    else if (convenio.value === "Particular") {
      const v = Number(valor.value || 0);
      const faixa = R.faixas.find(([limite]) => v > limite);
      txt = "Categoria: " + (faixa ? faixa[1] : R.categoriaZero);
    } else if (convenio.value === R.aDefinir) txt = "Defina o convênio antes de admitir.";
    categoria.textContent = txt || " ";
  }
  convenio.addEventListener("change", atualizar);
  valor.addEventListener("input", atualizar);
  atualizar();
}

// ------------------------------------------------------------ 6. responsável anterior
const usarResp = document.getElementById("usar-responsavel");
if (usarResp) {
  usarResp.addEventListener("click", () => {
    for (const campo of ["resp_nome", "parentesco", "resp_rg", "resp_cpf"]) {
      const el = document.getElementById("f-" + campo);
      el.value = usarResp.dataset[campo] || "";
      el.dispatchEvent(new Event("input"));     // reaplica a máscara
    }
  });
}
