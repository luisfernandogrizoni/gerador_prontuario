# Padrões de interface

Como o sistema deve parecer e se comportar. Vale para toda tela nova e para o que for mexido em tela antiga. Foi definido
com o usuário em 2026-10-14 e aplicado a todas as telas do sistema. Revisado no celular (360 e 390 px, sem rolar de lado) e nos contrastes.

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
  Conferido: todos os pares de papel (forte sobre suave) passam de 4,5:1. `--mais-suave` (cinza claro) **não** serve para texto
  (2,6:1): só para ícone decorativo e traço; texto secundário usa `--suave` (5:1).
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

Todo botão é **pílula** (`--r-botao`); o cartão em que ele fica tem só 6 px de canto.

## Espaço, cantos, texto

- Espaços: `--e1` a `--e6` (4, 8, 12, 16, 24, 32 px). Não inventar valores.
- Cantos (decisão do usuário, 2026-11-10): **caixas e cartões só levemente arredondados, botões bem arredondados**. `--r-sm` 4, `--r-md` e `--r-lg` 6 (cartões, seções, janelas, avisos, ladrilhos de ícone, listas) e `--raio` 6; `--r-botao` 999 (pílula) para tudo que é botão: `.botao`, itens do menu do topo, controle segmentado, paginador. Não escrever `border-radius` com número solto: usar o token. Campos de formulário (`input`, `select`) e etiquetas (`.chip`) ficaram como estavam.
- Sombras: `--sombra` (cartão) e `--sombra-alta` (janela, aviso).
- Texto: título de página `--t-titulo`, de seção `--t-secao`, corpo `--t-corpo`, rótulo `--t-rotulo`. Mínimo de 14 px.
- Alvos de clique com pelo menos 24 px (no celular, 42 px; `.botao` já cuida disso).

## Páginas

- **Uma largura só** para todas as telas: o conteúdo usa a tela até 1760 px (`--largura-max`) e começa na mesma borda do menu, com
  recuo de 16 a 32 px (`--pad-pagina`). Nada de coluna estreita centralizada no meio de uma tela grande. O que é estreito por
  natureza (formulário curto, senha) fica **à esquerda** com `.estreito` (820 px) ou `.estreito.curto` (520 px). Só a entrada e a
  página de erro são centralizadas. As páginas de quem ainda não entrou (entrar, código de segurança, "esqueci minha senha", senha
  nova) estendem `entrar_base.html`: o cartão no meio do fundo pastel, com o logotipo.
- Ordem do topo: **Voltar** (`linha_voltar`), título, subtítulo, ações à direita. Toda tela, menos Início e Entrada, tem Voltar.
- `+ Triagem` e `+ Prontuário` só no cabeçalho.
- **Sem textos de instrução ou ajuda** nas telas: só estado e erros.

## Avisos

- Confirmação de uma ação (flash): cartão discreto no canto inferior direito, com botão de fechar, que some sozinho
  (`.mensagens`). No canto de baixo para nunca cobrir as ações do topo.
  Já vem pronto: basta `flash("...")`.
- Pendências e alertas: no quadro de avisos do Início, nunca como faixa no meio da página.
- Erro de formulário: ao lado do campo (`small.erro`) e a caixa `.caixa-erros` no topo.
- Informação de estado que a pessoa precisa ler (a senha é provisória, a sessão terminou, o e-mail foi enviado): a caixa
  `.caixa-info` (azul pastel), no topo do conteúdo. Não é para instrução.
- Pop-up que exige uma resposta (a troca do pen-drive, a sessão a vencer): `<dialog>` com um título, uma frase e os botões à direita.

## Defesa do navegador (CSRF e CSP: `csrf.py`)

- Formulário POST novo: `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` logo depois da tag `<form>`.
- `<script>` ou `<style>` escrito dentro da página: `nonce="{{ csp_nonce() }}"`. Script ou estilo em arquivo (`static/`) não precisa.
- **Nada de atributo de evento** (`onclick=`, `onsubmit=`, `onchange=`): a política do navegador não deixa rodar. Use `data-confirmar="texto"`
  (formulário ou botão), `data-imprimir`, ou um listener em um arquivo de `static/`.
