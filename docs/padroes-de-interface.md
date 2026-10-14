# Padrões de interface

Como o sistema deve parecer e se comportar. Vale para toda tela nova e para o que for mexido em tela antiga. Foi definido
com o usuário em 2026-10-14. Ainda faltam, na fase 4, as telas Relatórios, Cadastros (listas), entrada, senha, documento e janelas.

## Ideia central

Limpo, pastel e dinâmico, como o **Início** e a lista de **Internos**: cartões brancos sobre fundo cinza-claro, cor suave
com texto escuro do mesmo tom, números e ícones que se leem à primeira vista. Nada de colorido sólido em excesso: **a cor
forte é exceção e quer dizer algo**.

## Cores: por papel, nunca por tela

Todas as cores vêm de variáveis em `templates/base.html` (`:root`). Não se escreve código de cor solto numa tela: usa-se o
papel. Cada papel tem o tom **forte** (barras, ícones, borda de destaque), o **suave** (fundo pastel) e o texto sobre ele.

| Papel | Quando | Variáveis |
|---|---|---|
| Primária | A marca e **a** ação principal da tela | `--primaria`, `--primaria-forte`, `--primaria-suave`, `--primaria-borda` |
| Perigo | Excluir, apagar, situação grave | `--perigo`, `--perigo-suave`, `--perigo-borda` (vinho) |
| Sucesso | Concluído, ativo, tudo certo | `--sucesso`, `--sucesso-suave`, `--sucesso-borda` |
| Atenção | Pendência, prazo chegando | `--atencao`, `--atencao-suave`, `--atencao-borda` |
| Informação | Em andamento, neutro com destaque | `--info`, `--info-suave`, `--info-borda` |
| Neutro | Tudo o mais; botão secundário | `--neutro`, `--neutro-suave`, `--neutro-borda` |

- O **vermelho da casa** é a marca e o botão principal. Não é a cor de "erro" de uma categoria: Caps AD, por exemplo, tem
  o próprio pastel (`.chip.caps`).
- **Nunca só a cor**: todo estado tem texto ou ícone junto (o selo "Ativo", não só uma bolinha verde).
- **Contraste**: texto de pelo menos 4,5:1 sobre o fundo (o pastel leva texto escuro do mesmo tom); bordas e ícones que
  carregam informação, 3:1.
- Foco visível em tudo que se clica: anel azul (`--foco`), nunca vermelho (o vermelho já quer dizer erro).
- As cores das categorias de convênio (`.chip.*`, `.tipo-*`) são as mesmas em todas as telas e não mudam.

## Botões

Um botão **cheio** (primário) por tela, para a ação principal. Os outros são pastel.

| Classe | Uso |
|---|---|
| `.botao` | Primário: Salvar, Editar (se for a ação da tela), Lançar. **Um por tela** |
| `.botao.suave` | Pastel da cor primária: o "principal" de um grupo que se repete (Visualizar dos documentos) |
| `.botao.secundario` | Pastel neutro: o padrão dos demais (Cancelar, Imprimir, Editar numa lista) |
| `.botao.fantasma` | Sem fundo: ações terciárias |
| `.botao.perigo` | Ação destrutiva, em vinho suave (Excluir registro) |
| `.botao.perigo.solido` | Só **dentro da confirmação** (o botão que de fato exclui) |
| `.botao.pequeno` | Em listas e linhas |

## Espaço, cantos, texto

- Espaços: `--e1` a `--e6` (4, 8, 12, 16, 24, 32 px). Não inventar valores.
- Cantos: `--r-sm` 8, `--r-md` 12, `--r-lg` 16 (cartões e seções).
- Sombras: `--sombra` (cartão) e `--sombra-alta` (janela, aviso).
- Texto: título de página `--t-titulo`, de seção `--t-secao`, corpo `--t-corpo`, rótulo `--t-rotulo`. Mínimo de 14 px.
- Alvos de clique com pelo menos 24 px (no celular, 42 px; `.botao` já cuida disso).

## Páginas

