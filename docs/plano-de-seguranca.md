# Plano de segurança

Combinado com o usuário em 2026-10-15 (decisões da mesma data nas seções 4 e 6). Serve de mapa: o que já existe, o que falta, em que ordem fazer, o que o sistema faz
sozinho e o que só uma pessoa na casa pode fazer. Cada fase é entregue num PR pequeno, com testes, e esta página é atualizada
no mesmo PR.

> Não é parecer jurídico. As referências da última seção devem ser conferidas nos textos oficiais antes de fixar prazos e
> números. Para a parte da LGPD, vale uma conversa com quem cuida do jurídico ou da contabilidade da associação.

## 1. O que o sistema guarda e por que isso importa

- **Dados pessoais de acolhidos e responsáveis**: nome, CPF, RG, endereço, telefones, filiação.
- **Dados de saúde e de situação social**: convênio, motivo da internação, exames, e o **acolhimento social** (uso de
  substâncias, tentativa de suicídio, violência, situação jurídica, rede de apoio). Na LGPD isso é **dado pessoal sensível**
  (art. 5º, II, e art. 11), com cuidado redobrado, e vem de pessoas em um momento de fragilidade.
- **Financeiro**: contribuição e parcelas de cada internação.
- A LGPD (art. 46) exige medidas técnicas e administrativas para proteger esses dados de acesso não autorizado e de perda, e
  (art. 48) a comunicação de incidente à ANPD e ao titular quando houver risco ou dano relevante.

Como o sistema roda: um computador do escritório (Windows 11 Home, `C:\prontuario`) serve os 3 computadores da rede interna,
com banco SQLite, sem custo de hospedagem. Isso tem uma vantagem de segurança (o dado não está na internet) e riscos próprios
(um computador só, na mão de quem trabalha ali, sem ninguém de TI).

## 2. Onde estamos hoje

| Área | O que já existe | Lacuna |
|---|---|---|
| Entrada | Login obrigatório em toda rota; senha só como hash (scrypt); **fase 3**: senhas fáceis barradas, senha provisória, sessão que termina em 30 min sem uso, limite por endereço, e-mail confirmado, "esqueci minha senha" e segundo fator (aplicativo autenticador); 5 erros bloqueiam o usuário por 10 min; mensagem igual para usuário inexistente e senha errada; trocar a senha derruba as outras sessões | O segundo fator é opcional (o sistema cobra do administrador, mas não obriga); o e-mail é um canal que a casa não controla por inteiro |
| Quem pode o quê | **Fase 1 (esta entrega)**: cascata de níveis com permissões configuráveis, nega por padrão, funcionário desativado perde o acesso | Quem tem "ver" vê todas as fichas; não há registro de quem viu o quê |
| Rastro | **Fase 2**: trilha de auditoria com tela só do administrador (entradas, leituras, alterações, administração e acessos negados); mais o registro técnico do servidor | Quem controla o computador e o banco consegue mexer na tabela (a trilha não protege do dono da máquina); sem política de retenção ainda (fase 8) |
| Rede | Porta aberta só para a sub-rede local (firewall); sem acesso externo; **fase 4**: HTTPS pelo Tailscale (certificado que ele emite e renova), com modo de transição e modo final que fecha o http da rede local | Até o usuário ligar, **HTTP sem criptografia** (a página inicial lembra); depois, quem não tem o Tailscale não abre |
| Navegador | Cookie HttpOnly e SameSite=Lax; nosniff; X-Frame-Options; sem cache das páginas; **fase 7**: token CSRF em todo envio, política de conteúdo (CSP) com nonce, Permissions-Policy e COOP/CORP | `style="..."` dentro das tags ainda é permitido; o ViaCEP recebe o CEP digitado |
| Dados | Excluir é em duas etapas (lixeira); banco fora do git; hook que barra dado real no repositório; **fase 5**: cópia externa criptografada em pen-drives em rodízio, conferida na hora, com aviso, tela de situação e teste de restauração | Depende de alguém trocar o pen-drive toda semana (o sistema avisa) e de a frase de recuperação estar em papel; o backup do dia (`.db`) segue sem criptografia no computador |
| Servidor | Tarefas agendadas, firewall, pasta `instance/` protegida; **fase 6**: roteiro do Windows e do roteador e verificador que confere sozinho (avisa na página inicial); **fase 9**: auditoria mensal das bibliotecas, revisão trimestral dos acessos e semestral do plano | Roda como SYSTEM (a troca por conta limitada ficou para um dia, feita junto); o roteiro depende de alguém percorrê-lo |
| Papel | — | Sem inventário de dados, política de retenção nem plano de resposta a incidente (o termo de sigilo foi dispensado: decisão da casa, 2026-10-16) |

## 3. Ameaças que o plano cobre (da mais provável para a menos)

| # | Ameaça | Exemplo na casa | Medida | Fase |
|---|---|---|---|---|
| 1 | **Perder tudo** | O disco do computador queima, ransomware, o computador é roubado, alguém apaga a pasta | Backup criptografado fora do computador, com rodízio e teste de restauração | 5 |
| 2 | **Quem tem login vê ou faz o que não devia** | Funcionário curioso, estagiário com acesso total, ex-funcionário que ainda entra | Cascata de acesso, bloqueio de desativado, trilha de auditoria | **1**, 2 |
| 3 | **Senha fraca, repetida, compartilhada ou anotada** | "Todo mundo usa o login do escritório" | Um usuário por pessoa, lista de senhas fracas, troca da provisória, segundo fator para administrador | 3 |
| 4 | **Alguém escuta a rede** | Wi-Fi do escritório com senha conhecida por muita gente; visitante conectado | HTTPS na rede interna, Wi-Fi separado para visitante | 4, 6 |
| 5 | **Acesso físico ao computador servidor** | Roubo, pessoa de passagem mexendo na máquina | Disco criptografado, bloqueio de tela, sala fechada | 6 |
| 6 | **Ataque pelo navegador** | Link malicioso faz o navegador de um funcionário logado executar uma ação | Token CSRF, CSP | 7 |
| 7 | **Dado que sai do sistema** | Prontuário baixado em pen-drive e esquecido; impressão deixada na impressora | Permissão própria para documentos, trilha de quem baixou | **1**, 2 |
| 8 | **Sistema exposto na internet sem querer** | Alguém libera uma porta no roteador "para acessar de casa" | Checklist do roteador, firewall só para a rede local | 6 |
| 9 | **Falha em uma biblioteca** | Vulnerabilidade conhecida no Flask, Werkzeug, python-docx | Auditoria mensal das dependências | 9 |

Acesso de fora do escritório (de casa, do celular, de um segundo polo) **muda o risco todo** e por isso não vale sem a
fase 10 (VPN), nunca abrindo porta no roteador.

## 4. As fases

