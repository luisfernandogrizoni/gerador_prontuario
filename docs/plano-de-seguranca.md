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
| Entrada | Login obrigatório em toda rota; senha só como hash (scrypt); 5 erros bloqueiam o usuário por 10 min; mensagem igual para usuário inexistente e senha errada; sessão de 10 h que não renova; trocar a senha derruba as outras sessões | Sem lista de senhas fracas; senha provisória não precisa ser trocada; sem tempo ocioso; sem limite por IP; sem segundo fator |
| Quem pode o quê | **Fase 1 (esta entrega)**: cascata de níveis com permissões configuráveis, nega por padrão, funcionário desativado perde o acesso | Quem tem "ver" vê todas as fichas; não há registro de quem viu o quê |
| Rastro | **Fase 2**: trilha de auditoria com tela só do administrador (entradas, leituras, alterações, administração e acessos negados); mais o registro técnico do servidor | Quem controla o computador e o banco consegue mexer na tabela (a trilha não protege do dono da máquina); sem política de retenção ainda (fase 8) |
| Rede | Porta aberta só para a sub-rede local (firewall); sem acesso externo | **HTTP sem criptografia**: senha e ficha trafegam em texto puro pela rede interna |
| Navegador | Cookie HttpOnly e SameSite=Lax; nosniff; X-Frame-Options; sem cache das páginas | Sem token CSRF; sem CSP |
| Dados | Excluir é em duas etapas (lixeira); banco fora do git; hook que barra dado real no repositório; **fase 5**: cópia externa criptografada em pen-drives em rodízio, conferida na hora, com aviso, tela de situação e teste de restauração | Depende de alguém trocar o pen-drive toda semana (o sistema avisa) e de a frase de recuperação estar em papel; o backup do dia (`.db`) segue sem criptografia no computador |
| Servidor | Tarefas agendadas, firewall, pasta `instance/` protegida | Roda como SYSTEM; disco sem criptografia (a verificar); roteador e Windows sem checklist |
| Papel | — | Sem inventário de dados, política de retenção, termo de sigilo nem plano de resposta a incidente |

## 3. Ameaças que o plano cobre (da mais provável para a menos)

| # | Ameaça | Exemplo na casa | Medida | Fase |
|---|---|---|---|---|
| 1 | **Perder tudo** | O disco do computador queima, ransomware, o computador é roubado, alguém apaga a pasta | Backup criptografado fora do computador, com rodízio e teste de restauração | 5 |
| 2 | **Quem tem login vê ou faz o que não devia** | Funcionário curioso, estagiário com acesso total, ex-funcionário que ainda entra | Cascata de acesso, bloqueio de desativado, trilha de auditoria | **1**, 2 |
| 3 | **Senha fraca, repetida, compartilhada ou anotada** | "Todo mundo usa o login do escritório" | Um usuário por pessoa, lista de senhas fracas, troca da provisória, segundo fator para administrador | 3 |
| 4 | **Alguém escuta a rede** | Wi-Fi do escritório com senha conhecida por muita gente; visitante conectado | HTTPS na rede interna, Wi-Fi separado para visitante | 4, 6 |
| 5 | **Acesso físico ao computador servidor** | Roubo, pessoa de passagem mexendo na máquina | Disco criptografado, bloqueio de tela, sala fechada | 6 |
| 6 | **Ataque pelo navegador** | Link malicioso faz o navegador de um funcionário logado executar uma ação | Token CSRF, CSP | 7 |
| 7 | **Dado que sai do sistema** | Prontuário baixado em pen-drive e esquecido; impressão deixada na impressora | Permissão própria para documentos, trilha de quem baixou, termo de sigilo | **1**, 2, 8 |
| 8 | **Sistema exposto na internet sem querer** | Alguém libera uma porta no roteador "para acessar de casa" | Checklist do roteador, firewall só para a rede local | 6 |
| 9 | **Falha em uma biblioteca** | Vulnerabilidade conhecida no Flask, Werkzeug, python-docx | Auditoria mensal das dependências | 9 |

Acesso de fora do escritório (de casa, do celular, de um segundo polo) **muda o risco todo** e por isso não vale sem a
fase 10 (VPN), nunca abrindo porta no roteador.

## 4. As fases