- Chamadas do JavaScript ao próprio sistema: o `fetch` normal (o `static/base.js` acrescenta o cabeçalho do token). Para chamar outro site, é
  preciso liberá-lo em `connect-src` (`csrf.py`), e isso é uma decisão de segurança, não de interface.

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
- **Salvamento automático** (`rascunhos.py`, `static/rascunho.js`, `templates/_rascunho.html`): todo formulário longo (triagem, prontuário,
  acolhimento social, relatório de alta, ficha de saúde, registro de enfermagem, evolução) leva `{{ campo_rascunho(rascunho) }}` dentro do `<form>`,
  `{{ aviso_rascunho(rascunho) }}` acima dele e `rascunho.js` por último. O `span.estado-form` passa a dizer o que acontece com o que foi digitado, nunca só
  pela cor: âmbar "Alterações não salvas" (a caminho), azul "Rascunho salvo às 14:32 · ainda não gravado" e vinho para o que deu errado (sem conexão,
  sessão terminou). O navegador só pergunta ao sair se há texto que **não chegou ao servidor**. Formulário de cadastro (funcionário, nível, convênio) **não** leva
  rascunho: tem senha e é curto.
- **Nomes e endereços saem escritos do mesmo jeito** (`validacao.nome_proprio`, `frase`, `escrever_bem`): FULANO FICTICIO DE TAL ou fulano ficticio de tal
  viram "Fulano Ficticio de Tal" (de, da, do, das, dos e e em minúsculas; numeral romano e S/N preservados). Campo de nome, mãe, cônjuge, responsável, rua,
  bairro, cidade, profissão, religião, parentesco e cargo leva `data-forma="nome|local|frase|uf|email"` no `<input>` (`static/base.js` mostra o resultado ao
  sair do campo); o **servidor** refaz ao gravar (`FORMAS` nos modelos, `forma=` nos campos do acolhimento social). Só muda o que está **todo** em maiúsculas
  ou **todo** em minúsculas (McDonald e "Maria da Silva" ficam como foram escritos; em rua, bairro e cidade uma sigla num texto misturado, como "Jardim ABC",
  também fica). Acento o sistema **não** coloca (JOSE vira Jose): o nome tem de ficar como no documento. Texto livre (relatórios, evolução) nunca é mexido.
  Campo novo de nome ou endereço: ponha a forma nos dois lugares (modelo/`Campo` e `data-forma`).
- **Escolher arquivo**: nunca o campo cru do navegador. `<label>` com o rótulo acima e, dentro, `<span class="escolher-arquivo" data-escolher-arquivo data-extensao="pdf"
  data-limite="bytes">` com o `<input type="file">` transparente **por cima** (clicar e soltar um arquivo ali são do próprio navegador, e o teclado continua funcionando), o
  ícone (`i-enviar`), o texto "Arraste o PDF para cá" (no celular, "Toque para escolher"), a dica do limite e o botão pastel "Escolher arquivo". Escolhido o arquivo, a área
  vira um item da lista (chip PDF, nome, tamanho, "pronto para enviar") e o botão passa a "Trocar arquivo"; tipo ou tamanho que não servem aparecem na hora, em vinho suave, e
  travam o envio (`static/base.js`, seção 4; o servidor confere de novo). Um arquivo solto fora da área não troca a página pelo PDF. Modelo: o formulário de anexo da ficha.
- Seção que a pessoa pode pular fica em `<details class="opcional">`.
- A seção leva só o título (sem subtítulo nem texto explicativo): o que o papel traz a mais, como o subtítulo do modelo do
  escritório, fica no documento impresso, não na tela.
