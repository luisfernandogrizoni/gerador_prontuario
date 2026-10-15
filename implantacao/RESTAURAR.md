# Restaurar o sistema a partir do backup

Para o dia em que o computador do escritório quebrar, for roubado ou o banco estragar. **Imprima esta página e guarde junto
da folha com a frase de recuperação.** O que você precisa ter em mãos:

- um pen-drive do rodízio (de preferência o mais novo; o que está fora do escritório também serve);
- a **frase de recuperação** (a folha em papel, formato `XXXX-XXXX-XXXX-XXXX-XXXX-XXXX`). **Sem ela as cópias dos pen-drives não
  abrem, nem para quem fez o sistema.** Não há como recuperar a frase;
- um computador com Windows e internet.

Os usuários e as senhas ficam **dentro do banco**: voltam junto. Só as sessões abertas caem (todo mundo entra de novo).

## Caso A: o computador está bom, mas o banco estragou ou foi apagado

1. Pare o sistema (PowerShell **como administrador**):

   ```powershell
   Stop-ScheduledTask "Prontuario - servidor"
   ```

2. Se ainda houver um backup do dia sem defeito na pasta de backup (`internos-AAAA-MM-DD_HHMMSS.db`), é o jeito mais rápido:

   ```powershell
   Rename-Item C:\prontuario\instance\internos.db internos_ESTRAGADO.db
   Copy-Item "E:\backup-prontuario\internos-AAAA-MM-DD_HHMMSS.db" C:\prontuario\instance\internos.db
   ```

3. Se não houver, restaure do pen-drive (plugue-o e veja a letra dele, aqui `F:`). Ele pede a frase: digite a do papel.

   ```powershell
   cd C:\prontuario
   .\.venv\Scripts\python.exe backup.py --restaurar "F:\prontuario-backup\prontuario-AAAA-MM-DD_HHMMSS.pbk" --para C:\prontuario\instance\internos_restaurado.db
   ```

   Ele só grava se o banco de dentro estiver íntegro e mostra quantos registros tem. Aí troque o arquivo:

   ```powershell
   Rename-Item C:\prontuario\instance\internos.db internos_ESTRAGADO.db
   Rename-Item C:\prontuario\instance\internos_restaurado.db internos.db
   ```

4. Ligue o sistema e confira:

   ```powershell
   Start-ScheduledTask "Prontuario - servidor"
   ```

   Abra o sistema, entre e veja a lista de internos. Guarde o `internos_ESTRAGADO.db` até ter certeza de que está tudo certo.

## Caso B: o computador foi perdido ou será trocado

1. No computador novo (Windows), instale o **Python 3.12 ou mais novo** (python.org; o do Microsoft Store não serve) e o **Git**.
2. Baixe o sistema:

   ```powershell
   git clone https://github.com/luisfernandogrizoni/gerador_prontuario C:\prontuario
   cd C:\prontuario
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Plugue o pen-drive, veja a letra dele e restaure o banco (digite a frase do papel quando pedir):

   ```powershell
   .\.venv\Scripts\python.exe backup.py --restaurar "F:\prontuario-backup\prontuario-AAAA-MM-DD_HHMMSS.pbk" --para C:\banco_restaurado.db
   ```

4. Instale o servidor levando esse banco (PowerShell **como administrador**; a pasta de backup é a do novo computador/HD):

   ```powershell
   powershell -ExecutionPolicy Bypass -File implantacao\instalar.ps1 -PastaBackup "E:\backup-prontuario" -BancoAtual C:\banco_restaurado.db
   ```

5. Refaça a cópia externa neste computador **com a mesma frase do papel** (com um pen-drive do rodízio plugado: o sistema confere
   se a frase abre a cópia antes de guardar):

   ```powershell
   powershell -ExecutionPolicy Bypass -File implantacao\configurar-backup-externo.ps1 -FraseExistente
   ```

   Depois prepare os pen-drives de novo, um de cada vez (`-PrepararMidia F: -Nome A`): eles continuam servindo, e as cópias
   que já estão neles continuam abrindo com a mesma frase.

6. **E-mail e segundo fator.** O envio de e-mail (`instance\email.json`) e a chave que abre o segundo fator (`instance\secret.key`)
   **não vão no backup do banco**, de propósito (um backup sozinho não dá a senha da caixa de e-mail nem o segundo fator de
   ninguém). No computador novo, ligue o e-mail de novo (`implantacao\configurar-email.ps1`, digitando a senha da caixa). Quem tinha
   o aplicativo autenticador ligado **não consegue usar o código do app** (a chave nova não abre o segredo antigo): entra com um
   **código de recuperação** (os que a pessoa guardou em papel) e liga o app de novo em *Minha segurança*, ou o administrador roda
   `.\.venv\Scripts\python.exe -m flask --app app desativar-segundo-fator USUARIO` e a pessoa entra só com a senha e liga de novo.
   (Se você ainda tiver a pasta `instance` do computador antigo, copiar o `secret.key` dela para o novo evita isso.)
7. Veja o endereço novo que o instalador mostrou e avise as pessoas; reserve o IP no roteador.

## Se a frase de recuperação foi perdida

As cópias `.pbk` dos pen-drives **não abrem**. Procure o último `internos-*.db` (sem criptografia) na pasta de backup deste
computador ou do HD, ou o `instance\internos.db` do próprio computador. Depois crie uma frase nova
(`implantacao\configurar-backup-externo.ps1`, apagando antes `instance\backup_chave.txt`) e guarde o papel num lugar de verdade.

## Treino (a cada 3 meses)

Faça o teste sem esperar a emergência. Com um pen-drive plugado, no servidor:

```powershell
cd C:\prontuario
.\.venv\Scripts\python.exe backup.py --testar-restauracao
```

Digite a frase **do papel** (não a do computador): o teste prova que o papel está certo e que a cópia abre. O sistema anota a
data e a página inicial para de cobrar. Se falhar, não é frescura: é o aviso de que, hoje, o backup não serve.
