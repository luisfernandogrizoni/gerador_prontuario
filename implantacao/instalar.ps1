<#
Instala o servidor do escritório NESTE computador. Rode uma vez, como Administrador:

    powershell -ExecutionPolicy Bypass -File implantacao\instalar.ps1 -PastaBackup "E:\backup-prontuario"

Para ver o que seria feito, sem mudar nada, acrescente -SoVer. Para desfazer (os dados e os backups
ficam), use -Remover. O passo a passo completo está em implantacao\LEIA-ME.md.

O que o script faz:
  1. cria o ambiente do Python (.venv) e instala as dependências;
  2. cria as pastas instance (o banco) e logs, só com acesso do SISTEMA, dos administradores e seu;
  3. (opcional) leva para cá os dados de outro banco, com -BancoAtual;
  4. libera a porta no firewall do Windows só para a rede local;
  5. impede o computador de suspender ou hibernar enquanto estiver na tomada;
  6. cria duas tarefas do Windows: o sistema (liga sozinho quando o computador ligar, e religa se cair)
     e o backup diário;
  7. liga o sistema, faz o primeiro backup e confere que os dois funcionaram.
#>
[CmdletBinding()]
param(
    [string]$PastaBackup = "",          # onde guardar os backups; de preferência OUTRO disco (HD externo)
    [int]$Porta = 8000,
    [string]$Python = "",               # caminho do python.exe, se o script não achar sozinho
    [string]$BancoAtual = "",           # banco SQLite com os dados de hoje (instance\internos.db do seu projeto)
    [string]$HoraDoBackup = "18:30",
    [switch]$SoVer,
    [switch]$Remover
)
$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent $PSScriptRoot
$NomeServidor = "Prontuario - servidor"
$NomeBackup = "Prontuario - backup diario"
$NomeRegra = "Prontuario (porta $Porta)"

function Passo($texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }
function Aviso($texto) { Write-Host "    AVISO: $texto" -ForegroundColor Yellow }
function Fazer($descricao, [scriptblock]$acao) {
    Write-Host "    - $descricao"
    if (-not $SoVer) { & $acao }
}

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin -and -not $SoVer) {
    throw "Rode este script como Administrador: botão direito no PowerShell > Executar como administrador."
}
if ($SoVer) { Write-Host "(modo -SoVer: nada será alterado)" -ForegroundColor Yellow }

# ------------------------------------------------------------------ desinstalar
if ($Remover) {
    Passo "Removendo o servidor (os dados e os backups NÃO são apagados)"
    Fazer "parar e remover as tarefas do Windows" {
        foreach ($n in $NomeServidor, $NomeBackup) {
            Stop-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $n -Confirm:$false -ErrorAction SilentlyContinue
        }
    }
    Fazer "remover a regra do firewall" { Remove-NetFirewallRule -DisplayName $NomeRegra -ErrorAction SilentlyContinue }
    return
}

# ------------------------------------------------------------------ Python
Passo "Procurando o Python"
function Achar-Python {
    if ($Python) { return $Python }
    $candidatos = @()
    $p = Get-Command python -ErrorAction SilentlyContinue
    if ($p) { $candidatos += $p.Source }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        try { $achado = & py -3 -c "import sys; print(sys.executable)"; if ($LASTEXITCODE -eq 0 -and $achado) { $candidatos += $achado } } catch { }
    }
    # o "python" da Microsoft Store (WindowsApps) não funciona para uma tarefa do sistema
    foreach ($c in $candidatos) { if ($c -and (Test-Path $c) -and ($c -notlike "*\WindowsApps\*")) { return $c } }
    throw "Não achei o Python. Instale o Python 3.12 ou mais novo (python.org) ou informe o caminho com -Python 'C:\...\python.exe'."
}
$py = Achar-Python
$versao = & $py -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$versao -lt [version]"3.10") { throw "O Python encontrado ($py) é o $versao; o sistema precisa do 3.10 ou mais novo." }
Write-Host "    $py (Python $versao)"
if ($py -like "$env:USERPROFILE*") {
    Aviso "esse Python está instalado só para o seu usuário. Funciona, mas se você trocar de versão do Python, rode este instalador de novo."
}

# ------------------------------------------------------------------ pastas, dependências, dados
Passo "Preparando as pastas e as dependências"
$venvPy = Join-Path $Raiz ".venv\Scripts\python.exe"
$instance = Join-Path $Raiz "instance"
$logs = Join-Path $Raiz "logs"
$usuario = "$env:USERDOMAIN\$env:USERNAME"

