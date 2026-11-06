# Dois polos, notificações e relatório de alta

Pedido do usuário em 2026-11-06. O sistema passa a separar os funcionários em dois **polos de trabalho** e a avisar cada polo do que o outro faz.
(Não confundir com o "polo 1 e polo 2" do plano de segurança, que são os dois *lugares* que usam o mesmo banco por VPN.)

## Os polos

- Campo **Polo de trabalho** no cadastro do funcionário (Cadastros > Funcionários; só o administrador muda): **Escritório** ou **Saúde**.
- **Escritório**: administrador, assistente social, equipe administrativa. **Saúde** (a casa de acolhida): enfermagem, psicologia, medicina, nutrição, coordenação.
- Os dados são os mesmos para todos; o polo só restringe o que cada um faz e decide quem é avisado.
- Quem ainda está *Não definido* vale **como antes** (só o nível de acesso decide), e a página inicial do administrador cobra o que falta.
- O nível de acesso (Administrador, Operador, Consulta) continua valendo: o polo só restringe e direciona. O administrador passa por tudo.

## Quem faz o quê (com o nível já permitindo)

| Ação | Escritório | Enfermeira(o) | Resto do Saúde | Administrador |
|---|---|---|---|---|
| Registrar e editar triagem | sim | não | não | sim |
| Ver a lista de triagens | sim | sim (só leitura) | sim (só leitura) | sim |
| Admitir triagem (virar prontuário) | sim | sim | não | sim |
| Cadastrar e editar prontuário | sim | sim | não | sim |
| Dar baixa | **não** | sim | não | sim |
| Registrar a chegada do envelope em papel | sim | não | não | sim |
| Imprimir documentos e anexar PDFs | sim | sim | sim | sim |
| Parcelas, relatórios, cadastros, excluir, unificar | pelo nível | não | não | sim |

"Enfermeira(o)" = função *Enfermeiro(a)* no cadastro, com COREN válido (categoria ENF). O resto do polo Saúde (psicóloga, médica, nutricionista, coordenação) segue lendo e
escrevendo na evolução multiprofissional como antes, mas não cadastra, admite nem dá baixa.

As permissões ficaram assim em `permissoes.py`: `triagem` (só Escritório; deixou de incluir *admitir*), `admitir` (nova), `internacao`, `baixa` (agora só dar baixa) e `envelope` (nova: a
chegada do envelope, que era da `baixa`). `POR_POLO` diz, para cada uma, o que cada polo pode; quem escolheu um nível mínimo para `baixa` ou `triagem` nas Permissões continua com
a mesma escolha em `envelope` e `admitir` (`migracoes._permissoes_dos_polos`).

Dar baixa também não passa pelo formulário do prontuário: se quem salva não pode dar baixa e o formulário traz término ou motivo de quem está ativo, o formulário volta com o aviso (o resto não é salvo).

## Notificações (`notificacoes.py`)

Cada destinatário tem a sua notificação (tabela `notificacoes`); quem fez a ação nunca é avisado dela, e só vale para o que acontece depois da atualização.

- **Novo prontuário do Escritório** → a enfermeira(o) (função, não o polo inteiro). Quando alguém que não é do polo Saúde (o Escritório ou o administrador) cadastra um prontuário novo
  (ativo) ou admite uma triagem, o aviso aparece no quadro de avisos da página inicial e some quando **ela** abre a ficha da pessoa. Um prontuário novo já encerrado (cadastro de histórico) não avisa.
- **Baixa** → o administrador e a assistente social (marca *Serviço Social*), no **sino** do cabeçalho: contador de não lidas, lista com histórico (`/notificacoes`) e "Marcar todas como
  lidas". Abrir a ficha da pessoa também marca como lidas as notificações dela sobre ela. A baixa pode vir da lista de internos ou do formulário do prontuário. O sino só aparece para quem recebe
  por função (administrador, assistente social) e para quem já recebeu alguma.
- O Escritório **não** é avisado quando a enfermeira cadastra ou admite.

## Relatório de alta (`relatorio_alta.py`)

O texto livre que a assistente social escreve quando a pessoa recebe baixa, de propósito sem perguntas fixas (versão "crua").

- Tela `/internacoes/<id>/relatorio-de-alta`: um campo de texto; *Salvar rascunho*, *Salvar e imprimir* e *Finalizar e assinar*.
- Documento no timbre da casa (junto dos outros impressos: `?itens=relatorio-alta`, também em Word): dados básicos do acolhido (nome, nascimento, CPF, convênio, período, tempo de permanência e
  motivo da saída), o texto e o campo de assinatura com o **nome e o CRESS** da assistente social.
- Mesmo molde do acolhimento social: **sigiloso** (escrevem a assistente social e o administrador; lê, sem editar, quem recebeu a permissão de ler os sigilosos; os outros só veem na ficha se
  foi feito); finalizar guarda data, hora e assinatura (exige o CRESS no cadastro); depois de finalizado ela ainda altera, e cada alteração vira uma versão no histórico, que só o administrador vê
  (`versoes.ALTA`). A trilha de auditoria registra salvar, finalizar, alterar e abrir, nunca o conteúdo.
- **Cobrança** no quadro de avisos da assistente social (e do administrador), sem "Ciente", até finalizar: mostra há quantos dias foi a baixa e **fica vermelha depois de 7 dias**. Só cobra baixas
  dadas depois da atualização (`Internacao.baixa_em`); as de antes podem ter o relatório escrito pela ficha, mas não geram cobrança.

## Para quem for mexer

- Toda rota nova entra em `permissoes.REGRAS` e na classificação da auditoria (um teste confere).
- `baixa_em` está em `CamposDeFormulario.CAMPOS_DO_SISTEMA`: coluna nova de `Internacao` que não vem do formulário precisa estar lá.
- Rascunho automático (`rascunhos.py`) ainda não cobre o relatório de alta; o texto só é guardado ao salvar.