| Fase | O que entrega | Quem faz | Situação |
|---|---|---|---|
| 1 | Cascata de acesso por nível | Sistema | **Feita** (nesta entrega) |
| 2 | Trilha de auditoria (com tela dentro do sistema, só administrador) | Sistema | **Feita** (2026-10-15) |
| 3 | Contas e sessões mais fortes: tempo ocioso, e-mail validado, "esqueci minha senha" e segundo fator do administrador | Sistema + usuário (e-mail institucional e celular com app autenticador) | A fazer; **depende de saber qual serviço de e-mail a casa usa** |
| 4 | HTTPS (celular e todos os navegadores) | Sistema + usuário (instalar a VPN) | A fazer; decidido usar o certificado da VPN |
| 5 | Backup que sobrevive ao computador | Sistema + usuário (pen-drives e rotina) | **Feita** (2026-10-15); falta o usuário configurar |
| 6 | Servidor Windows, rede e roteador | Quase tudo o usuário (roteiro passo a passo) | A fazer |
| 7 | Token CSRF e CSP | Sistema | A fazer |
| 8 | LGPD no papel | Usuário, com modelos prontos do sistema | A fazer |
| 9 | Manutenção contínua | Sistema (avisos) + usuário | A fazer |
| 10 | Segundo polo e acesso de fora do escritório (VPN) | Sistema + usuário (instalar a VPN) | A fazer; decidido: mesmo banco, opção A |

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
  e o termo de sigilo da fase 8 completam).
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

### Fase 3 — Contas e sessões

- **Lista de senhas fracas** embutida (sem depender de internet): barra "1234567890", "senha123", o nome do usuário, o nome da
  casa. Segue a orientação do NIST SP 800-63B de **bloquear senhas conhecidas em vez de exigir símbolos**, e de **não exigir
  troca periódica** (só quando houver suspeita). O mínimo atual (10 caracteres) pode subir; conferir os números da revisão 4 do
  guia antes de fixar.
- **Senha provisória**: a que o administrador cria vale só para o primeiro acesso; o sistema pede a troca antes de qualquer
  outra tela.
- **Tempo ocioso** (decidido: sim): sai sozinho depois de 30 minutos sem uso (ajustável), com aviso antes. Computador de
  escritório fica desbloqueado quando alguém levanta.
- **Bloqueio por tentativas** (já existe: 5 erros, 10 minutos) **mais** limite por endereço, porque hoje quem erra troca de
  usuário a cada 5 erros.
