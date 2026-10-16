<#
Auditoria das bibliotecas do sistema (fase 9 do plano de segurança): confere, na lista pública de vulnerabilidades conhecidas (pip-audit), as
bibliotecas Python que o sistema usa de verdade. O resultado vai para instance\auditoria_dependencias.json e a página inicial avisa o
administrador se alguma tem vulnerabilidade conhecida, se a auditoria falhou ou se parou de rodar. Precisa de internet.

  1) Primeira vez (faz a auditoria agora e agenda uma por mês; rode como Administrador, no servidor):

       powershell -ExecutionPolicy Bypass -File implantacao\auditar-dependencias.ps1 -Agendar

  2) Auditar de novo, quando quiser (não precisa ser Administrador):

       powershell -ExecutionPolicy Bypass -File implantacao\auditar-dependencias.ps1

Para ver o que seria feito, sem mudar nada, acrescente -SoVer.

O pip-audit fica num ambiente separado (.venv-auditoria, dentro da pasta do sistema), para não misturar as bibliotecas dele com as do sistema
(senão as dele apareceriam na auditoria). Se aparecer vulnerabilidade: rode implantacao\atualizar.ps1 (instala as versões novas que o
requirements.txt aceita). Se o aviso continuar, a correção ainda não saiu ou o requirements.txt precisa subir a versão: me avise.
#>
[CmdletBinding()]
param(
    [switch]$Agendar,
    [string]$Hora = "12:00",
    [switch]$SoVer
)
$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $Raiz ".venv\Scripts\python.exe"
$auditoria = Join-Path $Raiz ".venv-auditoria"
$auditoriaPy = Join-Path $auditoria "Scripts\python.exe"
$pacotes = Join-Path $Raiz ".venv\Lib\site-packages"
$saida = Join-Path $Raiz "instance\pip-audit.tmp.json"
$NomeTarefa = "Prontuario - auditoria de dependencias"

function Passo($texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }
function Aviso($texto) { Write-Host "    AVISO: $texto" -ForegroundColor Yellow }
function Fazer($descricao, [scriptblock]$acao) {
    Write-Host "    - $descricao"
    if (-not $SoVer) { & $acao }
}
function Nativo([string]$Exe, [string[]]$Argumentos) {
    # roda um programa e devolve o código de saída e o texto; no PowerShell 5.1 texto no stderr viraria erro fatal com $ErrorActionPreference = "Stop"
    $antes = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { $texto = & $Exe @Argumentos 2>&1 | ForEach-Object { "$_" } | Out-String; $codigo = $LASTEXITCODE } finally { $ErrorActionPreference = $antes }
    return [pscustomobject]@{ Codigo = $codigo; Saida = $texto.Trim() }
}

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($Agendar -and -not $admin -and -not $SoVer) { throw "Para agendar, rode este script como Administrador: botão direito no PowerShell > Executar como administrador." }
if ($SoVer) { Write-Host "(modo -SoVer: nada será alterado)" -ForegroundColor Yellow }
if (-not (Test-Path $venvPy)) { throw "Não achei $venvPy. O sistema foi instalado com implantacao\instalar.ps1 neste computador?" }
if (-not (Test-Path $pacotes) -and -not $SoVer) { throw "Não achei as bibliotecas do sistema em $pacotes." }

Passo "Preparando o pip-audit"
Fazer "atualizar o pip do sistema (o próprio pip também tem vulnerabilidades corrigidas de tempos em tempos)" {
    $r = Nativo $venvPy @("-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", "pip")
    if ($r.Codigo) { Aviso "não consegui atualizar o pip ($($r.Saida)); sigo assim mesmo." }
}
Fazer "criar o ambiente separado do pip-audit (.venv-auditoria), se ainda não existe" {
    if (-not (Test-Path $auditoriaPy)) {
        $r = Nativo $venvPy @("-m", "venv", $auditoria)
        if ($r.Codigo) { throw "Não consegui criar o ambiente do pip-audit: $($r.Saida)" }
    }
}
Fazer "instalar ou atualizar o pip-audit (precisa de internet)" {
    $r = Nativo $auditoriaPy @("-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", "pip-audit")
    if ($r.Codigo) {
        Nativo $venvPy @("manutencao.py", "falha-dependencias", "não consegui instalar o pip-audit (sem internet?)") | Out-Null
        throw "Não consegui instalar o pip-audit (sem internet?): $($r.Saida)"
    }
}

Passo "Conferindo as bibliotecas do sistema"
Fazer "rodar o pip-audit sobre $pacotes" {
    Remove-Item $saida -ErrorAction SilentlyContinue
    $r = Nativo $auditoriaPy @("-m", "pip_audit", "--path", $pacotes, "--format", "json", "--progress-spinner", "off", "-o", $saida)
    # o pip-audit sai com 1 quando ACHA vulnerabilidade (resultado válido); outro código, ou sem arquivo, é falha de verdade
    if (($r.Codigo -gt 1) -or -not (Test-Path $saida)) {
        $resumo = ($r.Saida -split "`n" | Select-Object -Last 2) -join " "
        Push-Location $Raiz; try { Nativo $venvPy @("manutencao.py", "falha-dependencias", "o pip-audit não terminou: $resumo") | Out-Null } finally { Pop-Location }
        throw "O pip-audit não terminou (sem internet?): $resumo"
    }
}
Fazer "guardar o resultado para a página inicial (instance\auditoria_dependencias.json)" {
    Push-Location $Raiz
    try {
        $r = Nativo $venvPy @("manutencao.py", "gravar-dependencias", $saida)
        Write-Host ("      " + ($r.Saida -replace "`n", "`n      "))
        if ($r.Codigo) { throw "Não consegui guardar o resultado." }
    } finally { Pop-Location; Remove-Item $saida -ErrorAction SilentlyContinue }
}

if ($Agendar) {
    Passo "Agendando a auditoria (a cada 4 semanas, às $Hora)"
    Fazer "criar a tarefa '$NomeTarefa' (roda como SISTEMA, mesmo sem ninguém logado)" {
        $script = Join-Path $Raiz "implantacao\auditar-dependencias.ps1"
        $acao = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory $Raiz
        $gatilho = New-ScheduledTaskTrigger -Weekly -WeeksInterval 4 -DaysOfWeek Monday -At $Hora
        $config = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
        Register-ScheduledTask -TaskName $NomeTarefa -Action $acao -Trigger $gatilho -Settings $config -Principal $principal -Force | Out-Null
    }
}
Write-Host ""
Write-Host "Pronto. O resultado aparece para o administrador na página inicial (e em Cadastros > Revisão)." -ForegroundColor Green