| Fase | O que entrega | Quem faz | Situação |
|---|---|---|---|
| 1 | Cascata de acesso por nível | Sistema | **Feita** (nesta entrega) |
| 2 | Trilha de auditoria (com tela dentro do sistema, só administrador) | Sistema | **Feita** (2026-10-15) |
| 3 | Contas e sessões mais fortes: tempo ocioso, e-mail validado, "esqueci minha senha" e segundo fator | Sistema + usuário (senha da caixa de envio no servidor, e-mail de cada funcionário e celular com app autenticador) | **Feita** (2026-10-15); falta o usuário configurar |
| 4 | HTTPS (celular e todos os navegadores) | Sistema + usuário (instalar o Tailscale) | **Feita** (2026-10-16); falta o usuário ligar |
| 5 | Backup que sobrevive ao computador | Sistema + usuário (pen-drives e rotina) | **Feita** (2026-10-15); falta o usuário configurar |
| 6 | Servidor Windows, rede e roteador | Quase tudo o usuário (roteiro passo a passo e verificador) | **Feita** (2026-10-16); o usuário percorre o roteiro; a conta limitada no lugar de SISTEMA ficou de fora de propósito |
| 7 | Token CSRF e CSP | Sistema | **Feita** (2026-10-16) |
| 8 | LGPD no papel | Usuário, com modelos prontos do sistema | A fazer |
| 9 | Manutenção contínua | Sistema (avisos) + usuário | **Feita** (2026-10-16); falta rodar `auditar-dependencias.ps1 -Agendar` uma vez |
| 10 | Segundo polo e acesso de fora do escritório (VPN) | Sistema + usuário (instalar o Tailscale) | **Feita** (2026-10-16); falta o usuário ligar |

Ordem sugerida: 1 → 5 → 2 → 3 → 4 + 10 (juntas: HTTPS pela VPN e o segundo polo) → 7 → 6 → 8 → 9. O backup (5) sobe na frente porque
perder tudo é a ameaça mais provável e a mais cara, e passa a ser obrigatório quando o polo 2 depender do computador do escritório.

### Fase 1 — Cascata de acesso por nível (entregue)

**Ideia.** Os níveis (Cadastros > Níveis de acesso) já formam uma cascata: o primeiro é o do administrador e cada nível tem
tudo o que os de baixo têm. Agora cada **permissão** tem um **nível mínimo**: quem está nele, ou acima, pode. O administrador
escolhe isso em **Cadastros > Permissões**, numa grade de permissões × níveis. Mover um nível na cascata muda quem passa, sem
refazer nada.

**Regras.**

1. **Nega por padrão.** Toda rota precisa estar em `permissoes.REGRAS`. Rota nova sem regra fica fechada para todos (até para o
   administrador) e o servidor registra o aviso. Um teste confere que não sobrou rota sem regra.
2. **Conferido num lugar só**, antes da rota rodar (`permissoes.exigir_permissao`), nunca espalhado pelas telas. As telas só
   **escondem** o que a pessoa não pode usar, para não oferecer botão que não funciona (`pode('triagem')` nos templates; as listas
   recebem as permissões por `permissoes_js()`).
3. **Administrador pode tudo.** Enquanto nenhum administrador tem usuário vinculado (sistema recém-instalado), quem está logado
   conta como administrador, senão ninguém conseguiria vincular o primeiro.
4. **Login sem funcionário ligado** cai no nível de menos acesso (o último da cascata).
5. **Funcionário desativado perde o acesso**: não entra mais (a senha certa não basta) e a sessão aberta é derrubada na página
   seguinte. Reativar devolve o acesso.
6. **O que só o administrador faz é fixo**, não se configura: criar usuário e senha, mudar nível, mexer nas permissões, lixeira.
7. **Acolhimento social fica fora da cascata**: é pela marca "Serviço Social" no cadastro do funcionário (e o administrador),
   porque é uma função, não uma hierarquia.
8. **Negar não quebra nada**: página (403) diz o nível da pessoa e o que faltou; ação do JavaScript recebe JSON 403; toda
   negação vai para `logs/servidor.log` com quem, o quê e qual permissão. Mudar permissão também (quem, de qual nível para qual).

**Padrão de fábrica** (o administrador muda na tela). Mantém o que o Operador já fazia, exceto que **unificar cadastros** e
**cadastrar convênios e funcionários** passam a ser do administrador (decisão do usuário, 2026-10-15; lançar parcelas continua
com o operador) e que o nível **Consulta** passa a só consultar:

| Permissão | Administrador | Operador | Consulta |
|---|:-:|:-:|:-:|
| Ver triagens, internos, fichas e o início | ✓ | ✓ | ✓ |
| Ver e baixar relatórios | ✓ | ✓ | ✓ |
| Imprimir e baixar os documentos do acolhido | ✓ | ✓ | – |
| Registrar e editar triagens (inclui mudar a situação e admitir) | ✓ | ✓ | – |
| Registrar e editar prontuários | ✓ | ✓ | – |
| Dar baixa e anotar o prontuário em papel | ✓ | ✓ | – |
| Lançar e excluir parcelas | ✓ | ✓ | – |
| Excluir registros (vão para a lixeira) | ✓ | ✓ | – |
| Unificar cadastros duplicados | ✓ | – | – |
| Cadastrar convênios e funcionários (sem usuário e senha) | ✓ | – | – |
| Criar usuários, trocar senhas, definir níveis e permissões | ✓ | – | – |
| Lixeira: restaurar e apagar de vez | ✓ | – | – |
| Ver a situação do backup e dos pen-drives (fase 5) | ✓ | – | – |
| Ver a trilha de auditoria (fase 2) | ✓ | – | – |
| Acolhimento social (sigiloso) | ✓ | só com a marca | só com a marca |

Quem tem a permissão de cadastros vê também as abas Níveis de acesso e Permissões, só para ler; sem ela a área Cadastros inteira
some do menu. O administrador pode devolver qualquer uma ao Operador na grade, a qualquer momento.

**Limites desta fase** (por isso existem as seguintes):

- Quem tem "ver" enxerga **todos** os acolhidos. Não há restrição por registro nem por convênio.
- Documento baixado ou impresso sai do controle do sistema (por isso `documentos` é uma permissão própria, e a trilha da fase 2
  completa).
- Não há registro de **quem viu** o quê (fase 2).

**Como conferir.** `teste_permissoes.py` (74 verificações): sementes, cobertura das rotas, consulta/operador/administrador em
cerca de 60 rotas, tela escondendo botões, edição da matriz (valor ruim, campo ausente, nível desativado, mover nível),
acolhimento pela marca, funcionário desativado com sessão aberta, rota sem regra.

### Fase 2 — Trilha de auditoria (entregue em 2026-10-15)

**Para quê.** Responder, depois do fato, "quem abriu, alterou, baixou ou apagou isto, e quando?". É o que a ANPD espera para
investigar um incidente e o que dissuade o curioso. Decisão do usuário: **registrar tudo**, inclusive toda abertura de ficha, e
**ver os registros dentro do sistema**, com um botão que só o administrador enxerga.

**O que foi feito** (`auditoria.py`, tabela `eventos_auditoria`, tela **Cadastros > Auditoria**, permissão fixa `auditoria`):

- **Entradas**: entrou, senha errada (de usuário que existe), usuário que não existe, bloqueio depois de 5 erros, tentativa durante o
  bloqueio, entrada recusada por funcionário desativado, saiu, sessão derrubada.
- **Leituras**: abrir a ficha, o formulário de edição, o acolhimento social e um formulário já preenchido com um acolhido; carregar
  as listas; buscar pessoa; ver, imprimir (`?imprimir=1`) e baixar cada documento; ver e baixar relatórios; lixeira; cadastro de
  funcionário, lista de funcionários, níveis, permissões, backup; e a própria trilha (ver e exportar).
