<#
Liga o envio de e-mail do sistema (código de confirmação do e-mail, "esqueci minha senha", avisos de segurança e o aviso da troca do
pen-drive). Rode como Administrador, neste computador (o servidor), UMA vez:

       powershell -ExecutionPolicy Bypass -File implantacao\configurar-email.ps1

O script pergunta, uma coisa de cada vez:
  - a caixa de envio (o padrão é sistema@restauracao.org.br, na Hostinger);
  - a SENHA dessa caixa: ela é digitada aqui, NÃO aparece na tela e NUNCA vai para o código, para o repositório nem para o chat.
    Fica só em instance\email.json, que o Windows deixa aberto apenas para o SISTEMA, os administradores e quem instalou;
  - o endereço do sistema que vai nos links dos e-mails (o padrão é o endereço deste computador na rede do escritório);
  - quem recebe os avisos do sistema (o padrão é financeiro@restauracao.org.br).

Depois manda um e-mail de teste para o endereço que você informar. Parâmetros opcionais:

       -Caixa sistema@restauracao.org.br   -Avisos financeiro@restauracao.org.br   -Endereco http://192.168.15.19:8000
       -Servidor smtp.hostinger.com   -Porta 465   -Seguranca ssl|starttls
       -TestarPara alguem@restauracao.org.br   (só testa o envio, sem mudar a configuração: use -SoTestar)

Para ver o que seria feito, sem mudar nada, acrescente -SoVer.
#>
[CmdletBinding()]
param(
    [string]$Caixa = "sistema@restauracao.org.br",
    [string]$Avisos = "financeiro@restauracao.org.br",
    [string]$Endereco = "",
    [string]$Servidor = "smtp.hostinger.com",
    [int]$Porta = 465,
    [ValidateSet("ssl", "starttls")][string]$Seguranca = "ssl",
    [int]$PortaDoSistema = 8000,
    [string]$TestarPara = "",
    [switch]$SoTestar,
    [switch]$SoVer
)
$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $Raiz ".venv\Scripts\python.exe"

function Passo($texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin -and -not $SoVer) { throw "Rode este script como Administrador: botão direito no PowerShell > Executar como administrador." }
if ($SoVer) { Write-Host "(modo -SoVer: nada será alterado)" -ForegroundColor Yellow }
if (-not (Test-Path $venvPy)) { throw "Não achei $venvPy. O sistema foi instalado com implantacao\instalar.ps1 neste computador?" }

if (-not $Endereco) {
    # o endereço deste computador na rede do escritório (a mesma que o instalar.ps1 mostra no fim)
    $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" } |
        Select-Object -First 1 -ExpandProperty IPAddress
    if ($ip) { $Endereco = "http://${ip}:$PortaDoSistema" }
}

Push-Location $Raiz
try {
    if (-not $SoTestar) {
        Passo "Configurando o envio de e-mail"
        Write-Host "    caixa de envio: $Caixa   servidor: ${Servidor}:$Porta ($Seguranca)"
        Write-Host "    avisos para: $Avisos   endereço do sistema nos links: $Endereco"
        if (-not $SoVer) {
            # a senha é pedida pelo próprio comando, escondida (não passa por este script nem pela linha de comando)
            $argumentos = @("-m", "flask", "--app", "app", "configurar-email", "--servidor", $Servidor, "--porta", $Porta, "--seguranca", $Seguranca,
                            "--usuario", $Caixa, "--avisos-para", $Avisos)
            if ($Endereco) { $argumentos += @("--endereco-do-sistema", $Endereco) }
            & $venvPy @argumentos
            if ($LASTEXITCODE) { throw "O comando de configuração falhou." }
        }
    }
    if (-not $TestarPara) { $TestarPara = $Avisos.Split(",")[0].Trim() }
    Passo "Enviando um e-mail de teste para $TestarPara"
    if (-not $SoVer) {
        & $venvPy -m flask --app app testar-email $TestarPara
        if ($LASTEXITCODE) { throw "O e-mail de teste não saiu. Confira a senha da caixa, o servidor e a porta (rode de novo este script)." }
        Write-Host ""
        Write-Host "Pronto. Confira se o e-mail chegou (olhe também o spam)." -ForegroundColor Green
    }
} finally {
    Pop-Location
}
