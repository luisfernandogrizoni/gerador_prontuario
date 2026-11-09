# Importar registros históricos (ex-residentes de pastas e planilhas antigas)

Pedido do usuário em 2026-11-09: "colocar essa galera toda no sistema". Um levantamento da pasta `Internos` (OneDrive) e da `Lista de Internos.xlsx` contra o banco do
servidor achou 434 pessoas, das quais 57 já estavam no sistema e **377 não** (a conta primeiro dizia 436 e 379: duas pastas-contêiner, "SAIU 2021" e "SAIU EM 2021 E 2022",
tinham sido contadas como pessoas). Quase todas são ex-residentes antigos: 124 têm dados na planilha (datas, motivo, convênio, cidade, CPF) e o resto só tem o nome da pasta e o
ano da pasta de saída. Os arquivos das pastas são, na maioria, Word antigo (só 187 são PDF), então **os documentos não entram**. Mas os 2.494 formulários Word do prontuário
(ficha de primeiro contato, contrato terapêutico, informativo socioeconômico...) foram lidos e trouxeram, para quem faltava, CPF válido (151), nascimento (191) e data de entrada
(219) que a planilha não tinha; isso entrou na lista de importação. Este texto descreve o que o sistema ganhou para isso e a tela **Para conferir**, em que a equipe completa
cada registro com o prontuário de papel.

## Decisões

- **Só o cadastro**: nome, CPF, nascimento, cidade, convênio, entrada, saída e motivo, quando existirem. Os documentos continuam nas pastas. O que o Word trouxe além disso (RG,
  endereço, telefone, estado civil, escolaridade, religião, profissão, mãe, responsável, cartão SUS) está só na planilha de conferência: o script ainda não o importa.
- **Nada é inventado**: quem não tem datas entra sem datas (inativo), com a marca "importado" e a origem ("Ex-Residentes / Saíram em 2024"), e o quadro de avisos não cobra a data.
- **Uma internação por pessoa** nas pastas repetidas; se a lista trouxer duas entradas diferentes para a mesma pessoa, entram duas internações (há dado).
- **O banco real nunca é alterado sem você pedir**: o script só simula por padrão, e gravar exige `--gravar`, backup e a palavra SIM.

## O que mudou no sistema

- `Internacao.origem` (coluna nova, criada sozinha na subida, vazia = digitado no sistema): `"<de onde veio> | lote AAAAMMDD-HHMMSS"`. Propriedades `importado`, `origem_txt` e
  `lote_da_importacao`. `origem` está em `CamposDeFormulario.CAMPOS_DO_SISTEMA`: o formulário nunca a altera.
- **Quadro de avisos**: o aviso "Inativo sem data de saída" não aparece para registro importado.
- **Formulário do prontuário**: num registro importado a *data de internação* e o *convênio* deixam de ser obrigatórios (sem isso nem um CPF errado se corrigiria nele; o convênio
  em branco aparece como "A definir"). Ao salvar, um registro importado **continua inativo** mesmo sem término nem motivo (antes, sem eles, viraria ativo). Registro comum não muda.
- **Ficha**: faixa azul "Registro importado (origem). São dados parciais: confira e complete o que faltar".
- **Auditoria**: ação `importacao.lote` (importou ou desfez um lote); `conferido.marcar` e `conferido.desfazer` (veja a tela Para conferir).
- `requirements.txt` ganhou `openpyxl` (ler a lista em Excel).

## A tela "Para conferir" (`conferencia.py`, `/conferir`)

Depois de importar, quem está com a pasta de papel na mão completa cada registro. O item **Para conferir** do menu (com o número dos que faltam) aparece para quem pode editar prontuários
(Escritório, enfermeira e administrador) e some quando não há importados.

- **A fila** são os importados ainda não conferidos (`Internacao.origem` preenchida e `conferido_em` vazio), do mais recente para o mais antigo: pela data de saída ou de entrada; sem
  data, pelo ano que a pasta de origem diz; "anos anteriores" por último; dentro do ano, por nome. Há um contador ("142 de 377 conferidos") e uma barra de progresso.
- **Filtros**: nome, pasta de origem, "o que falta" (CPF, nascimento, data de entrada, data de saída, motivo, convênio, endereço, nome da mãe, responsável) e a situação (a conferir,
  já conferidos, todos). "O que falta" é só um guia: o papel pode simplesmente não ter a informação, então **conferir é um ato explícito**, nunca automático.
- **Formulário de conferência**: *Conferir* abre o formulário de prontuário do registro, com uma faixa que diz o que está em branco e dois botões a mais: **Salvar e ir para o próximo**
  e **Conferido: salvar e ir para o próximo** (grava, marca como conferido e abre o seguinte da fila, com os mesmos filtros, que viajam em campos escondidos `c_q`, `c_origem`, `c_falta`).
  Sem mais ninguém na fila, volta à lista dizendo isso. O botão Salvar comum nunca marca nada como conferido.