- **Duas larguras**: leitura e formulário curto em 960 px (`main`); listas, painéis, ficha e formulário com índice em 1320 px (`main.largo`), para o título e o Voltar ficarem no mesmo lugar em todas.
- Ordem do topo: **Voltar** (`linha_voltar`), título, subtítulo, ações à direita. Toda tela, menos Início e Entrada, tem Voltar.
- `+ Triagem` e `+ Prontuário` só no cabeçalho.
- **Sem textos de instrução ou ajuda** nas telas: só estado e erros.

## Avisos

- Confirmação de uma ação (flash): cartão discreto no canto inferior direito, com botão de fechar, que some sozinho
  (`.mensagens`). No canto de baixo para nunca cobrir as ações do topo.
  Já vem pronto: basta `flash("...")`.
- Pendências e alertas: no quadro de avisos do Início, nunca como faixa no meio da página.
- Erro de formulário: ao lado do campo (`small.erro`) e a caixa `.caixa-erros` no topo.

## Formulários

- **Seção = cartão com ícone**: `<fieldset class="tom-azul">{{ legenda('Acolhido', 'usuario') }} ...` (`templates/_cartao.html`).
  A legenda é o cabeçalho do cartão; o `tom-*` escolhe a cor do ícone. Cada seção, um assunto.
- **Formulário longo** (mais de 3 seções): `<main class="largo">` + `<div class="form-grade"><form data-indice>` e
  `<script src="secoes.js">`. O script monta o **índice lateral** (acompanha a rolagem, marca a seção com erro, abre a
  seção opcional recolhida; no celular vira uma barra de seções presa no topo) e leva ao primeiro erro ao voltar.
  Formulário curto (cadastros): só a coluna única de 960 px, sem índice.
- **Barra de salvar fixa** (`.barra-salvar`, no fim do `<form>`): o primeiro botão de envio é o que o Enter aciona, então
  vem primeiro; só um é primário. Leva o `span.estado-form` ("Alterações não salvas", aparece quando o formulário difere
  do que abriu). Sem botão "Cancelar": o Voltar do topo já faz isso.
- Seção que a pessoa pode pular fica em `<details class="opcional">`.
- Rótulo **acima** do campo, nunca placeholder no lugar de rótulo.
- Campos lado a lado só quando formam uma coisa só (CEP, rua e número; data e hora). O resto, em sequência.
- Foco, erro e obrigatório sempre visíveis. Erro ao lado do campo, e a tela volta sem perder o digitado.
- Opção marcada leva a cor da seção; escala de risco e parecer usam o semáforo (`.opcao.ok`, `.atencao`, `.grave`).

## Telas de leitura (a ficha do paciente é o modelo)

- **Cabeçalho de identidade**: faixa pastel na cor da situação (`tom-*`), com avatar (o mesmo das listas: `avatar_da_pessoa`),
  nome, selo, o que se **deduz** (há quanto tempo, previsão, idade, categoria) e as ações: **uma** primária, as de uso comum em
  pastel e as raras num menu **Mais** (`details.mais`/`.menu-mais`; destrutiva por último, em `.item-perigo`).
- **Cartões** de seção com ícone pastel: `{% call cartao('Título', 'icone', 'tom') %}` (`templates/_cartao.html`).
  Duas colunas em telas largas (`.ficha-grade`): o principal à esquerda e, à direita, o que se consulta toda hora; no celular a
  coluna lateral vem primeiro. Tela de leitura com duas colunas usa `main.largo`, para ficar alinhada às listas.
- **Sem redundância**: um dado aparece num lugar só. O cabeçalho mostra só o que se deduz; as datas ficam no cartão. A idade
  está no cabeçalho, não no cadastro.
- **Vazio não ocupa lugar**: `dados([(rótulo, valor), ...])` mostra só o que tem valor e junta o resto numa linha,
  "Não informado: ...".
- Impressão: botões e menus saem, uma coluna só, cartões sem cortar.

## Antes de entregar uma tela

1. Só variáveis de cor, espaço e canto do `base.html`. Nenhum valor solto.
2. Um botão primário. Perigo em vinho suave; sólido só na confirmação.
3. Estados com texto ou ícone, contraste conferido, foco visível.
4. Funciona no celular (390 px) e imprime (ou fica fora do papel, se for só de tela).
5. Capturas antes e depois conferidas no navegador.