- **Alterações** (só quando **deu certo**; formulário recusado não vira "alterou"): triagem e prontuário (criou, ou editou e **quais
  campos**), situação, baixa, envelope, parcelas, unificação, excluir, restaurar e apagar de vez, acolhimento (rascunho, finalizar,
  adendo) e "Ciente" de aviso.
- **Administração**: funcionário criado e editado (quais campos), usuário criado, senha redefinida pelo administrador, senha trocada
  pela própria pessoa, níveis, **permissões (de qual nível para qual)** e convênios.
- **Acessos negados**: cada 403, com a permissão que faltou.
- Cada linha leva **quando, o login, o código da ação, o acolhido e/ou o objeto, o endereço de rede e o navegador**.

**O que NÃO é guardado**: o conteúdo. Só *qual* campo mudou, nunca o valor; não vai o que foi digitado numa busca, nem o usuário
digitado num login que não existe (pode ser uma senha no campo errado), nem senha, nem o valor de uma parcela, nem a chave do
"Ciente" (pode ter CPF). O nome do acolhido aparece na tela porque vem do cadastro, não da trilha: se o registro for apagado do
banco, fica "apagado do banco" e o número do cadastro. **O Início não é registrado** (é um resumo; o que ele leva a abrir é registrado
quando abre).

**Regras de construção.** Só se acrescenta: nenhuma tela edita nem apaga evento. Gravar a trilha **nunca derruba a tela** (falha vai
para `logs/servidor.log`). **Tudo está classificado**: cada rota está em `LEITURAS`, `EXPLICITAS` ou `NAO_REGISTRA` (com o motivo), e um
teste falha se aparecer rota nova sem classificação (o mesmo espírito do "nega por padrão" da fase 1).

**A tela** (Cadastros > Auditoria, só o administrador): filtros por período, usuário, tipo (entradas, leituras, alterações,
administração, acessos negados) e **acolhido** (parte do nome; acha até quem foi apagado), 50 por página, do mais novo para o mais
velho, com o nome de quem fez (do cadastro de funcionários), o link da ficha e o endereço. **Baixar CSV** (separador `;`, com BOM para o
Excel, sem fórmulas, até 20 mil linhas). Consultar e exportar **ficam registrados**, com os filtros, sem o nome buscado.

**Limites.** Quem controla o computador e o banco consegue mexer na tabela: a trilha protege contra o uso indevido **pelo sistema**,
não contra o dono da máquina (os backups, que levam a tabela, permitem comparar). A retenção (por quanto tempo guardar) é definida na
fase 8; por ora nada é apagado. Leitura que não passa pelo sistema (alguém abrindo o arquivo do banco) não aparece.

**Como conferir.** `teste_auditoria.py` (132 verificações: login, bloqueio, cada leitura, cada alteração, as que **não** podem
registrar, nada sensível no registro, filtros, paginação, CSV, falha de gravação) e `teste_auditoria_pg.py` (Postgres e
`copiar_banco.py`).

### Fase 3 — Contas e sessões (entregue em 2026-10-15)

**Para quê.** A senha é a porta de tudo. Esta fase fecha as formas mais comuns de ela falhar: senha fácil de adivinhar, senha que
ninguém trocou, computador esquecido logado, tentativa em massa de um mesmo computador, senha perdida resolvida na base do
"manda a senha pelo WhatsApp" e administrador sem nada além da senha entre o invasor e a casa inteira.

**O que foi feito**

- **Senhas fáceis de adivinhar são barradas** (`senhas_fracas.py`, sem depender de internet): as mais usadas (inclusive as com o nome
  da casa e do sistema), sequências ("1234567890", "qwerty"), repetições ("aaaa1111"), o nome do usuário, o nome da pessoa e as
  trocas óbvias ("p@ssw0rd123", "S3nha2024"). Segue o NIST SP 800-63B: **bloquear o conhecido em vez de exigir símbolos**, e **sem troca
  periódica**. O mínimo continua 10 caracteres. A mensagem sugere uma frase de várias palavras.
- **Senha provisória**: a que o administrador define para outra pessoa (cadastro novo ou redefinição) vale só para entrar e trocar:
  até a troca, nenhuma outra tela abre (nem os dados) e o menu fica escondido. A do próprio administrador, definida por ele, não é
  provisória.
- **Acesso novo = e-mail obrigatório e confirmado antes de usar** (decidido em 2026-10-16): não se cria um acesso (usuário novo, ou ligar um
  usuário a um funcionário que não tinha) sem informar o e-mail da pessoa, e **o e-mail não se repete entre funcionários** (o sistema diz de
  quem é). No primeiro acesso a pessoa troca a senha e, em seguida, **confirma o e-mail com o código**; só então o sistema abre (até lá só
  abrem a confirmação, a troca de senha e o "Sair"). **Vale só para acessos novos**: quem já tinha acesso entra como antes e vê o aviso
  "Sua conta" até confirmar. A confirmação **não é cobrada** se o envio de e-mail não está configurado ou se o funcionário ficou sem
  e-mail (senão ninguém novo entraria); em emergência o administrador marca no servidor:
  `flask --app app confirmar-email USUARIO` (fica na auditoria como feito pelo terminal).
- **Entrar com o usuário ou com o e-mail**: o campo da entrada (e do "esqueci minha senha") aceita os dois. Só vale como login o e-mail **já
  confirmado** e de **um** funcionário só (se, em banco antigo, dois funcionários tiverem o mesmo e-mail, ele não vale como login: o usuário
  continua valendo). A resposta de erro é a mesma de sempre. O login só por e-mail foi descartado: o primeiro administrador nasce no
  terminal, quem ainda não confirmou ficaria sem entrar e a auditoria usa o nome de usuário.
- **Tempo ocioso** (decidido: sim): **30 minutos** sem uso encerram a sessão; aos 25 abre um aviso com a contagem ("Manter conectado" ou
  "Sair agora"). Digitar, clicar, rolar e tocar contam como uso, em qualquer aba do navegador; **a lista que se atualiza sozinha a cada
  30 segundos não conta** (senão uma lista esquecida aberta seguraria a sessão para sempre). O teto absoluto de 10 horas continua. A
  entrada explica "a sua sessão terminou por falta de uso" e o encerramento fica na auditoria (`sessao.expirada`).
- **Limite por endereço**: mais de 15 senhas ou códigos errados em 10 minutos vindos do mesmo computador bloqueiam as tentativas **dele**
  (até com a senha certa), além dos 5 erros por usuário que já existiam (quem errava trocava de usuário a cada 5).
- **E-mail do funcionário, confirmado**: só o administrador cadastra (Cadastros > Funcionários) e só vale depois de a própria pessoa
  digitar, em **Minha segurança**, o código de 6 dígitos que o sistema mandou para ele (30 minutos, 5 tentativas, no máximo 5 e-mails
  por hora e 1 por minuto). Trocar o e-mail pede a confirmação de novo. A tela mostra o endereço mascarado.