- **Ficha**: a faixa do importado ganha *Conferir agora* e *Marcar como conferido*; depois de conferido, a faixa diz quem conferiu e quando e oferece *Reabrir conferência*.
- **Dados**: `Internacao.conferido_em` e `conferido_por` (colunas novas, criadas sozinhas na subida; estão em `CAMPOS_DO_SISTEMA`). Marcar e reabrir entram na trilha de auditoria.
- **Permissões**: `lista_para_conferir` e `marcar_conferido` usam a permissão `internacao` (e, por isso, o polo: a psicóloga e a médica não veem a tela).

## A lista

Planilha `.xlsx` (aba `Importar`, ou a primeira) ou CSV (Excel em português: ponto e vírgula, cp1252 ou UTF-8), **uma linha por internação**, com estas colunas (a ordem não
importa; só *Nome* é obrigatória): `Nome | CPF | Nascimento | Cidade | Estado | Convênio | Entrada | Saída | Motivo | Origem | Forçar`.

- Linhas com o mesmo CPF (ou, sem CPF, o mesmo nome) são **uma pessoa** com várias internações.
- Datas: `dd/mm/aaaa`, `aaaa-mm-dd` ou data do Excel. Vazio, `-` e `Não informado` = sem data.
- CPF que não confere pelo dígito verificador entra **em branco** (aviso no relatório). O Excel apaga zeros à esquerda: o script completa se o dígito conferir.
- Convênio: `Particular`, `CAPS AD`, `Prefeitura Tarumã` (ou os nomes do Cadastros; `Social` vira Particular com contribuição R$ 0,00, que é a categoria Social). Desconhecido = em branco.
- Motivo: `Conclusão`, `Desistência`, `Desligamento`; `Exclusão` vira Desligamento (aviso). `Falecimento` e `Não informado` ficam em branco (o sistema não tem esses motivos).
  As tabelas `MOTIVOS` e `CONVENIOS` no começo de `importar_historico.py` mudam isso.
- `Forçar = sim`: cria mesmo que já exista alguém com o mesmo **nome** no sistema (só para quem for outra pessoa). Não vale contra quem já foi importado antes.

## Como rodar (no servidor, PowerShell)

```powershell
cd C:\prontuario
.venv\Scripts\python.exe importar_historico.py C:\caminho\lista.xlsx
```

Só simula: mostra quantas pessoas e internações entrariam, quem seria pulado (já está no sistema, pelo CPF ou pelo nome, inclusive na lixeira) e quem tem erro, e grava o
relatório em `logs\importacao-AAAAMMDD-HHMMSS-simulacao.csv` (uma linha por linha da lista, com os avisos). Corrija a lista até a simulação sair como você espera. (O relatório e a lista têm **nomes e CPFs**: guarde-os com o mesmo cuidado do banco e apague quando não precisar mais.) Depois:

```powershell
.venv\Scripts\python.exe importar_historico.py C:\caminho\lista.xlsx --gravar
```

Faz o backup, mostra o resumo, pede **SIM** e grava tudo numa transação só (ou entra tudo, ou nada). **Havendo linhas com erro, não grava** (`--pular-erros` grava o que está
certo e deixa os erros de fora). Repetir o comando com a mesma lista não duplica ninguém.

## Desfazer um lote

O número do lote aparece ao fim da importação, no relatório e na faixa da ficha (`origem`). Para desfazer:

```powershell
.venv\Scripts\python.exe importar_historico.py --desfazer 20261109-153000            # só simula
.venv\Scripts\python.exe importar_historico.py --desfazer 20261109-153000 --gravar   # apaga de vez, depois do backup e do SIM
```

Só apaga o que **ninguém usou depois**: com parcelas, acolhimento, ficha de saúde, relatório de alta, registros de enfermagem, evoluções, documentos anexados, histórico de
versões ou notificações, ou editado dias depois de importado, o registro fica e é listado. A pessoa que ficar sem nenhuma internação sai junto.

## Para quem for mexer

- A leitura do banco nunca altera nada na simulação (só `SELECT`). `gravar()` cria `Pessoa` e `Internacao` pelo `preencher` (nome e cidade no padrão de escrita do sistema, CPF só dígitos).
- Um teste novo (`teste_importar_historico.py`, no scratchpad da sessão) cobre migração, simulação, gravação, repetição, Forçar, lixeira, CSV, as telas com registro importado e o desfazer.
- Os **documentos** (7,5 mil arquivos Word e 187 PDFs) ficaram de fora de propósito; se um dia entrarem, os PDFs vão pelo recurso de documentos escaneados (`anexos.py`, até 25 MB cada).
