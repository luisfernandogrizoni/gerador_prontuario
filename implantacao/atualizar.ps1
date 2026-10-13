<#
Atualiza o servidor do escritório com a versão mais nova do GitHub. Rode como Administrador:

    powershell -ExecutionPolicy Bypass -File implantacao\atualizar.ps1

Faz um backup, para o sistema, baixa o código novo (git pull), instala as dependências que mudaram e liga
o sistema de novo (as mudanças no banco são aplicadas sozinhas na subida). Se algo falhar no meio, o sistema
é ligado de novo mesmo assim, na versão que estava, e o script avisa. Use -SoVer para só listar os passos.
#>
[CmdletBinding()]
param(
    [int]$Porta = 8000,
    [switch]$SoVer
)
$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $Raiz ".venv\Scripts\python.exe"
$Nome = "Prontuario - servidor"

function Passo($texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }
function Fazer($descricao, [scriptblock]$acao) {
    Write-Host "    - $descricao"
    if (-not $SoVer) { & $acao }
}

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin -and -not $SoVer) { throw "Rode este script como Administrador: botão direito no PowerShell > Executar como administrador." }
if ($SoVer) { Write-Host "(modo -SoVer: nada será alterado)" -ForegroundColor Yellow }

Passo "1/4 Backup antes de atualizar"
Fazer "rodar o backup (se falhar, a atualização é cancelada)" {
    & $venvPy (Join-Path $Raiz "backup.py")
    if ($LASTEXITCODE) { throw "O backup falhou: não vou atualizar sem backup. Veja $Raiz\logs\backup.log" }
}

Passo "2/4 Parando o sistema"
Fazer "parar a tarefa '$Nome' e esperar a porta $Porta liberar" {
    Stop-ScheduledTask -TaskName $Nome -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Get-NetTCPConnection -LocalPort $Porta -State Listen -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Seconds 1
    }
}

$falhou = $null
try {
    Passo "3/4 Baixando a versão nova"
    Fazer "git pull" {
        & git -C $Raiz pull --ff-only
        if ($LASTEXITCODE) { throw "O git pull falhou (alterações locais na pasta do servidor? sem internet?)." }
    }
    Fazer "instalar as dependências" {
        & $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $Raiz "requirements.txt")
        if ($LASTEXITCODE) { throw "Falha ao instalar as dependências." }
    }
} catch {
    $falhou = $_.Exception.Message
    Write-Host "    ERRO: $falhou" -ForegroundColor Red
} finally {
    Passo "4/4 Ligando o sistema"
    Fazer "iniciar a tarefa '$Nome' e esperar responder" {
        Start-ScheduledTask -TaskName $Nome
        $ok = $false
        for ($i = 0; $i -lt 40 -and -not $ok; $i++) {
            try { $ok = ((Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Porta/login" -TimeoutSec 3).StatusCode -eq 200) } catch { Start-Sleep -Seconds 1 }
        }
        if ($ok) { Write-Host "      o sistema respondeu." }
        else { Write-Host "    ERRO: o sistema não respondeu em 40 segundos. Veja $Raiz\logs\servidor.log" -ForegroundColor Red; $script:falhou = "o sistema não subiu" }
    }
}

Write-Host ""
if ($falhou) { Write-Host "Atualização NÃO concluída: $falhou" -ForegroundColor Red; exit 1 }
Write-Host "Versão em uso agora:" -ForegroundColor Green
& git -C $Raiz log -1 --format="    %h %s"