- **"Esqueci minha senha"** (link na entrada): a pessoa informa o usuário; se ele existe, está ativo e tem e-mail confirmado, recebe um
  **link de uso único, que vale 30 minutos**. **A resposta na tela é a mesma exista ou não o usuário**, e o envio é em segundo plano (o
  tempo de resposta também não revela). O link é guardado só como resumo; abrir o link não o gasta (leitores de e-mail abrem links); só
  o envio da senha nova; senha fraca ou código errado não gastam o link. Usar o link **derruba as outras sessões**, avisa por e-mail e
  vai para a auditoria. O endereço do link vem da **configuração**, nunca do cabeçalho Host do pedido (um pedido forjado não faz o
  e-mail apontar para outro site). Limite de 10 pedidos por hora por computador. **Administrador sem o segundo fator não redefine
  pela caixa de e-mail** (recebe só uma explicação): quem invadir a caixa de e-mail não vira administrador.
- **Segundo fator (aplicativo autenticador no celular)**, opcional para todos e **cobrado no quadro de avisos do administrador**.
  Não é um app para criar: é o Google Authenticator, Microsoft Authenticator, Authy ou outro gratuito. Em **Minha segurança > Ativar o
  aplicativo autenticador** o sistema mostra um QR code (e a chave, para quem estiver no próprio celular), a pessoa digita o primeiro
  código para provar que funcionou e recebe **8 códigos de recuperação, mostrados uma única vez** (imprimir e guardar fora do
  computador). É o TOTP da RFC 6238. Depois da senha, a entrada pede o código; **cada código vale uma vez** (repetição é recusada) e 5
  códigos errados bloqueiam o usuário por 10 minutos. O segredo fica **cifrado** no banco (a chave está em `instance/secret.key`,
  fora do banco: um backup do banco sozinho não dá o segundo fator de ninguém); os códigos de recuperação, só como resumo. SMS fica de
  fora de propósito (o NIST deixou de aceitá-lo). Desativar pede a senha e um código; **celular perdido**: o administrador desativa
  no cadastro da pessoa (caixa "Desativar o aplicativo autenticador desta pessoa"), ou no servidor com
  `flask --app app desativar-segundo-fator USUARIO`.
- **Avisos de segurança por e-mail** (para o e-mail confirmado da pessoa): senha trocada ou redefinida, segundo fator ligado ou
  desligado. A mesma estrutura manda ao **e-mail principal da casa** (`financeiro@restauracao.org.br`) o **lembrete da troca do
  pen-drive**, a cópia externa atrasada, os dois pen-drives plugados e o teste de restauração que falta: no máximo **um por dia** por
  assunto (o do teste, um por semana), pela tarefa do backup, sem nunca derrubá-la.
- **Quadro de avisos** ganhou "Sua conta": e-mail ainda não confirmado, segundo fator que o administrador ainda não ligou, poucos
  códigos de recuperação.
- **Minha segurança** (o nome de quem entrou, no topo; no celular, a inicial): e-mail, aplicativo autenticador e a troca de senha.

**Como o e-mail funciona** (`email_envio.py`). A caixa de envio é `sistema@restauracao.org.br` (Hostinger, `smtp.hostinger.com`,
porta 465 com SSL; 587 com STARTTLS também funciona). Configuração em `instance/email.json`, que só o SISTEMA, os administradores do
Windows e quem instalou leem. **A senha dessa caixa é digitada uma única vez, no servidor, e não aparece na tela**:
`implantacao\configurar-email.ps1` (ou `flask --app app configurar-email`), que depois manda um e-mail de teste. **Nunca vai para o
código, o repositório, o chat nem os registros.** O certificado do servidor de e-mail é sempre conferido. O texto dos e-mails (que traz
códigos e links) e a senha **nunca** vão para o registro do servidor. Sem a configuração, o sistema funciona normalmente e as telas
avisam que o envio ainda não foi configurado.

**O que muda para cada pessoa.** Quem já tinha usuário continua entrando como antes (ninguém é forçado a trocar a senha). Quem receber
senha nova do administrador troca no primeiro acesso. A sessão agora termina por falta de uso.

**Limites.** O segundo fator não protege de quem controla o computador do servidor. A sessão é por navegador (o cookie), então vale o
mesmo cuidado com computador compartilhado de sempre. E-mail comum não é canal seguro: por isso o link vale 30 minutos e uma vez, e
o administrador precisa do segundo fator. O token CSRF e a política de conteúdo do navegador ficam para a fase 7.

**Como conferir.** `teste_contas.py` (227 verificações: senhas, provisória, tempo ocioso, limite por endereço, e-mail, "esqueci minha
senha" com todos os casos de recusa, segundo fator com repetição, recuperação e bloqueio, comandos do servidor), `teste_email.py` (63:
servidores SMTP de mentira com SSL, STARTTLS e certificado autoassinado; certificado recusado; senha recusada; servidor travado;
injeção de cabeçalho; nada de segredo no registro), `teste_aviso_email.py` (32: avisos do pen-drive), `teste_migracao_contas.py` e
`teste_contas_pg.py` (banco antigo aberto pelo código novo, no SQLite e no Postgres, e `copiar_banco.py` com banco de origem antigo).
Também foi conferido no navegador (computador e celular), inclusive o aviso de tempo ocioso com os tempos encurtados.

### Fase 4 — HTTPS na rede interna (entregue em 2026-10-16; falta o usuário ligar)

**Por quê.** Hoje a senha e as fichas viajam em texto puro entre o computador de cada pessoa e o servidor. Quem estiver na mesma
rede (Wi-Fi compartilhado, um visitante, um aparelho infectado) consegue ler com ferramentas gratuitas.

**Decisão (2026-10-15).** O usuário quer acesso pelo **celular** e por **qualquer navegador** (Chrome, Edge, Firefox, Safari), e o segundo
polo vai precisar de VPN de qualquer jeito (fase 10). Logo: **Tailscale** (VPN gratuita) com o certificado público que ele mesmo emite. Os
navegadores e celulares aceitam sem instalar nada, o que uma autoridade certificadora local (Caddy, `tls internal`) não daria (certificado
instalado à mão em cada computador e celular, e o Firefox com configuração própria).

**Como funciona** (`implantacao/configurar-https.ps1`, `servidor.py`, `instance/rede.json`):

- O **Tailscale Serve** do próprio servidor entrega `https://servidor.tailXXXX.ts.net` (porta 443, só dentro da rede do Tailscale) e repassa
  para o sistema em `127.0.0.1:8000`. O certificado é emitido e **renovado pelo Tailscale**: nada de arquivo de certificado nem de tarefa de
  renovação. Nenhuma porta é aberta no roteador.
- Três **modos de rede**, em `instance/rede.json` (o script grava):
  - `http` (o de sempre, padrão): aberto na rede local, sem HTTPS;
  - `misto` (**transição**): igual ao `http` **e** atende o HTTPS do Tailscale. Dá para migrar um computador de cada vez, sem ninguém
    perder o acesso;
  - `https` (**final**, `-FecharHttp`): o sistema escuta só em `127.0.0.1`, o cookie do login volta a ser **só-HTTPS** (`SESSAO_SEM_HTTPS`
    sai), o navegador recebe **HSTS** (1 ano) e a regra do firewall da porta é removida.
