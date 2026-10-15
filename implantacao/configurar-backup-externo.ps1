<#
Liga a cópia externa criptografada do backup (pen-drives em rodízio). Rode como Administrador, neste computador (o servidor).

  1) Primeira vez (gera a frase de recuperação, que você anota EM PAPEL, e liga a tarefa de hora em hora):

       powershell -ExecutionPolicy Bypass -File implantacao\configurar-backup-externo.ps1

     Computador novo, com a frase que já existe no papel (em vez de gerar outra):

       powershell -ExecutionPolicy Bypass -File implantacao\configurar-backup-externo.ps1 -FraseExistente

  2) Para cada pen-drive (plugue um de cada vez, veja a letra dele no Explorador de Arquivos):

       powershell -ExecutionPolicy Bypass -File implantacao\configurar-backup-externo.ps1 -PrepararMidia E: -Nome A
       powershell -ExecutionPolicy Bypass -File implantacao\configurar-backup-externo.ps1 -PrepararMidia F: -Nome B

Para ver o que seria feito, sem mudar nada, acrescente -SoVer. O passo a passo completo está em implantacao\LEIA-ME.md
(parte 3) e, para o dia em que for preciso restaurar, em implantacao\RESTAURAR.md.

O que o script faz:
  - confere que a biblioteca de criptografia está instalada;
  - (primeira vez) gera a frase de recuperação, mostra UMA vez e guarda em instance\backup_chave.txt (acesso só do SISTEMA,
    dos administradores e de quem instalou);
  - cria a tarefa 'Prontuario - copia externa': das 8h às 20h, de hora em hora, leva o backup mais novo para o pen-drive
    que estiver plugado (a de 18:30 já faz isso junto; esta cobre o pen-drive plugado depois);
  - com -PrepararMidia, prepara o pen-drive (cria a pasta prontuario-backup com um código só dele) e faz a primeira cópia.
#>
[CmdletBinding()]
param(
    [string]$PrepararMidia = "",        # letra do pen-drive a preparar, ex.: E:
    [string]$Nome = "",                 # nome dele (A, B...): para saber qual levar para casa
    [switch]$FraseExistente,            # computador novo: em vez de gerar uma frase, digite a que já está no papel
    [string]$HoraInicial = "08:00",
    [switch]$SoVer
)
$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $Raiz ".venv\Scripts\python.exe"
$backup = Join-Path $Raiz "backup.py"
$instance = Join-Path $Raiz "instance"
$NomeTarefa = "Prontuario - copia externa"

function Passo($texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }
function Fazer($descricao, [scriptblock]$acao) {
    Write-Host "    - $descricao"
    if (-not $SoVer) { & $acao }
}

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin -and -not $SoVer) { throw "Rode este script como Administrador: botão direito no PowerShell > Executar como administrador." }
if ($SoVer) { Write-Host "(modo -SoVer: nada será alterado)" -ForegroundColor Yellow }
if (-not (Test-Path $venvPy)) { throw "Não achei $venvPy. O sistema foi instalado com implantacao\instalar.ps1 neste computador?" }

# ------------------------------------------------------------------ preparar um pen-drive
if ($PrepararMidia) {
    Passo "Preparando o pen-drive $PrepararMidia"
    if (-not (Test-Path (Join-Path $instance "backup_chave.txt"))) {
        throw "A frase de recuperação ainda não foi criada. Rode antes, sem parâmetros: implantacao\configurar-backup-externo.ps1"
    }
    $argumentos = @("--preparar-midia", $PrepararMidia)
    if ($Nome) { $argumentos += @("--nome", $Nome) }
    Fazer "preparar o pen-drive (cria a pasta prontuario-backup nele)" {
        & $venvPy $backup @argumentos
        if ($LASTEXITCODE) { throw "Não consegui preparar o pen-drive." }
    }
    Fazer "fazer a primeira cópia criptografada nele" {
        & $venvPy $backup --so-externo
        if ($LASTEXITCODE) { Write-Host "    AVISO: a cópia não terminou. Veja $Raiz\logs\backup.log" -ForegroundColor Yellow }
    }
    Write-Host ""
    Write-Host "Pronto. Plugue sempre este mesmo pen-drive: o sistema o reconhece em qualquer porta." -ForegroundColor Green
    return
}

# ------------------------------------------------------------------ primeira configuração
Passo "Conferindo a biblioteca de criptografia"
Fazer "instalar o que faltar (cryptography)" {
    & $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $Raiz "requirements.txt")
    if ($LASTEXITCODE) { throw "Falha ao instalar as dependências (sem internet?)." }
}

Passo "Frase de recuperação"
if (Test-Path (Join-Path $instance "backup_chave.txt")) {
    Write-Host "    já existe (instance\backup_chave.txt). Nada foi mudado."
} else {
    if ($FraseExistente) {
        Fazer "guardar neste computador a frase que você já tem no papel (plugue um pen-drive do rodízio para ela ser conferida)" {
            & $venvPy $backup --informar-frase
            if ($LASTEXITCODE) { throw "A frase não foi guardada." }
        }
    } else {
        Write-Host "    A frase vai aparecer UMA vez. Tenha papel e caneta à mão." -ForegroundColor Yellow
        Fazer "gerar a frase e guardar neste computador" {
            & $venvPy $backup --configurar-externo
            if ($LASTEXITCODE) { throw "Não consegui criar a frase." }
        }
    }
}

Passo "Tarefa do Windows (roda como SISTEMA, mesmo sem ninguém logado)"
Fazer "criar '$NomeTarefa': das $HoraInicial às 20h, de hora em hora, leva o backup mais novo para o pen-drive plugado" {
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    $acao = New-ScheduledTaskAction -Execute $venvPy -Argument "backup.py --so-externo" -WorkingDirectory $Raiz
    $gatilho = New-ScheduledTaskTrigger -Daily -At $HoraInicial
    $repeticao = New-ScheduledTaskTrigger -Once -At $HoraInicial -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Hours 12)
    $gatilho.Repetition = $repeticao.Repetition
    $config = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -StartWhenAvailable -MultipleInstances IgnoreNew `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $NomeTarefa -Action $acao -Trigger $gatilho -Settings $config -Principal $principal -Force | Out-Null
}

Passo "Unidades deste computador"
Fazer "listar as unidades e os pen-drives já preparados" {
    & $venvPy $backup --listar-midias
}

Write-Host ""
Write-Host "Falta: preparar cada pen-drive (um de cada vez, com ele plugado):" -ForegroundColor Green
Write-Host "    powershell -ExecutionPolicy Bypass -File implantacao\configurar-backup-externo.ps1 -PrepararMidia E: -Nome A"
Write-Host "    powershell -ExecutionPolicy Bypass -File implantacao\configurar-backup-externo.ps1 -PrepararMidia F: -Nome B"