- Margem lateral de quem está dentro de um `fieldset` vem do cartão (`base.html`). Em CSS de página use `margin-top` e
  `margin-bottom`, nunca `margin: x 0 y`, que zera a lateral e encosta o conteúdo na borda.
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
- **O prontuário é da PESSOA, numa página só, com ABAS por função** (`templates/ficha.html`, endereço `/internacoes/<id>` ou `/pessoas/<id>/prontuario`): o **cabeçalho de identidade** ("Prontuário nº N ·
  passagem X de Y") e, embaixo, as abas: **Resumo** (a internação, o responsável e em que pé está cada área, com "Abrir" para a aba dela), **Dados pessoais**, **Serviço Social** (acolhimento e,
  de quem recebeu baixa, o relatório de alta), **Saúde** (ficha de saúde, registros de enfermagem, evolução; só de quem já foi internado), **Financeiro** (parcelas e contribuição), **Imprimir** e
  **Escaneados**. Quem tem mais de uma passagem (ou uma triagem) vê, entre o cabeçalho e as abas, a **faixa de passagens**: escolher uma troca o cabeçalho e as abas para os da passagem escolhida,
  **sem sair da página** (cada passagem é uma "visão" `.visao` já na página; a do endereço aberto sai à mostra e o endereço passa a ser o da escolhida). A aba aberta fica no endereço (`#aba-social`)
  e é lembrada por pessoa na sessão (salvar um relatório volta à mesma aba). As âncoras antigas (`#acolhimento`, `#saude`, `#alta`, `#parcelas`, `#escaneados`, `#envelope`) valem para a passagem do
  endereço aberto e abrem a aba onde estão (as outras levam `p<nº>-` na frente). Nada de blocos que abrem e fecham por passagem, nem de uma página por passagem.
- **A aba Imprimir é o único lugar de impressão dos impressos: a caixa "Documentos para imprimir" AO LADO do preview** (decisão do usuário, 2026-11-10; **não existe página de impressão à parte**).
  À esquerda, a caixa com uma caixinha por documento (os do conjunto padrão da passagem vêm marcados; o Serviço Social entra assim que o acolhimento começa, com o aviso "rascunho"), o menu "⋯" em cada linha
  (**Imprimir só este**, que marca só ele e imprime; **Baixar Word**), a declaração (outro documento, sem caixinha, que tem a escolha de quem assina e por isso abre a própria página: Abrir + menu) e a barra
  "N escolhidos" com **Imprimir os escolhidos** e **Baixar Word**. À direita, o **preview das folhas**: `/internacoes/<id>/impressos?itens=...&embutido=1` num `iframe`, carregado só quando a aba abre e
  **recarregado a cada caixinha marcada ou desmarcada** (sem nenhuma marcada, some e dá lugar a um aviso). Nada de barra em cima do preview: `?embutido=1` mostra só as folhas.
  **Imprimir** = recarregar o preview com `?imprimir=1`, e a página das folhas manda imprimir ao abrir (só assim o impresso conta como impresso: auditoria `doc.imprimir` e a marca do pedido de exames/enxoval).
  Os atalhos de imprimir (depois de "Salvar e imprimir" do acolhimento, da alta e da ficha de saúde; "Imprimir" das triagens e da página inicial) vão direto à ficha:
  `/internacoes/<id>?itens=a,b&imprimir=1#aba-imprimir` marca esses documentos e já manda imprimir (o `?imprimir=1` sai do endereço, e F5 não imprime de novo). Um endereço antigo
  `/internacoes/<id>/impressos` (sem `embutido`) só redireciona para a aba. Quem não tem a permissão `documentos` e só lê relatórios sigilosos vê, na mesma caixa, só o que lê (o preview pede só esses itens,
  que abrem sem a permissão). No celular a caixa fica em cima e o preview embaixo.
  O preview é a **única** página que pode ficar dentro de outra (mesmo endereço: `X-Frame-Options: SAMEORIGIN` e `frame-ancestors 'self'`, em `csrf.EMOLDURAVEIS`); todas as outras seguem em `DENY`.