Fazer "criar o ambiente do Python (.venv) e instalar as dependências (pode levar alguns minutos)" {
    if (-not (Test-Path $venvPy)) {
        & $py -m venv (Join-Path $Raiz ".venv")
        if ($LASTEXITCODE) { throw "Não consegui criar o ambiente do Python." }
    }
    & $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $Raiz "requirements.txt")
    if ($LASTEXITCODE) { throw "Falha ao instalar as dependências (sem internet?)." }
}

function Proteger($pasta) {
    New-Item -ItemType Directory -Force -Path $pasta | Out-Null
    # por SID, não por nome: "Administrators" se chama "Administradores" no Windows em português
    $meuSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls $pasta /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "*${meuSid}:(OI)(CI)F" | Out-Null
    if ($LASTEXITCODE) { Aviso "não consegui restringir o acesso a $pasta" }
}
Fazer "criar instance e logs, com acesso só do SISTEMA, dos administradores e de $usuario" {
    Proteger $instance
    Proteger $logs
}

if (-not $PastaBackup) {
    $PastaBackup = Join-Path $Raiz "backups"
    Aviso "sem -PastaBackup, os backups ficam em $PastaBackup, no MESMO disco do banco: protegem de um erro, não de um disco que queima. Use um HD externo."
} elseif ((Split-Path $PastaBackup -Qualifier -ErrorAction SilentlyContinue) -eq (Split-Path $Raiz -Qualifier)) {
    Aviso "a pasta de backup está no mesmo disco do sistema: não protege de um disco que queima. Ligue também a cópia externa criptografada em pen-drives (implantacao\configurar-backup-externo.ps1)."
}
if ($PastaBackup -like "\\*") {
    Aviso "pasta de rede como destino costuma falhar nas tarefas do sistema (elas não têm a sua senha). Prefira um disco ligado a este computador."
}
Fazer "guardar a pasta de backup ($PastaBackup)" {
    New-Item -ItemType Directory -Force -Path $PastaBackup | Out-Null
    Set-Content -Path (Join-Path $instance "pasta_backup.txt") -Value $PastaBackup -Encoding UTF8
}

if ($BancoAtual) {
    $bancoNovo = Join-Path $instance "internos.db"
    if (Test-Path $bancoNovo) {
        Aviso "já existe ${bancoNovo}: os dados de $BancoAtual NÃO foram copiados (não sobrescrevo um banco existente)."
    } else {
        Fazer "levar os dados de $BancoAtual para $bancoNovo (cópia consistente)" {
            & $venvPy (Join-Path $Raiz "backup.py") --origem $BancoAtual --copiar-para $bancoNovo
            if ($LASTEXITCODE) { throw "Não consegui copiar os dados." }
        }
    }
}

# ------------------------------------------------------------------ rede e energia
Passo "Firewall e energia"
Fazer "liberar a porta $Porta só para a rede local (regra '$NomeRegra'); NÃO abra a porta no roteador" {
    Remove-NetFirewallRule -DisplayName $NomeRegra -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName $NomeRegra -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Porta -RemoteAddress LocalSubnet -Profile Any | Out-Null
}
Fazer "não suspender nem hibernar enquanto estiver na tomada" {
    & powercfg /change standby-timeout-ac 0
    & powercfg /change hibernate-timeout-ac 0
}
Fazer "não deixar o Windows desligar dispositivos USB para economizar energia (derruba adaptador de rede USB)" {
    & powercfg /setacvalueindex SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0
    & powercfg /setactive SCHEME_CURRENT
}
if (Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue) {
    Fazer "notebook: fechar a tampa na tomada não faz nada (senão o computador suspende e o sistema cai)" {
        & powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
        & powercfg /setactive SCHEME_CURRENT
    }
}

