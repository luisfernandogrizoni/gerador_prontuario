# Servidor do escritório (Windows)

Um computador do escritório guarda o banco e roda o sistema; os outros usam pelo navegador, em
`http://IP-DO-SERVIDOR:8000`, cada pessoa com o seu usuário. Não custa nada e os dados não saem do escritório.

Funciona **só dentro da rede do escritório**. O banco fica num único lugar: o backup (parte 3) é o que protege contra
disco queimado, vírus ou arquivo apagado sem querer.

## Antes de começar

- **Python 3.10 ou mais novo** (python.org) e **Git**. O "python" que vem da Microsoft Store não serve.
- Um **HD externo ou pendrive grande** para os backups, sempre ligado ao servidor. Backup no mesmo disco do banco
  protege de erro, não de pane no disco.
- Se der, **cabo de rede** no servidor: Wi-Fi funciona, mas cai mais.
- Uma pessoa responsável por ligar, atualizar e conferir o backup.

## 1. Instalar (uma vez)

Use uma pasta **separada** da de desenvolvimento, para mexer no código não afetar o sistema do escritório:

```powershell
git clone https://github.com/luisfernandogrizoni/gerador_prontuario C:\prontuario
```

Abra o PowerShell **como administrador** (botão direito > Executar como administrador). Primeiro só veja o que será feito:

```powershell
cd C:\prontuario
powershell -ExecutionPolicy Bypass -File implantacao\instalar.ps1 -SoVer -PastaBackup "E:\backup-prontuario"
```

Depois instale de verdade (troque a pasta de backup e o caminho do banco atual):

```powershell
powershell -ExecutionPolicy Bypass -File implantacao\instalar.ps1 -PastaBackup "E:\backup-prontuario" -BancoAtual "C:\caminho\do\projeto\instance\internos.db"
```

O instalador cria o ambiente do Python, leva os dados do banco atual (uma cópia consistente, sem apagar o original),
libera a porta 8000 no firewall **só para a rede local**, impede o computador de suspender, e cria duas tarefas do Windows:
**Prontuario - servidor** (liga sozinho quando o computador ligar e religa se cair) e **Prontuario - backup diario** (18:30).
Ele liga o sistema, faz o primeiro backup e mostra os endereços para os outros computadores.

As tarefas rodam como o usuário SISTEMA do Windows, para subir sem ninguém logado. Por isso o banco (`instance`) e os
registros (`logs`) ficam com acesso só do SISTEMA, dos administradores e de quem instalou.

## 2. O que fazer à mão depois

1. **IP fixo.** Se o IP do servidor mudar, os favoritos dos outros computadores quebram. Entre no painel do roteador
   (geralmente `192.168.0.1` ou `192.168.1.1`, o "gateway" que o `ipconfig` mostra) e crie uma *reserva de DHCP* (ou
   "IP fixo") para este computador.
2. **Windows Update.** Configurações > Windows Update > Opções avançadas > *Horário ativo*: marque o horário do
   expediente, para o computador não reiniciar no meio do dia. Reiniciar de madrugada é seguro: o sistema volta sozinho.
3. **Usuários.** Cada pessoa tem o seu, com senha própria de no mínimo 10 caracteres. Só o primeiro usuário (o seu) é
   criado pelo terminal; o resto é feito dentro do sistema:

   ```powershell
   cd C:\prontuario
   .\.venv\Scripts\python.exe -m flask --app app criar-usuario luis
   ```

   Entre com ele, abra *Cadastros > Funcionários*, edite o seu cadastro e, em *Acesso ao sistema*, escolha o seu usuário
   em *Usuário de login* (o seu cadastro é o do nível Administrador). Daí em diante só o administrador cria usuários:
   em *Novo funcionário* (ou editando a pessoa), preencha *Criar um usuário novo* e a senha. Cada pessoa troca a própria
   senha depois, em *Alterar senha*.