- **Uma ação principal por área + menu "Mais"** (`details.mais`, fechado sozinho por `static/base.js`): cada linha do Acompanhamento mostra a situação (selo) e UM botão claro
  (Preencher, Continuar, Alterar); o secundário (histórico de versões, registros de enfermagem, evolução) vai no menu. Nenhum botão de documento mora dentro de uma área.
- **Sem redundância**: um dado aparece num lugar só. O cabeçalho mostra só o que se deduz; as datas ficam no cartão. A idade
  está no cabeçalho, não no cadastro.
- **Vazio não ocupa lugar**: `dados([(rótulo, valor), ...])` mostra só o que tem valor e junta o resto numa linha,
  "Não informado: ...".
- Impressão da ficha: botões, abas e menus saem, uma coluna só, cartões sem cortar (as abas saem todas, menos a da página de impressão embutida).

## Documentos: os que se imprimem e os escaneados ficam SEPARADOS

- Em cada passagem da ficha (`templates/ficha.html`) são **duas abas**, cada uma com um propósito: **Imprimir** (o que o sistema gera: prontuário, capa do envelope, manual, ficha
  multiprofissional, relatórios do Serviço Social e de alta, pedido de exames, enxoval, declaração) e **Escaneados** (os PDFs do papel assinado). Nunca na mesma lista: quem quer imprimir não vê
  PDF, e quem procura um PDF não vê impresso.
- **Imprimir**: a caixa de documentos com as caixinhas ao lado do preview (veja acima); os botões de documento **não** moram dentro das áreas (Serviço Social, Saúde...); a página de relatórios
  usa o mesmo jeito (`templates/_acoes_documento.html`).
- **Escaneados**: um botão só, **Anexar PDF** (abre uma janela com o arquivo, o título e a **área**), a lista com o chip da área, a contagem na própria aba e o **filtro por área** (Todos, Saúde,
  Social, Financeiro, Geral).
- O que cada pessoa vê dos escaneados segue o sigilo da área (`app._pode_ver_area_do_anexo`): o do Serviço Social só vai a quem lê o Serviço Social, o de Saúde a quem lê a saúde, o Financeiro a quem
  tem a permissão do financeiro, o geral a quem tem `documentos`; o administrador vê tudo. Quem não vê uma área também não anexa nela.

## Anexos (documentos escaneados)

- O PDF do documento físico assinado entra pelo cartão **Documentos escaneados** da passagem na ficha (`templates/ficha.html`, `anexos.py`): linha com o chip PDF, o título, quando e por quem foi
  enviado e o tamanho, a área; **Abrir** (outra aba) e, no menu "Mais", **Baixar PDF**, **Vincular à área** e **Remover** (com confirmação). Quem removeu esconde; só o administrador vê o removido
  (tracejado, título riscado) e restaura ou apaga de vez. **Anexar PDF** abre uma janela: a área "Escolher arquivo" (ver Formulários) com o limite dito nela e conferido no navegador antes de enviar
  (`data-limite`), o título, a **área** (Geral, Saúde, Financeiro, Serviço Social) e o botão **Anexar** em pastel (`.botao.suave`); o servidor confere de novo.
- Quem vê mas não pode anexar (`anexar`) não vê o botão **Anexar PDF** nem o Remover. Na impressão da ficha os botões saem.

## Listas que crescem (internos)

- Lista que pode chegar a milhares de registros **não** baixa tudo para o navegador: `static/tabela.js` (`TabelaPaginada`) pede ao servidor só a página que mostra,
  e `busca_de_internos.py` faz a busca, os filtros, a ordem e a paginação (`GET /api/internos/busca`). A lista de triagens, que é curta e some sozinha,
  continua com a `TabelaDinamica` (tudo no navegador).