- **Quem acessa continua identificado.** Atrás de um proxy todo acesso chegaria como `127.0.0.1`; o waitress passa a confiar nos cabeçalhos
  `X-Forwarded-For` e `X-Forwarded-Proto` **só de quem vem de 127.0.0.1** (o Tailscale Serve) e apaga esses cabeçalhos de qualquer outra origem,
  então ninguém na rede local consegue se passar por outro endereço. Assim a auditoria e o limite de tentativas continuam vendo o **aparelho**
  de cada acesso (`100.x.x.x`). Se o proxy não repassar o endereço, o sistema não limita o endereço local (para um erro de um não bloquear todos);
  continuam valendo os 5 erros por usuário. **Conferir na prática** (passo 5 do LEIA-ME, parte 5): Cadastros > Auditoria deve mostrar `100.x.x.x`.
- O script confere o Tailscale (conectado, MagicDNS, HTTPS ligado no painel), liga o modo "Run unattended" (o Tailscale volta sozinho depois de
  reiniciar o Windows, sem ninguém logado), grava o modo, religa o sistema, **troca o endereço dos links dos e-mails** (`flask --app app
  endereco-do-sistema`, para o "esqueci minha senha" apontar para o endereço novo) e **testa o endereço https** a partir do servidor
  **antes** de fechar o http. `-Desfazer` volta tudo ao http da rede local.
- A página inicial mostra "Segurança da rede" enquanto o modo for `http` ou `misto` (só no servidor do escritório).

**O que o usuário precisa fazer** (LEIA-ME, parte 5): criar a conta do Tailscale (com verificação em duas etapas), instalar nos aparelhos,
ligar o *HTTPS Certificates* no painel, rodar `configurar-https.ps1` no servidor, migrar os computadores e celulares e, no fim,
`-FecharHttp`.

**Limites e cuidados**

- **Os nomes ficam públicos**: o nome do computador e da rede (`tailXXXX.ts.net`) aparecem nos registros públicos de certificados. Usar nomes
  neutros; nada com nome de paciente.
- **A conta do Tailscale é a chave da rede**: verificação em duas etapas nela; remover do painel qualquer aparelho perdido.
- O plano gratuito é **para uso não comercial**: confirmar que a casa se enquadra (há desconto para entidades sem fins lucrativos).
- Depois de `-FecharHttp`, **quem não tem o Tailscale não abre mais o sistema**. No próprio servidor, `http://127.0.0.1:8000` abre sempre.
- Se o Tailscale ou a internet cair, o acesso pelos outros aparelhos pode cair (a rede costuma lembrar dos aparelhos conhecidos, mas não é
  garantido): por isso o modo `misto` existe e o `-Desfazer` está sempre à mão.
- **Manter os dois acessos é uma escolha válida** (`configurar-https.ps1 -ManterOsDois`, modo `misto` com `"manter_http": true`; o lembrete da
  página inicial some). O custo: a senha e o cookie de quem entra pelo http seguem sem criptografia na rede do escritório. Mitigações: Wi-Fi
  forte e visitantes separados, administrador e tarefas sensíveis pelo endereço https, e o segundo fator do administrador (fase 10), que
  impede que uma senha espiada na rede abra a conta dele.
- O HSTS faz o navegador exigir HTTPS naquele nome por 1 ano; por isso ele só vai no modo `https` (ou em hospedagem com HTTPS).
- **Não testado com o Tailscale de verdade nesta entrega** (não há conta nem o programa instalado neste computador de desenvolvimento): o
  script e o sistema foram testados com um Tailscale de mentira e com o waitress real; a primeira execução no servidor é o teste final, e o modo
  `misto` existe para ela ser segura.

**Como conferir.** `teste_rede.py` (47 verificações: leitura do modo, o que cada modo liga, o waitress real confiando só no proxy local e
recusando cabeçalhos forjados, o sistema de verdade subindo em cada modo com cookie e HSTS, o limite de tentativas, o comando do endereço dos
e-mails e o lembrete na página inicial) e o script contra um `tailscale.cmd` de mentira (conectado, sem login, sem HTTPS, sem nome).

### Fase 5 — Backup que sobrevive ao computador (entregue em 2026-10-15)

**Antes.** `backup.py` fazia uma cópia consistente do banco todo dia às 18:30 e guardava as últimas 30 no computador (ou num HD
sempre ligado), sem criptografia. Disco queimado, roubo ou vírus levavam o banco e as cópias juntos.

**Por que dois pen-drives, e não um.** Um só fica plugado e cai junto (vírus, roubo, incêndio); pen-drive barato falha sem
avisar; e, enquanto grava, ele é a única cópia fora do computador. Por isso **dois em rodízio**: um plugado no servidor, o outro
**guardado trancado**, trocados toda semana. O usuário decidiu guardar o segundo **na gaveta trancada do escritório** (2026-10-15):
isso protege de vírus, de erro e de pen-drive que estraga, mas **não de incêndio, alagamento ou roubo do escritório inteiro**
(fica registrado como risco aceito; levar o pen-drive guardado para casa uma vez por mês fecha essa lacuna).

**O que foi feito** (`copia_externa.py`, `backup.py`, `implantacao/configurar-backup-externo.ps1`):

- A cópia vai **criptografada** (AES-256-GCM, chave tirada de uma frase de recuperação pelo scrypt) e comprimida; trocar um byte
  ou errar a frase é detectado. Quem achar o pen-drive não lê nada.
- A **frase de recuperação** (24 letras e números sem ambiguidade) é gerada uma vez, aparece uma vez na tela para ser anotada **em
  papel** e fica guardada no servidor (`instance/backup_chave.txt`, acesso só do SISTEMA e dos administradores) para a tarefa
  automática poder criptografar. Para restaurar em outro computador basta o arquivo e a frase do papel; o sistema novo guarda a
  mesma frase com `-FraseExistente`, conferindo que ela abre uma cópia do rodízio.
- **Conferida na hora**: depois de gravar, o arquivo é aberto de novo, descriptografado e o banco de dentro é conferido
  (integridade e número de registros). Cópia que não abre é apagada do pen-drive.
- **Rodízio reconhecido pelo sistema**: cada pen-drive é *preparado* uma vez (pastinha `prontuario-backup` com um código próprio) e
  é reconhecido em qualquer porta ou letra. A cópia externa nunca vai para o disco do próprio computador. O sistema anota desde
  quando cada um está plugado.
- **Histórico**: em cada pen-drive ficam as cópias dos últimos 14 dias, uma por semana nas 8 semanas seguintes e uma por mês até
  1 ano.
- **Lembrete da troca (pop-up)**: na sexta (com o pen-drive plugado há 4 dias ou mais) e, se a troca ficou para trás, em qualquer dia a
  partir do 7º, a página inicial abre um pop-up "Hora de trocar o pen-drive do backup", uma vez por dia em cada computador até a troca
  ser feita; na sexta de manhã manda esperar até as 18:45. A versão por **e-mail** (fase 3) sai pela tarefa do backup, uma vez por dia, para o e-mail principal.
- **Tarefas**: o backup das 18:30 leva a cópia externa junto; a tarefa *Prontuario - copia externa* roda de hora em hora das 8h às
  20h e cobre o pen-drive plugado depois. **Falha da cópia externa nunca cancela o backup do dia nem a atualização.**