4. **Testar** a partir de outro computador: abra o endereço que o instalador mostrou e entre. Salve como favorito.
5. **Aposente o banco antigo.** Depois de conferir que os dados estão no servidor, renomeie o `instance\internos.db` do
   projeto de desenvolvimento (por exemplo para `internos_ANTIGO_nao_usar.db`). Dois bancos em uso ao mesmo tempo
   significam dados espalhados e perdidos.

## 3. Backup

- Todo dia às 18:30 (ou, se o computador estava desligado, assim que ligar) o `backup.py` copia o banco para a pasta
  escolhida e guarda as últimas **30 cópias**. A cópia é conferida depois de feita; só vale se estiver íntegra.
- **A página inicial avisa** ("Backup do banco") se passarem mais de 3 dias sem backup. Quando aparecer, veja
  `C:\prontuario\logs\backup.log`: o motivo mais comum é o HD externo desconectado.
- Para fazer um backup na hora: `.\.venv\Scripts\python.exe backup.py`.
- Os arquivos desta pasta (`internos-*.db`) têm **dados pessoais** e **não são criptografados**: guarde o HD em lugar
  fechado e não envie para Drive/OneDrive. Eles protegem de erro e de arquivo estragado; **não** protegem de roubo, incêndio
  ou vírus que atinjam o computador e o HD juntos. Para isso existe a cópia externa, abaixo.
- **Nunca copie `internos.db` na mão** com o sistema ligado; use o `backup.py`.

### Cópia externa criptografada, em dois pen-drives em rodízio

Um pen-drive só não basta: se ele fica plugado, um vírus, um roubo ou um incêndio levam o banco e a cópia juntos; pen-drive
barato falha sem avisar; e, enquanto grava, ele é a única cópia fora do computador. Por isso são **dois**: um fica plugado
no servidor e o outro **guardado, trancado** (a gaveta trancada do escritório foi a escolha da casa), e **trocam de lugar toda
semana**. A gaveta protege de vírus, de erro e de pen-drive que estraga; **não protege de incêndio, alagamento nem de roubo do
escritório inteiro**. Se um dia der, levar o pen-drive guardado para casa uma vez por mês resolve isso.

- A cópia vai **criptografada** (AES-256) e **conferida na hora**: o sistema abre o arquivo de novo e confere o banco. Quem
  achar o pen-drive não lê nada. Ficam as cópias dos últimos 14 dias, uma por semana nas 8 semanas seguintes e uma por mês
  até 1 ano.
- A chave é uma **frase de recuperação** de 24 letras e números. Ela aparece **uma única vez**, na configuração: anote **em
  papel** e guarde fora do computador (não tire foto, não salve em arquivo). **Sem ela as cópias dos pen-drives não abrem.**

**Configurar (uma vez)**, no servidor, com o PowerShell **como administrador**:

```powershell
cd C:\prontuario
powershell -ExecutionPolicy Bypass -File implantacao\configurar-backup-externo.ps1
```

Ele mostra a frase (anote!), guarda uma cópia dela no servidor (só o SISTEMA e os administradores leem; é o que deixa a tarefa
automática criptografar) e cria a tarefa **Prontuario - copia externa** (das 8h às 20h, de hora em hora). Depois, **prepare
cada pen-drive**, um de cada vez, com ele plugado (veja a letra no Explorador de Arquivos):

```powershell
powershell -ExecutionPolicy Bypass -File implantacao\configurar-backup-externo.ps1 -PrepararMidia E: -Nome A
```

```powershell
powershell -ExecutionPolicy Bypass -File implantacao\configurar-backup-externo.ps1 -PrepararMidia F: -Nome B
```

O sistema reconhece cada pen-drive pelo código da pastinha `prontuario-backup` que ele ganha, em qualquer porta ou letra.
Nunca é usado o disco do próprio computador.