- **E-mail validado** (decidido: sim, a casa tem e-mails institucionais): cada funcionário tem um e-mail no cadastro, confirmado
  por um código enviado a ele antes de valer. O e-mail serve para o "esqueci minha senha" e para avisos de segurança ("sua senha
  foi trocada", "entrada de um computador novo").
- **"Esqueci minha senha"**: a pessoa informa o usuário e o sistema manda um **link de uso único, que vale 30 minutos**, para o
  e-mail confirmado. A mensagem na tela é a mesma exista ou não o usuário (não revela quem tem cadastro); o link é guardado só
  como resumo (hash) no banco; usar o link derruba as outras sessões. **Administrador não redefine sozinho pelo e-mail: exige
  também o segundo fator**, porque quem invade o e-mail não pode virar administrador. Continua valendo a redefinição pelo
  administrador (Cadastros > Funcionários).
- **Segundo fator opcional (TOTP) para o administrador**. **Não é um aplicativo para criar**: é um app gratuito que já existe
  (Google Authenticator, Microsoft Authenticator, Authy...) e que o administrador instala no celular. O sistema mostra um QR code
  uma vez, o app passa a gerar um número de 6 dígitos que muda a cada 30 segundos, e o sistema pede esse número depois da senha.
  Códigos de recuperação impressos cobrem o celular perdido. SMS fica de fora: o NIST deixou de aceitá-lo.
- Sessão derrubada quando o nível muda.

**O que a parte do e-mail exige**: o servidor precisa **enviar** e-mail. A casa usa a **Hostinger**, que oferece envio por SMTP
com usuário e senha (servidor `smtp.hostinger.com`, porta 465 com SSL ou 587 com STARTTLS; conferir os dados no painel da
Hostinger na hora): é o caso simples, sem OAuth. Precisa de uma **caixa de envio** (por exemplo `sistema@seudominio`), cuja senha
o administrador digita **uma vez no servidor** (guardada em `instance/`, com acesso só do SISTEMA e dos administradores, nunca no
código nem no repositório). O link do e-mail aponta para o endereço do sistema, então só abre dentro do escritório ou pela VPN
(fase 10), o que é o desejado. A mesma estrutura manda o **lembrete da troca do pen-drive por e-mail** (fase 5).

### Fase 4 — HTTPS na rede interna

**Por quê.** Hoje a senha e as fichas viajam em texto puro entre o computador de cada pessoa e o servidor. Quem estiver na mesma
rede (Wi-Fi compartilhado, um visitante, um aparelho infectado) consegue ler com ferramentas gratuitas.

**Como.** Um programa pequeno e gratuito (Caddy) fica na frente do sistema, com certificado de uma **autoridade certificadora
local** criada na própria casa (`tls internal`). O `waitress` passa a ouvir só em `127.0.0.1`. O cookie de sessão volta a ser
`Secure` (sai `SESSAO_SEM_HTTPS`) e entra HSTS.

**O que o usuário precisa fazer** (uma vez por computador): instalar o certificado raiz da casa. No Windows, em
`certlm.msc` → Autoridades de Certificação Raiz Confiáveis. **Firefox** tem repositório próprio: é preciso ligar
`security.enterprise_roots.enabled` (ou política `ImportEnterpriseRoots`) para ele aceitar o certificado do Windows. **Celulares**
exigem instalar o certificado manualmente e o Android mostra um aviso permanente.

**Alternativa** que evita instalar certificado em cada máquina: registrar um domínio próprio (cerca de R$ 40 por ano) e usar um
certificado público por desafio de DNS. O endereço interno passa a ter nome (`prontuario.casaacolhida.org.br`) e todos os
navegadores e celulares aceitam sem configuração. Custa pouco e simplifica a vida; decidir junto com a resposta abaixo.

**Decisão (2026-10-15)**: o usuário quer acesso pelo **celular** e por **qualquer navegador** (Chrome, Edge, Firefox, Safari).
Isso pesa contra a autoridade certificadora local (instalar e configurar certificado em cada celular e no Firefox). Como o
segundo polo vai precisar de VPN de qualquer jeito (fase 10), a recomendação é **usar o certificado que a própria VPN emite**
(Tailscale: `tailscale cert`, certificado público válido para o nome do computador na VPN), que todos os navegadores e celulares
aceitam sem instalar nada. A confirmar na hora de fazer: limites do plano gratuito e o funcionamento no Windows 11 Home.

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
  ser feita; na sexta de manhã manda esperar até as 18:45. A versão por **e-mail** vem com a estrutura de e-mail da fase 3.
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

### Fase 6 — Servidor Windows, rede e roteador

Roteiro com o passo a passo, quase tudo manual, em `implantacao/`:

- **Disco criptografado**: o Windows 11 Home tem a "Criptografia de dispositivo" se o computador tiver TPM e atender aos
  requisitos (Configurações → Privacidade e segurança → Criptografia de dispositivo). Guardar a chave de recuperação em papel.
- **Serviço com conta limitada** no lugar de SYSTEM: se alguém explorar o sistema, não ganha o computador inteiro.
- **Windows**: atualizações automáticas ligadas; Microsoft Defender ligado; conta de administrador do Windows com senha forte e
  conta comum para o dia a dia; bloqueio de tela por inatividade; computador em sala que se tranca.
- **Rede**: perfil "Privada"; o firewall só abre a porta para a sub-rede (já está); sem encaminhamento de portas no roteador
  (UPnP desligado); senha de administração do roteador trocada; Wi-Fi com WPA2/WPA3 e senha forte; **rede de visitantes separada**.
- **Impressão**: a impressora fica onde só a equipe passa; documento com dado sensível não fica na bandeja.

### Fase 7 — Defesa do navegador

- **Token CSRF** em todo formulário e chamada de alteração (hoje só `SameSite=Lax`, que é bom, mas não substitui).
- **CSP** (Content-Security-Policy) sem `unsafe-inline`: exige tirar os scripts e estilos que ainda estão dentro das páginas e
  passá-los para arquivos (as telas novas já seguem isso, como `static/permissoes.js`).
- Cabeçalhos extras: `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Content-Disposition` nos downloads.

### Fase 8 — LGPD no papel

Modelos prontos em `docs/lgpd/`, para a casa preencher e assinar:

- **Inventário de dados**: o quê, para quê, base legal (tutela da saúde, obrigação legal, consentimento do responsável quando
  for o caso), quem acessa, onde fica, por quanto tempo.
- **Política de retenção**: por quanto tempo guardar prontuário de ex-interno e quanto tempo um registro fica na lixeira antes
  de ser apagado de vez. Alinhar com as exigências do conselho profissional e da vigilância sanitária.
- **Termo de sigilo** assinado por quem recebe um login.
- **Plano de resposta a incidente**: quem avisa quem, em quanto tempo; a comunicação à ANPD e ao titular tem prazo (conferir a
  Resolução CD/ANPD nº 15/2024). Inclui o que fazer se um computador for roubado ou um pen-drive de backup for perdido.
- **Canal do titular** (art. 18): como a pessoa pede acesso, correção ou eliminação.
- A associação provavelmente se enquadra como agente de tratamento de **pequeno porte** (Resolução CD/ANPD nº 2/2022), com
  obrigações simplificadas, mas ainda precisa de canal de atendimento e das medidas acima. Confirmar com a contabilidade ou o jurídico.

### Fase 9 — Manutenção contínua

- **Auditoria mensal das dependências** (`pip-audit`) em um script de `implantacao/`, com aviso na página inicial se houver
  vulnerabilidade conhecida.
- **Revisão trimestral dos acessos**: lista de usuários × funcionários ativos × nível, com aviso no quadro de avisos.
- **Teste de restauração do backup** trimestral (fase 5) e revisão deste plano a cada semestre.

### Fase 10 — Segundo polo e acesso de fora do escritório

**Pergunta de origem (2026-10-15).** Hoje o sistema só abre quando o computador está no Wi-Fi do escritório. Dá para instalar
um servidor em outro polo e os dois usarem o mesmo banco?

**Por que não dois servidores com o SQLite.** O SQLite é um arquivo, feito para um computador só; dois servidores abrindo o mesmo
arquivo pela rede podem corrompê-lo. Manter um banco por polo e sincronizar traz conflitos (a mesma pessoa cadastrada nos dois
lados, numeração repetida, internet que cai no meio) e não é recomendado.

**Opção A (recomendada): um banco só, e o polo 2 entra no computador do escritório por VPN.**

- Sem servidor novo e sem sincronização: os dois polos usam o mesmo sistema e veem o que o outro registrou na hora.
- A VPN (por exemplo Tailscale, que tem plano gratuito; conferir os limites atuais) liga os aparelhos numa rede privada, **sem
  abrir porta no roteador** e sem expor o sistema na internet. Serve também para o celular fora do escritório.
- O HTTPS (fase 4) pode usar o certificado que a própria VPN oferece, sem instalar certificado em cada máquina (a confirmar).
- Ponto fraco: o computador do escritório vira o ponto único. Se ele ou a internet de lá cair, o polo 2 para. O backup externo
  (fase 5) passa a ser obrigatório.
- **Pré-requisitos de segurança**, que passam a ser obrigatórios antes de liberar: HTTPS (4), segundo fator do administrador, tempo
  ocioso (3), trilha de auditoria com o endereço de cada acesso (2) e o termo de sigilo (8).

**Opção B: Postgres central e um servidor do sistema em cada polo.** O sistema já suporta (`DATABASE_URL`, testado nesta entrega,
incluindo a cópia do SQLite com `copiar_banco.py`). O banco precisa ficar num lugar que os dois polos alcancem: a mesma VPN, ou um
Postgres em nuvem (custo, e dado de saúde fora do país, com implicação de LGPD). Só compensa se o polo 2 precisar funcionar com o
escritório fora do ar.

**Decisões (2026-10-15)**: os polos compartilham **exatamente as mesmas informações**, como se o sistema estivesse na nuvem, e o
polo 2 tem computadores e internet. Logo vale a **opção A**, sem campo "polo" e sem sincronização: um sistema, um banco, um
endereço (o do computador do escritório na VPN) para os dois polos e para o celular. Falta só confirmar com o usuário a hora de
fazer, porque depende das fases 2, 3 e 4 (pré-requisitos acima) e do backup externo (5).

## 5. O que só uma pessoa na casa pode fazer

| Quando | Tarefa |
|---|---|
| Agora | Revisar a grade de **Cadastros > Permissões** e ajustar o que cada nível pode; conferir que cada pessoa está no nível certo |
| Agora | Conferir se algum login ainda é compartilhado ("escritório", "recepção"). Um usuário por pessoa |
| Agora | Desativar o funcionário de quem saiu da casa (o login deixa de entrar na hora) |
| Fase 5 | Comprar **2 pen-drives** (marca conhecida, 32 GB bastam), rodar `configurar-backup-externo.ps1`, **anotar a frase em papel e guardar fora do computador**, preparar cada pen-drive e combinar quem troca na sexta (o pen-drive que sai do computador vai para a gaveta trancada) |
| Fase 5 | A cada 3 meses, fazer o teste de restauração (2 minutos, `implantacao/RESTAURAR.md`) |
| Fase 6 | Seguir o roteiro do Windows e do roteador |
| Fase 4 | Instalar o certificado em cada computador (e celular, se houver) |
| Fase 10 | Instalar a VPN no computador do escritório e em cada aparelho que for acessar de fora |
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

**Em aberto**

1. Qual **caixa de e-mail** o sistema usa para enviar (por exemplo, sistema@seudominio) e quem recebe o lembrete de troca do
   pen-drive? (A senha dela é digitada por você no servidor, nunca no código nem no repositório.)
2. Fase 3: **segundo fator** para o administrador, sim ou não? (Usa um app gratuito que já existe no celular, não um app novo.)
   A recomendação é sim, e passa a ser necessário para redefinir a senha do administrador pelo e-mail.

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