- **Avisos na página inicial** (no servidor do escritório): cópia externa não configurada; nenhum pen-drive preparado; mais de 3
  dias sem cópia ("o pen-drive está plugado?"); mesmo pen-drive plugado há 7 dias ou mais ("leve o A para fora e plugue o B");
  os dois plugados ao mesmo tempo; teste de restauração por fazer (depois de 7 dias) e a cada ~100 dias.
- **Cadastros > Backup** (só administrador): cada pen-drive, desde quando está plugado, última cópia, backup do dia, teste de
  restauração e pendências.
- **Teste de restauração** (`backup.py --testar-restauracao`): abre a cópia mais nova com a frase **digitada do papel**, o que
  prova que o papel está certo e que o backup serve, e anota a data. **Restaurar** (`--restaurar ARQ.pbk --para NOVO.db`) só
  grava se o banco de dentro estiver íntegro. O passo a passo para imprimir está em `implantacao/RESTAURAR.md`.

**Limites** (por isso as outras fases): quem ganhar acesso de administrador no servidor lê a frase guardada nele (a criptografia
protege o pen-drive perdido ou roubado, não o servidor invadido); o backup do dia (`.db`) continua sem criptografia no
computador ou no HD fixo; e depende de uma pessoa trocar o pen-drive toda semana (o sistema avisa, mas não troca sozinho).

**Como conferir.** `teste_copia_externa.py` (118 verificações: ida e volta byte a byte, byte trocado em cada parte, frase errada,
arquivo cortado, banco grande, pen-drive clonado, disco cheio, cópia que não abre, retenção, rodízio, avisos, comandos
interativos) e `teste_backup_externo_app.py` (25: página inicial e tela de backup).

### Fase 6 — Servidor Windows, rede e roteador (entregue em 2026-10-16; o usuário faz o que é físico)

Quase tudo aqui é físico (o roteador, a sala, a impressora, a senha do Windows): **só uma pessoa na casa pode fazer**. O que o sistema pôde fazer
foi tornar isso **uma lista curta, com o motivo de cada item**, e **conferir sozinho o que dá para conferir**.

- **`implantacao/ROTEIRO-DO-WINDOWS-E-DA-REDE.md`**: o passo a passo, em português, com caixas para marcar: disco criptografado (e a chave de
  recuperação em papel), atualizações do Windows, antivírus, uma conta de administrador e outra comum, senha em todas as contas, sem entrada
  automática, bloqueio de tela, área de trabalho remota e compartilhamento desligados, sala trancada; no roteador, senha do painel trocada, Wi-Fi
  WPA2/WPA3 com senha forte, **rede de visitantes separada**, UPnP e encaminhamento de portas desligados, administração remota desligada,
  firmware em dia, reserva de IP; impressão (impressora onde só a equipe passa, nada na bandeja, papel picotado); e a rotina trimestral.
- **`implantacao/verificar-servidor.ps1`** (só lê, não muda nada; Administrador): confere disco criptografado, espaço em disco, atualizações,
  antivírus, firewall, tipo de rede, **portas abertas para a rede** (RDP, telnet, FTP, WinRM, VNC, compartilhamento de arquivos), área de
  trabalho remota, SMB1, contas sem senha, administradores, entrada automática, bloqueio de tela, relógio (os códigos do autenticador
  dependem dele), permissões da pasta `instance`, tarefas do sistema, backup do dia e o modo de rede do sistema. Cada item sai **OK**,
  **ATENCAO** ou **VERIFICAR**, com o que fazer. O resultado vai para `instance/verificacao_servidor.json` e a **página inicial avisa o
  administrador** se achou algo para corrigir ou se passou de 100 dias sem rodar. (Testado de verdade num Windows 11: o script roda, e o
  sistema lê o JSON que ele grava.)
- **Serviço com conta limitada no lugar de SISTEMA: NÃO foi automatizado, de propósito.** Trocar a conta mexe em permissões de pasta, em direitos
  de logon e nas tarefas agendadas; um erro derruba o sistema ou o backup e isso não se testa sem o computador do escritório. O que ele evitaria
  já está coberto por outras camadas (pasta `instance` fechada, sistema só em `127.0.0.1` no modo `https`, firewall, CSRF e política de conteúdo).
  O roteiro explica como fazer **junto**, com backup recém-feito e janela de manutenção, se a casa quiser.

### Fase 7 — Defesa do navegador (entregue em 2026-10-16)

**Por quê.** O que protege o sistema por dentro (senha, nível, auditoria) não ajuda se uma página de outro site conseguir fazer o navegador
de quem está logado mandar um comando (**CSRF**), ou se alguém conseguir pôr um `<script>` numa página do sistema (**XSS**). Esta fase fecha
as duas portas no navegador.

**O que foi feito** (`csrf.py`, `static/base.js`, os templates):

- **Token CSRF em todo envio que muda coisas** (POST e afins), inclusive a entrada. O token vai na sessão (muda a cada entrada), os 28
  formulários POST levam `<input type="hidden" name="csrf_token">` e as chamadas do JavaScript levam o cabeçalho `X-CSRF-Token` (o
  `base.js` embrulha o `fetch` do próprio sistema, e cobre formulário criado por script). Sem o token, ou com um que não confere: **400**,
  uma tela explicando ("A página venceu"; JSON nas chamadas do JavaScript), comparação em tempo constante e registro na auditoria
  (`csrf.recusado`: só o método e a rota, nunca o que foi digitado). Não conta como senha errada. Token na linha do endereço não vale.
- **Política de conteúdo (CSP)** em toda página: script e estilo só do próprio sistema ou **com o nonce da resposta** (um código novo a cada
  página, que o servidor põe nas próprias tags). Quem conseguir injetar um `<script>` na página não leva nada para rodar (testado no
  Chrome: um script inserido à força é barrado e o relatório chega ao registro do servidor). `connect-src` só o próprio sistema e o ViaCEP
  (o preenchimento do endereço pelo CEP); `form-action 'self'`, `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'self'`. Sem
  `unsafe-inline` nem `unsafe-eval` em script e em bloco de estilo (só `style="..."` dentro das tags continua permitido).
  Em vez de tirar todos os scripts e estilos de dentro das páginas (a ideia original), usamos o **nonce**, que dá a mesma proteção sem
  reescrever as telas. Os atributos de evento (`onclick`, `onsubmit`, `onchange`) foram trocados por `data-confirmar`,
  `data-imprimir` e `data-trocar-emissor`, tratados pelo `base.js`.
- **Relatório da política**: o navegador avisa `/csp-relatorio` quando barra algo, e o sistema escreve **uma linha curta** em `logs\servidor.log`
  (o que foi barrado e em qual página, sem consulta nem conteúdo; no máximo 20 por minuto). **Modo de emergência**: se uma tela deixar de
  funcionar por causa da política, `CSP_SOMENTE_RELATORIO=1` põe a política em "só avisar" (o navegador não bloqueia, só relata) até se
  achar a causa.
- **Cabeçalhos extras**: `Permissions-Policy` (sem câmera, microfone, localização, pagamento, USB), `Cross-Origin-Opener-Policy` e
  `Cross-Origin-Resource-Policy` iguais a `same-origin`. Os downloads (Word e CSV) já saem com `Content-Disposition: attachment`.