**Rotina semanal (5 minutos):** na **sexta, depois das 18:30**, tire o pen-drive que está plugado, guarde-o na gaveta trancada e
plugue o outro. Quem troca não precisa lembrar sozinho: a **página inicial** avisa quando o mesmo pen-drive passa de 7 dias
plugado, quando falta plugar o pen-drive (mais de 3 dias sem cópia) e quando os dois estão plugados ao mesmo tempo. A tela
**Cadastros > Backup** (só o administrador) mostra cada pen-drive, desde quando está plugado e a última cópia.

**Teste de restauração (a cada 3 meses):** com um pen-drive plugado, no servidor:

```powershell
cd C:\prontuario
.\.venv\Scripts\python.exe backup.py --testar-restauracao
```

Digite a frase **do papel**. O teste abre a cópia mais nova e confere o banco: prova que o papel está certo e que o backup
serve. A página inicial cobra o primeiro teste depois de 7 dias e um novo a cada ~100 dias.

**Se o computador morrer**, ou para restaurar: `implantacao\RESTAURAR.md` (imprima e guarde junto da folha da frase).

**Restaurar** do backup do dia (com o sistema parado; para restaurar de um pen-drive, veja `RESTAURAR.md`):

```powershell
Stop-ScheduledTask "Prontuario - servidor"
Copy-Item "E:\backup-prontuario\internos-AAAA-MM-DD_HHMMSS.db" C:\prontuario\instance\internos.db -Force
Start-ScheduledTask "Prontuario - servidor"
```

Teste isso uma vez com o sistema funcionando bem, para saber que funciona antes de precisar.

## 4. Atualizar o sistema

Depois que uma mudança for juntada no `main` do GitHub, no servidor (PowerShell como administrador):

```powershell
cd C:\prontuario
powershell -ExecutionPolicy Bypass -File implantacao\atualizar.ps1
```

Faz um backup (e **cancela se o backup falhar**), para o sistema, baixa a versão nova, instala o que mudou e liga de novo.
O banco se atualiza sozinho na subida. Se algo falhar, o sistema volta a ligar na versão que estava.

## 5. Se algo der errado

| Sintoma | O que ver |
| --- | --- |
| Outro computador não abre a página | O servidor está ligado? O IP mudou (`ipconfig`)? Ambos na mesma rede/roteador? Tente pelo IP, não pelo nome. |
| A página abre, mas alguém não consegue entrar | 5 senhas erradas seguidas bloqueiam o usuário por 10 minutos. Para dar uma senha nova e desbloquear, o administrador preenche *Nova senha* no cadastro da pessoa (*Cadastros > Funcionários*). Se não houver nenhum administrador que consiga entrar: `.\.venv\Scripts\python.exe -m flask --app app redefinir-senha maria`. |
| O sistema parou | `C:\prontuario\logs\servidor.log` mostra o erro. No Agendador de Tarefas, a tarefa *Prontuario - servidor* mostra o último resultado. |
| Aviso de backup na página inicial | `C:\prontuario\logs\backup.log`; o HD externo está ligado? |
| Quer ligar à mão, para ver o erro na tela | `cd C:\prontuario` e `.\.venv\Scripts\python.exe servidor.py` (pare a tarefa antes, para não dividir a porta). |

## 6. Segurança e limites

- **Sem HTTPS na rede interna.** A senha trafega sem criptografia dentro da rede do escritório. Mantenha o Wi-Fi com
  senha forte e deixe visitantes em outra rede.
- O firewall libera a porta 8000 só para a sub-rede local. **Não** redirecione portas no roteador.
- O Windows 11 Home não tem o BitLocker completo. Em Configurações > Privacidade e segurança, veja se há
  *Criptografia do dispositivo* e, se houver, ative (guarde a chave de recuperação fora do computador). Use senha no Windows.
- O servidor registra só erros, sem acessos e sem dados dos internos.
- Acesso de fora do escritório não existe, de propósito.

## 7. Desinstalar

```powershell
powershell -ExecutionPolicy Bypass -File implantacao\instalar.ps1 -Remover
```

Remove as tarefas e a regra do firewall. O banco (`instance`) e os backups **não** são apagados.