- **Uma linha por PESSOA**: quem teve mais de uma passagem aparece uma vez só, com a mais recente, e o CPF/idade ganha "2 passagens"; as contagens das abas são de pessoas.
- **Busca**: várias palavras em qualquer ordem (todas precisam aparecer), sem acento e sem diferença de maiúsculas; nome, mãe, responsável, cidade, categoria, situação,
  e números (CPF, RG, cartão SUS, telefones, com ou sem pontuação); `#123` acha a pessoa pelo número de qualquer passagem dela. Sem ordem escolhida, quem tem o nome começando pelo que foi
  digitado vem antes de quem só tem a mãe ou o responsável com aquele nome.
- **Filtros**: situação (abas Ativos | Inativos | Todos), categoria e ano de início; os números das abas já levam em conta a busca e os outros filtros. "Limpar filtros"
  aparece quando há busca ou filtro. 25, 50 (padrão) ou 100 por página, e "Todos (para imprimir)", que tem teto (`LIMITE_DE_TODOS`).
- Tudo o que a pessoa escolhe (busca, filtros, ordem, página, tamanho) fica na URL; o "voltar" reencontra a lista como estava. **Salvar um prontuário leva à ficha da
  pessoa** (não à lista): a ficha confirma "Prontuário de X salvo." e, em "Salvar e baixar prontuário", começa o download do conjunto (`?baixar=1`). A atualização automática (30 s) só pede a página atual e espera se a aba está escondida.
- **Auditoria**: cada consulta à lista é uma leitura de dados pessoais, mas a trilha guarda UMA linha por pessoa a cada minuto (e por tipo: com ou sem busca), nunca o
  texto buscado (`auditoria._leitura_da_lista`).
- Limite conhecido: o filtro roda em Python sobre uma consulta leve de todos os internos (cerca de 0,2 s com 5 mil registros). Passando de dezenas de milhares, o próximo
  passo é uma coluna de busca já normalizada no banco.

## Estados vazios e erros

- **Estado vazio** (lista sem registro, lixeira vazia): `.vazio` com um ícone pastel (`.icone-vazio`) e uma frase curta;
  as listas dinâmicas já fazem isso (static/tabela.js).
- **Páginas de erro** (404, 403, 405, 500): `templates/erro.html`, com ícone, o código, o que houve e **um** caminho de volta.
  O de API (JSON) segue com a resposta padrão. Nenhum detalhe técnico aparece na tela (fica no registro do servidor).
- **Entrada**: fundo em pastel (rosa da marca e azul) com o cartão em destaque; é a única tela com fundo diferente.
- **Cadastros**: as abas têm ícone (`_abas_cadastros.html`); formulário curto sem "Cancelar".

## Níveis de acesso na tela

- **Esconda o que a pessoa não pode usar**, nunca ofereça botão que dá "sem permissão": `{% if pode('triagem') %}` no template
  (permissões em `permissoes.py`); nas listas dinâmicas, `permissoes_js()` leva o mesmo ao JavaScript (`const PODE = ...`).
  Um botão cheio que some não deixa buraco: o que sobra continua alinhado. Menu "Mais" sem nenhum item não aparece.
- **A tela nunca é a trava.** Quem manda é a regra da rota (`permissoes.REGRAS`, nega por padrão). Rota nova precisa de regra,
  senão fica fechada para todos; ação do JavaScript recebe JSON 403 e mostra o aviso que a lista já sabe mostrar.
- **Grade de permissões** (`cadastro_permissoes.html`): permissão nas linhas, níveis nas colunas, um cartão por grupo (formulário
  com índice e barra de salvar). Cada célula é um sinal com texto (✓ pode, – não pode), nunca só cor; o anel marca o nível mínimo.
  Quem só pode ler vê o mesmo sem as opções. No celular cada permissão vira um bloco com o nome de cada nível ao lado do sinal.

## Antes de entregar uma tela

1. Só variáveis de cor, espaço e canto do `base.html`. Nenhum valor solto.
2. Um botão primário. Perigo em vinho suave; sólido só na confirmação.
3. Estados com texto ou ícone, contraste conferido, foco visível.
4. Funciona no celular (390 px) e imprime (ou fica fora do papel, se for só de tela).
5. Capturas antes e depois conferidas no navegador.