**Para quem mexe no sistema** (`docs/padroes-de-interface.md`): formulário POST novo leva `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`;
`<script>` ou `<style>` dentro da página leva `nonce="{{ csp_nonce() }}"`; nada de `onclick=` (use `data-*` e o `base.js`); chamada nova do
JavaScript usa o `fetch` normal (o `base.js` põe o cabeçalho).

**Limites.** O CSRF não protege de quem já controla o navegador da pessoa (extensão maliciosa, computador infectado). `style="..."` dentro
das tags segue permitido (só estilo, sem código). O ViaCEP recebe o CEP digitado (dado de endereço, fora do sistema): se a casa não quiser
isso, basta tirar o `viacep.com.br` de `connect-src` em `csrf.py` e o preenchimento automático deixa de funcionar.

**Como conferir.** `teste_csrf.py` (53 verificações, com o CSRF ligado: token na página e em todo formulário, recusa de TODA rota POST sem
token em HTML e em JSON, token errado/no endereço/de sessão antiga, a política com nonce em todas as tags, sem atributo de evento, o relatório,
a confirmação do nome com aspas), os testes de servidor real (`teste_servidor.py`, `teste_rede.py`) e a conferência no Chrome em todas as
telas, sem uma só violação, com envio de formulário, confirmações, impressão, troca de quem assina e chamadas do JavaScript.

### Fase 8 — LGPD no papel

Modelos prontos em `docs/lgpd/`, para a casa preencher e assinar:

- **Inventário de dados**: o quê, para quê, base legal (tutela da saúde, obrigação legal, consentimento do responsável quando
  for o caso), quem acessa, onde fica, por quanto tempo.
- **Política de retenção**: por quanto tempo guardar prontuário de ex-interno e quanto tempo um registro fica na lixeira antes
  de ser apagado de vez. Alinhar com as exigências do conselho profissional e da vigilância sanitária.
- ~~**Termo de sigilo** assinado por quem recebe um login.~~ **Dispensado por decisão da casa (2026-10-16)**: os computadores que acessam o
  sistema são patrimônio da instituição, e o que importa é proteger os dados e dar logins seguros (fases 1 a 5, 7 e 10). Se um dia a casa
  quiser, é só um papel: o sistema não depende dele.
- **Plano de resposta a incidente**: quem avisa quem, em quanto tempo; a comunicação à ANPD e ao titular tem prazo (conferir a
  Resolução CD/ANPD nº 15/2024). Inclui o que fazer se um computador for roubado ou um pen-drive de backup for perdido.
- **Canal do titular** (art. 18): como a pessoa pede acesso, correção ou eliminação.
- A associação provavelmente se enquadra como agente de tratamento de **pequeno porte** (Resolução CD/ANPD nº 2/2022), com
  obrigações simplificadas, mas ainda precisa de canal de atendimento e das medidas acima. Confirmar com a contabilidade ou o jurídico.

### Fase 9 — Manutenção contínua (entregue em 2026-10-16)

O que se esquece com o tempo, o sistema lembra (`manutencao.py`; os avisos só aparecem **para o administrador** e **no servidor do escritório**,
na categoria "Manutenção" do quadro da página inicial):

- **Auditoria das bibliotecas** (`implantacao/auditar-dependencias.ps1 -Agendar`, uma vez): roda o **pip-audit** (a lista pública de
  vulnerabilidades de bibliotecas Python) sobre as bibliotecas que o sistema usa de verdade e **agenda uma por mês** (a cada 4 semanas, como
  SISTEMA). O pip-audit mora num ambiente separado (`.venv-auditoria`) para não misturar as bibliotecas dele com as do sistema. O aviso diz o
  pacote, a versão e a versão que corrige; avisa também se a auditoria falhou (sem internet) ou se parou de rodar (mais de 45 dias). pip,
  setuptools e wheel (ferramentas de instalação) não viram aviso, e o script atualiza o pip. Precisa de internet. (Testado de verdade: o pip-audit
  rodou sobre as bibliotecas do ambiente de teste e o sistema leu o JSON que ele produz.)
- **Revisão trimestral dos acessos** (**Cadastros > Revisão**, só o administrador): cada login com o funcionário, o nível, a última entrada e os
  **pontos de atenção** (login sem funcionário, funcionário desativado, nunca entrou, não entra há mais de 90 dias, administrador sem o
  autenticador, e-mail sem confirmar, senha provisória que ninguém trocou; e os funcionários ativos sem login). Botão **"Marcar como
  revisada"** (fica na auditoria) e o aviso volta em 90 dias.
- **Revisão semestral do plano de segurança**: o mesmo botão, a cada 180 dias.
- **Verificação do servidor** (fase 6): aviso se achou algo ou se passou de 100 dias.
- **Teste de restauração do backup** trimestral: já cobrado pela cópia externa (fase 5), no mesmo quadro de avisos.

**Como conferir.** `teste_manutencao.py` (47+ verificações: o resultado do pip-audit, avisos em cada estado, a situação de cada login, a tela e os
botões, só o administrador) e a execução real dos dois scripts.

### Fase 10 — Segundo polo e acesso de fora do escritório (entregue em 2026-10-16; falta o usuário ligar)

**Pergunta de origem (2026-10-15).** Hoje o sistema só abre quando o computador está no Wi-Fi do escritório. Dá para instalar
um servidor em outro polo e os dois usarem o mesmo banco?

**Por que não dois servidores com o SQLite.** O SQLite é um arquivo, feito para um computador só; dois servidores abrindo o mesmo
arquivo pela rede podem corrompê-lo. Manter um banco por polo e sincronizar traz conflitos (a mesma pessoa cadastrada nos dois
lados, numeração repetida, internet que cai no meio) e não é recomendado.

**Decisão (2026-10-15): opção A, um banco só.** Os polos compartilham **exatamente as mesmas informações**, como se o sistema estivesse na
nuvem, e o polo 2 tem computadores e internet. Logo: um sistema, um banco, um endereço (o do computador do escritório no Tailscale) para os
dois polos e para o celular. Sem campo "polo" e sem sincronização. Com a fase 4 pronta, ligar o polo 2 é **instalar o Tailscale lá** (LEIA-ME,
parte 5), e esta fase entrega o que faltava para isso ser seguro:

- **Segundo fator obrigatório para o administrador** quando o sistema pode ser acessado de fora (modos `misto` e `https`, `servidor.py`). O
  administrador sem o aplicativo autenticador só consegue abrir a tela de ativação (`Ligue o aplicativo autenticador`), com os dados fechados
  até lá. No modo `http` (só o escritório) não exige. Dá para desligar (`"segundo_fator_do_administrador": false` em `instance/rede.json`, ou a
  variável `EXIGIR_SEGUNDO_FATOR=0`) para quem não tem celular. Celular perdido: `flask --app app desativar-segundo-fator USUARIO`, e ele liga de novo.
- **Aviso de aparelho novo**: quando alguém entra por um endereço de rede (cada aparelho do Tailscale tem o seu `100.x`) que nunca usou, e já
  tinha entrado antes, recebe um e-mail ("Entrada por um aparelho novo", com o endereço e o que fazer se não foi ela); se for administrador,
  o e-mail principal da casa também. Fica na auditoria (`login.aparelho_novo`). A primeira entrada de uma conta e as do próprio servidor
  (127.0.0.1) não avisam; o e-mail que falha nunca atrapalha a entrada.
