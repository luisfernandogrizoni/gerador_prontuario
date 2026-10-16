<#
Liga o HTTPS do sistema pelo Tailscale (fase 4 do plano de segurança: docs\plano-de-seguranca.md). Rode como Administrador, neste
computador (o servidor), DEPOIS de instalar o Tailscale, entrar na sua conta e ligar o HTTPS no painel (veja implantacao\LEIA-ME.md, parte 5).

  1) Primeira vez, sem risco (o endereço de hoje, http://IP:8000, continua funcionando para quem ainda não migrou):

       powershell -ExecutionPolicy Bypass -File implantacao\configurar-https.ps1

  2) Quando TODOS os computadores e celulares já usam o endereço novo (https://...ts.net), feche o http da rede local:

       powershell -ExecutionPolicy Bypass -File implantacao\configurar-https.ps1 -FecharHttp

  3) Para voltar ao que era (http na rede local, sem HTTPS):

       powershell -ExecutionPolicy Bypass -File implantacao\configurar-https.ps1 -Desfazer

Para ver o que seria feito, sem mudar nada, acrescente -SoVer.

O que o script faz (modo "misto"; com -FecharHttp, "https"):
  - confere que o Tailscale está conectado, que o HTTPS está ligado no painel e descobre o nome do computador (algo.tailXXXX.ts.net);
  - liga o "Tailscale Serve": o HTTPS do nome acima passa a entregar o sistema (o certificado é do Tailscale e se renova sozinho);
  - grava instance\rede.json (o modo) e religa o sistema;
  - passa o endereço novo para os links dos e-mails ("esqueci minha senha");
  - testa o endereço novo (https) a partir deste computador;
  - com -FecharHttp: o sistema deixa de escutar na rede local (só atende pelo Tailscale), o cookie do login passa a ser só-HTTPS, o
    navegador passa a exigir HTTPS neste endereço e a regra do firewall da porta é removida.
#>
[CmdletBinding()]
param(
    [switch]$FecharHttp,
    [switch]$Desfazer,
    [int]$Porta = 8000,
    [string]$Tailscale = "",           # caminho do tailscale.exe, se o script não achar sozinho
    [switch]$SoVer
)
$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $Raiz ".venv\Scripts\python.exe"
$instance = Join-Path $Raiz "instance"
$NomeServidor = "Prontuario - servidor"
$NomeRegra = "Prontuario (porta $Porta)"

function Passo($texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }
function Aviso($texto) { Write-Host "    AVISO: $texto" -ForegroundColor Yellow }
function Fazer($descricao, [scriptblock]$acao) {
    Write-Host "    - $descricao"
    if (-not $SoVer) { & $acao }
}

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin -and -not $SoVer) { throw "Rode este script como Administrador: botão direito no PowerShell > Executar como administrador." }
if ($SoVer) { Write-Host "(modo -SoVer: nada será alterado)" -ForegroundColor Yellow }
if (-not (Test-Path $venvPy)) { throw "Não achei $venvPy. O sistema foi instalado com implantacao\instalar.ps1 neste computador?" }

function Nativo([string]$Exe, [string[]]$Argumentos) {
    # roda um programa e devolve o código de saída e o texto (stdout e stderr). No PowerShell 5.1, texto no stderr de um programa vira erro
    # fatal quando $ErrorActionPreference = "Stop": aqui isso fica desligado só durante a chamada.
    $antes = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $saida = & $Exe @Argumentos 2>&1 | ForEach-Object { "$_" } | Out-String
        $codigo = $LASTEXITCODE
    } finally { $ErrorActionPreference = $antes }
    return [pscustomobject]@{ Codigo = $codigo; Saida = $saida.Trim() }
}

function Gravar-Modo($modo) {
    # sem BOM: o sistema lê com ou sem, mas assim o arquivo fica igual em qualquer versão do PowerShell
    $texto = (@{ modo = $modo } | ConvertTo-Json -Compress)
    [System.IO.File]::WriteAllText((Join-Path $instance "rede.json"), $texto, (New-Object System.Text.UTF8Encoding($false)))
}