# a rede em que este computador está: só avisa, não muda nada
$rota = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction SilentlyContinue | Sort-Object RouteMetric | Select-Object -First 1
if ($rota) {
    $placa = Get-NetAdapter -InterfaceIndex $rota.InterfaceIndex -ErrorAction SilentlyContinue
    if ($placa -and $placa.PhysicalMediaType -like "*802.11*") {
        Aviso "este computador está na rede por Wi-Fi ($($placa.Name)). Para servidor, cabo de rede é bem mais estável: se der, ligue um cabo no roteador."
        Fazer "tentar impedir que o Windows desligue o adaptador Wi-Fi para economizar energia" {
            try { Set-NetAdapterPowerManagement -Name $placa.Name -AllowComputerToTurnOffDevice Disabled -ErrorAction Stop }
            catch { Aviso "este adaptador não aceitou o ajuste. Se o sistema cair do nada, abra Gerenciador de Dispositivos > Adaptadores de rede > o Wi-Fi > Gerenciamento de Energia e desmarque 'Permitir que o computador desligue este dispositivo'." }
        }
    }
    $perfil = Get-NetConnectionProfile -InterfaceIndex $rota.InterfaceIndex -ErrorAction SilentlyContinue
    if ($perfil -and $perfil.NetworkCategory -eq "Public") {
        Write-Host "    A rede está como 'Pública'. Funciona (a regra do firewall vale para esse perfil), mas os outros computadores podem não achar este pelo NOME: use o endereço com números (IP)."
    }
}

# ------------------------------------------------------------------ tarefas do Windows
Passo "Tarefas do Windows (rodam como SISTEMA, mesmo sem ninguém logado)"
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Fazer "criar '$NomeServidor': liga o sistema quando o computador ligar e religa se ele cair" {
    $acao = New-ScheduledTaskAction -Execute $venvPy -Argument "servidor.py --porta $Porta" -WorkingDirectory $Raiz
    $gatilho = New-ScheduledTaskTrigger -AtStartup
    $config = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) `
        -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $NomeServidor -Action $acao -Trigger $gatilho -Settings $config -Principal $principal -Force | Out-Null
    Stop-ScheduledTask -TaskName $NomeServidor -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName $NomeServidor
}
Fazer "criar '$NomeBackup': todo dia às $HoraDoBackup (se o computador estiver desligado, roda assim que ligar)" {
    $acao = New-ScheduledTaskAction -Execute $venvPy -Argument "backup.py" -WorkingDirectory $Raiz
    $gatilho = New-ScheduledTaskTrigger -Daily -At $HoraDoBackup
    $config = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $NomeBackup -Action $acao -Trigger $gatilho -Settings $config -Principal $principal -Force | Out-Null
}

# ------------------------------------------------------------------ conferência
Passo "Conferindo"
Fazer "esperar o sistema responder em http://127.0.0.1:$Porta" {
    $ok = $false
    for ($i = 0; $i -lt 40 -and -not $ok; $i++) {
        try { $ok = ((Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Porta/login" -TimeoutSec 3).StatusCode -eq 200) } catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ok) { throw "O sistema não respondeu em 40 segundos. Veja $logs\servidor.log" }
    Write-Host "      o sistema respondeu."
}
Fazer "rodar o primeiro backup agora" {
    Start-ScheduledTask -TaskName $NomeBackup
    $marcador = Join-Path $instance "ultimo_backup.txt"
    $ok = $false
    for ($i = 0; $i -lt 60 -and -not $ok; $i++) {
        Start-Sleep -Seconds 1
        $ok = (Test-Path $marcador) -and ((Get-Item $marcador).LastWriteTime -gt (Get-Date).AddMinutes(-2))
    }
    if ($ok) { Write-Host "      backup feito em $PastaBackup" }
    else { Aviso "o primeiro backup não terminou em 1 minuto. Veja $logs\backup.log (o HD externo está conectado?)" }
}

Write-Host ""
Write-Host "Pronto. Nos outros computadores, abra no navegador um destes endereços:" -ForegroundColor Green
# só endereços de rede local (10.x, 172.16-31.x, 192.168.x), sem adaptadores virtuais
$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -match '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)' -and $_.PrefixLength -lt 32 -and $_.InterfaceAlias -notlike "*Loopback*" } |
    Select-Object -ExpandProperty IPAddress
foreach ($ip in $ips) { Write-Host "    http://${ip}:${Porta}" }
Write-Host "    http://${env:COMPUTERNAME}:${Porta}   (pelo nome do computador, se a rede resolver)"
Write-Host ""
Write-Host "Falta fazer à mão (veja o LEIA-ME.md): IP fixo no roteador, horário ativo do Windows Update, os usuários das pessoas e a cópia externa criptografada em pen-drives (implantacao\configurar-backup-externo.ps1)." -ForegroundColor Yellow