- **Política de acesso do Tailscale** (`implantacao/tailscale-politica.json`, mostrada já preenchida por
  `configurar-https.ps1 -MostrarPolitica`): cada aparelho só alcança o servidor, só na porta 443. Sem isso, um computador infectado do polo 2
  alcançaria os computadores do escritório (por padrão todo aparelho da rede alcança todos os outros).
- **Cada pessoa do polo 2 com a própria conta** do Tailscale (convite por usuário; até 6 no plano gratuito), nunca a conta da casa compartilhada.
- **Roteiro de liberação e do dia a dia** no LEIA-ME, parte 5: antes de liberar, durante e quando alguém sai ou perde um aparelho.

**Pré-requisitos** (todos entregues): HTTPS (fase 4), segundo fator do administrador e tempo ocioso (fase 3), trilha de auditoria com o
endereço de cada acesso (fase 2), backup externo (fase 5). O **termo de sigilo** foi dispensado por decisão da casa (2026-10-16): os computadores
que acessam o sistema são todos patrimônio da instituição, e a proteção está nos logins e nos dados.

**Limites.** O computador do escritório é o ponto único: se ele ou a internet de lá cair, o polo 2 para (o backup externo mostra o que fazer
para recomeçar em outro computador, `implantacao/RESTAURAR.md`). O aviso de aparelho novo depende de o Tailscale repassar o endereço de quem
acessa (conferir na auditoria, LEIA-ME parte 5, passo 5). Se a casa um dia precisar que o polo 2 funcione com o escritório fora do ar, a
opção B (Postgres central) continua disponível: o sistema já suporta (`DATABASE_URL`, `copiar_banco.py`).

**Como conferir.** `teste_polo2.py` (51 verificações: quando a exigência vale, o administrador barrado e liberado, quem não deve ser barrado,
o aviso de aparelho novo em cada situação e a política do Tailscale).

## 5. O que só uma pessoa na casa pode fazer

| Quando | Tarefa |
|---|---|
| Agora | Revisar a grade de **Cadastros > Permissões** e ajustar o que cada nível pode; conferir que cada pessoa está no nível certo |
| Agora | Conferir se algum login ainda é compartilhado ("escritório", "recepção"). Um usuário por pessoa |
| Agora | Desativar o funcionário de quem saiu da casa (o login deixa de entrar na hora) |
| Fase 5 | Comprar **2 pen-drives** (marca conhecida, 32 GB bastam), rodar `configurar-backup-externo.ps1`, **anotar a frase em papel e guardar fora do computador**, preparar cada pen-drive e combinar quem troca na sexta (o pen-drive que sai do computador vai para a gaveta trancada) |
| Fase 5 | A cada 3 meses, fazer o teste de restauração (2 minutos, `implantacao/RESTAURAR.md`) |
| Fase 6 | Percorrer `implantacao\ROTEIRO-DO-WINDOWS-E-DA-REDE.md` (disco criptografado, contas, roteador, rede de visitantes...) e rodar `implantacao\verificar-servidor.ps1` a cada 3 meses |
| Fase 9 | Rodar `implantacao\auditar-dependencias.ps1 -Agendar` uma vez (agenda a auditoria mensal das bibliotecas) e, a cada 3 meses, fazer a **Cadastros > Revisão** de acessos |
| Fase 3 | Rodar `implantacao\configurar-email.ps1` no servidor e **digitar a senha da caixa `sistema@`** (e trocá-la, se já apareceu em conversa); cadastrar o **e-mail de cada funcionário** (Cadastros > Funcionários); cada pessoa confirma o seu em **Minha segurança**; o administrador **liga o aplicativo autenticador** no celular e guarda os 8 códigos de recuperação em papel |
| Fase 4 | Criar a conta do Tailscale (com verificação em duas etapas), instalar nos aparelhos, ligar o HTTPS no painel, rodar `configurar-https.ps1` no servidor, migrar os aparelhos e, no fim, `-FecharHttp` (LEIA-ME, parte 5) |
| Fase 10 | Convidar cada pessoa do polo 2 no Tailscale (conta própria), colar a política de acesso (`configurar-https.ps1 -MostrarPolitica`), instalar nos aparelhos do polo (LEIA-ME, parte 5) |
| Fase 8 | Preencher e assinar os modelos |

## 6. Decisões e perguntas

**Respondidas em 2026-10-15**

1. Os polos compartilham exatamente as mesmas informações (fase 10, opção A, sem campo "polo"); o polo 2 tem computadores e internet.
2. Celular e todos os navegadores: o HTTPS usa o certificado da VPN (fase 4). A VPN terá **3 aparelhos**: 2 computadores (um por
   polo) e 1 celular móvel; cabe no plano gratuito (conferir os limites atuais na hora).
3. Grade de fábrica: unificar e cadastros só do administrador; parcelas ficam com o operador. Níveis: Administrador, Operador e
   Consulta; o administrador reorganiza na tela quando precisar.
4. Auditoria: registrar tudo, com tela dentro do sistema que só o administrador vê (fase 2, entregue).
5. Tempo ocioso: sim (fase 3). Validação de e-mail, "esqueci minha senha" e bloqueio após 5 erros: sim (fase 3; o bloqueio já existe).
6. O pen-drive que sai do computador fica **na gaveta trancada do escritório** (risco aceito: não protege de incêndio nem de roubo do
   escritório inteiro).
7. O e-mail institucional é da **Hostinger** (envio por SMTP com senha: mais simples que o Microsoft 365).
8. Caixa de envio `sistema@restauracao.org.br`; e-mail principal, que recebe os avisos do sistema, `financeiro@restauracao.org.br`.
9. Segundo fator (aplicativo autenticador no celular): sim, para o administrador; vale para quem quiser. Passa a ser necessário para o administrador redefinir a senha pelo e-mail.
10. Termo de sigilo: dispensado (2026-10-16). Os computadores que acessam o sistema são todos patrimônio da instituição; o foco é proteger os
    dados e criar logins seguros.

**Em aberto**

_(nada em aberto desta fase)_

## 7. Referências

- Lei nº 13.709/2018 (LGPD), arts. 5º, 6º (VII e VIII), 11, 18, 46 a 49.
- ANPD, *Guia orientativo de segurança da informação para agentes de tratamento de pequeno porte* (2021) — medidas
  administrativas e técnicas, em linguagem simples. Resolução CD/ANPD nº 2/2022 (agentes de pequeno porte) e nº 15/2024
  (comunicação de incidente de segurança).
- OWASP ASVS, capítulo de controle de acesso (V4): nega por padrão, menor privilégio, regra aplicada no servidor e num ponto
  central, falhar fechado, registrar decisões de autorização.
- NIST SP 800-63B (autenticação): lista de senhas conhecidas bloqueada, sem regras de composição, sem troca periódica, segundo fator
  por aplicativo (TOTP) em vez de SMS.
- Mozilla, *Enterprise policies* — `ImportEnterpriseRoots` (Firefox usar o repositório de certificados do Windows). Microsoft,
  *Device encryption in Windows* (Windows 11 Home). Caddy, *Automatic HTTPS* — `tls internal` (autoridade certificadora local).