function Religar-Sistema {
    Fazer "religar o sistema (tarefa '$NomeServidor')" {
        Stop-ScheduledTask -TaskName $NomeServidor -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        Start-ScheduledTask -TaskName $NomeServidor
    }
}

function Esperar-Sistema($url) {
    for ($i = 0; $i -lt 40; $i++) {
        try { if ((Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) { return $true } } catch { Start-Sleep -Milliseconds 750 }
    }
    return $false
}

# ------------------------------------------------------------------ achar o tailscale
function Achar-Tailscale {
    if ($Tailscale) { return $Tailscale }
    $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($c in @("$env:ProgramFiles\Tailscale\tailscale.exe", "${env:ProgramFiles(x86)}\Tailscale\tailscale.exe")) { if (Test-Path $c) { return $c } }
    return ""
}

# ------------------------------------------------------------------ desfazer
if ($Desfazer) {
    Passo "Voltando ao http na rede local"
    $ts = Achar-Tailscale
    if ($ts) { Fazer "desligar o HTTPS do Tailscale Serve" { Nativo $ts @("serve", "--https=443", "off") | Out-Null } }
    Fazer "apagar instance\rede.json (volta o modo http)" { Remove-Item (Join-Path $instance "rede.json") -ErrorAction SilentlyContinue }
    Fazer "liberar a porta $Porta só para a rede local (regra '$NomeRegra')" {
        Remove-NetFirewallRule -DisplayName $NomeRegra -ErrorAction SilentlyContinue
        New-NetFirewallRule -DisplayName $NomeRegra -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Porta -RemoteAddress LocalSubnet -Profile Any | Out-Null
    }
    Fazer "voltar os links dos e-mails para o endereço da rede local" {
        $ip = (Nativo $venvPy @("-c", "import servidor; print(servidor.endereco_na_rede())")).Saida
        if ($ip) { Nativo $venvPy @("-m", "flask", "--app", "app", "endereco-do-sistema", "http://${ip}:$Porta") | Out-Null }
    }
    Religar-Sistema
    Write-Host ""
    Write-Host "Pronto: o sistema voltou a atender em http://IP:$Porta na rede local. Se algum navegador insistir em https, é o HSTS: use o endereço antigo com http://." -ForegroundColor Green
    return
}

# ------------------------------------------------------------------ conferir o tailscale
Passo "Conferindo o Tailscale"
$ts = Achar-Tailscale
if (-not $ts) { throw "Não achei o Tailscale neste computador. Instale em tailscale.com/download (Windows), entre na conta e rode este script de novo. Passo a passo: implantacao\LEIA-ME.md, parte 5." }
Write-Host "    tailscale: $ts"
$bruto = & $ts status --json
if ($LASTEXITCODE) { throw "O Tailscale não respondeu. Abra o Tailscale (ícone perto do relógio) e entre na conta." }
$st = $bruto | ConvertFrom-Json
if ($st.BackendState -ne "Running") { throw "O Tailscale não está conectado (situação: $($st.BackendState)). Abra o Tailscale, entre na conta e rode este script de novo." }
$nome = ([string]$st.Self.DNSName).TrimEnd(".")
if (-not $nome) { throw "Este computador ainda não tem nome na rede do Tailscale. No painel (login.tailscale.com/admin/dns), ligue o MagicDNS." }
if ($st.PSObject.Properties.Name -contains "CertDomains") {
    if (-not $st.CertDomains -or ($st.CertDomains -notcontains $nome)) {
        throw "O HTTPS ainda não está ligado na sua conta do Tailscale. No painel (login.tailscale.com/admin/dns), em 'HTTPS Certificates', clique em 'Enable HTTPS', e rode este script de novo."
    }
}
Write-Host "    nome deste computador na rede: $nome"
Write-Host "    endereço do sistema:           https://$nome"

# ------------------------------------------------------------------ ligar
Passo "Ligando o HTTPS"
Fazer "deixar o Tailscale rodando mesmo sem ninguém logado no Windows (para o sistema voltar sozinho depois de reiniciar)" {
    $r = Nativo $ts @("set", "--unattended=true")
    if ($r.Codigo) { Aviso "não consegui ligar o modo 'Run unattended'. Clique com o botão direito no ícone do Tailscale > Preferences > Run unattended. ($($r.Saida))" }
}
Fazer "Tailscale Serve: https://$nome  ->  http://127.0.0.1:$Porta (o certificado é do Tailscale e se renova sozinho)" {
    $r = Nativo $ts @("serve", "--bg", "--https=443", "http://127.0.0.1:$Porta")
    if ($r.Codigo) { throw "O Tailscale Serve não ligou: $($r.Saida)`nSe a mensagem trouxer um endereço (login.tailscale.com/...), abra-o, autorize e rode este script de novo." }
}
$modo = if ($FecharHttp) { "https" } else { "misto" }
if ($FecharHttp -and -not $SoVer) {
    # antes de fechar o http, o endereço novo precisa estar funcionando: senão o sistema ficaria inacessível
    Write-Host "    - conferindo o endereço novo antes de fechar o http da rede local"
    if (-not (Esperar-Sistema "http://127.0.0.1:$Porta/login")) { throw "O sistema não responde em http://127.0.0.1:$Porta. Nada foi alterado no modo de rede." }
    try { $r = Invoke-WebRequest "https://$nome/login" -UseBasicParsing -TimeoutSec 25; if ($r.StatusCode -ne 200) { throw "situação $($r.StatusCode)" } }
    catch { throw "O endereço https://$nome não abriu a partir deste computador ($($_.Exception.Message)). O http da rede local NÃO foi fechado. Confira o Tailscale e tente de novo." }
}
Fazer "gravar o modo '$modo' em instance\rede.json" { Gravar-Modo $modo }
Fazer "passar o endereço novo para os links dos e-mails" {
    $r = Nativo $venvPy @("-m", "flask", "--app", "app", "endereco-do-sistema", "https://$nome")
    if ($r.Codigo) { Aviso "o e-mail ainda não foi configurado: quando configurar (implantacao\configurar-email.ps1), rode: flask --app app endereco-do-sistema https://$nome" }
    else { Write-Host "      $($r.Saida)" }
}
if ($FecharHttp) {
    Fazer "fechar a porta $Porta do firewall (o sistema só atende por dentro do Tailscale)" { Remove-NetFirewallRule -DisplayName $NomeRegra -ErrorAction SilentlyContinue }
}
Religar-Sistema

# ------------------------------------------------------------------ conferir
Passo "Conferindo"
if (-not $SoVer) {
    if (-not (Esperar-Sistema "http://127.0.0.1:$Porta/login")) { Aviso "o sistema ainda não respondeu em http://127.0.0.1:$Porta. Veja C:\prontuario\logs\servidor.log." }
    try {
        $r = Invoke-WebRequest "https://$nome/login" -UseBasicParsing -TimeoutSec 25
        if ($r.StatusCode -eq 200) { Write-Host "    https://$nome abriu neste computador (certificado válido)." -ForegroundColor Green } else { Aviso "https://$nome respondeu com a situação $($r.StatusCode)." }
    } catch {
        Aviso "https://$nome não abriu a partir deste computador: $($_.Exception.Message). Confira o Tailscale e tente de novo; o endereço antigo continua valendo."
    }
}
Write-Host ""
Write-Host "Endereço do sistema:  https://$nome" -ForegroundColor Green
if ($FecharHttp) {
    Write-Host "O http da rede local está FECHADO: quem não tem o Tailscale não abre mais o sistema."
} else {
    Write-Host "O endereço antigo (http://IP:$Porta) continua funcionando enquanto você migra os computadores. Quando todos usarem o novo, rode de novo com -FecharHttp."
}
Write-Host "Confira: depois de entrar, abra Cadastros > Auditoria. Na coluna do endereço deve aparecer um número 100.x.x.x (o aparelho de quem entrou), não 127.0.0.1."
