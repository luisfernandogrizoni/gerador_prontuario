<#
Verificação do servidor (fase 6 do plano de segurança): confere, SEM MUDAR NADA, o que dá para conferir sozinho no computador que guarda o
sistema: disco criptografado, atualizações do Windows, antivírus, firewall, tipo de rede, portas abertas, área de trabalho remota, contas,
entrada automática, relógio, permissões da pasta do sistema, backup e espaço em disco. O que depende do roteador, da sala e da impressora
não dá para conferir daqui: está em implantacao\ROTEIRO-DO-WINDOWS-E-DA-REDE.md.

       powershell -ExecutionPolicy Bypass -File implantacao\verificar-servidor.ps1

Rode como Administrador (sem isso, alguns itens aparecem como "VERIFICAR"). Faça a cada 3 meses: a página inicial avisa quando passar disso.
Cada item sai como  OK  (em ordem),  ATENCAO  (precisa corrigir) ou  VERIFICAR  (confira à mão, o roteiro diz como). O resultado fica em
instance\verificacao_servidor.json (a página inicial lê dali).
#>
[CmdletBinding()]
param(
    [string]$Saida = ""                  # onde gravar o resultado (padrão: instance\verificacao_servidor.json)
)
$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $PSScriptRoot
$instance = Join-Path $Raiz "instance"
if (-not $Saida) { $Saida = Join-Path $instance "verificacao_servidor.json" }

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Write-Host "AVISO: fora do modo Administrador, alguns itens saem como VERIFICAR." -ForegroundColor Yellow }

$itens = New-Object System.Collections.ArrayList
function Item([string]$nome, [string]$situacao, [string]$detalhe, [string]$corrigir = "") {
    [void]$itens.Add([pscustomobject]@{ item = $nome; situacao = $situacao; detalhe = $detalhe; corrigir = $corrigir })
}
function Tentar([string]$nome, [scriptblock]$acao) {
    try { & $acao } catch { Item $nome "VERIFICAR" "não consegui conferir ($($_.Exception.Message.Split("`n")[0]))" "Rode como Administrador, ou confira à mão: veja o roteiro." }
}

# ------------------------------------------------------------------ disco
Tentar "Disco criptografado" {
    $ok = $null
    try {
        $v = Get-CimInstance -Namespace "root/CIMV2/Security/MicrosoftVolumeEncryption" -ClassName Win32_EncryptableVolume -Filter "DriveLetter='$($env:SystemDrive)'" -ErrorAction Stop
        $ok = ($v.ProtectionStatus -eq 1)
    } catch { $ok = $null }
    if ($ok -eq $true) { Item "Disco criptografado" "OK" "O disco do Windows ($($env:SystemDrive)) está protegido (BitLocker ou criptografia de dispositivo)." }
    elseif ($ok -eq $false) { Item "Disco criptografado" "ATENCAO" "O disco do Windows NÃO está criptografado: quem levar o computador (ou só o disco) lê tudo." "Configurações > Privacidade e segurança > Criptografia do dispositivo (Windows 11 Home) ou BitLocker (Pro). Guarde a chave de recuperação em papel, fora do computador." }
    else { Item "Disco criptografado" "VERIFICAR" "Não consegui ler o estado (precisa de Administrador, ou o computador não oferece)." "Configurações > Privacidade e segurança > Criptografia do dispositivo: veja se está ligada." }
}
Tentar "Espaço em disco" {
    $d = Get-PSDrive -Name $env:SystemDrive.TrimEnd(":")
    $livre = [math]::Round($d.Free / 1GB, 1)
    if ($livre -lt 5) { Item "Espaço em disco" "ATENCAO" "Só $livre GB livres no disco do sistema." "Apague o que não precisa: o banco e os backups crescem com o tempo." }
    else { Item "Espaço em disco" "OK" "$livre GB livres." }
}

# ------------------------------------------------------------------ Windows
Tentar "Atualizações do Windows" {
    $servico = Get-Service wuauserv -ErrorAction Stop
    $politica = (Get-ItemProperty "HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" -Name NoAutoUpdate -ErrorAction SilentlyContinue).NoAutoUpdate
    $ultima = Get-HotFix -ErrorAction SilentlyContinue | Where-Object { $_.InstalledOn } | Sort-Object InstalledOn -Descending | Select-Object -First 1
    if ($servico.StartType -eq "Disabled" -or $politica -eq 1) { Item "Atualizações do Windows" "ATENCAO" "As atualizações automáticas estão desligadas." "Configurações > Windows Update: ligue e coloque o horário ativo no expediente (o computador reinicia de madrugada, e o sistema volta sozinho)." }
    elseif ($ultima -and ((Get-Date) - $ultima.InstalledOn).Days -gt 60) { Item "Atualizações do Windows" "ATENCAO" "A última atualização instalada foi em $($ultima.InstalledOn.ToString('dd/MM/yyyy')) (há mais de 60 dias)." "Configurações > Windows Update > Verificar atualizações, e reinicie." }
    else { Item "Atualizações do Windows" "OK" ("Ligadas." + $(if ($ultima) { " Última instalada em $($ultima.InstalledOn.ToString('dd/MM/yyyy'))." } else { "" })) }
}
Tentar "Antivírus" {
    try {
        $m = Get-MpComputerStatus -ErrorAction Stop
        $idade = $m.AntivirusSignatureAge
        if (-not $m.AntivirusEnabled -or -not $m.RealTimeProtectionEnabled) { Item "Antivírus" "ATENCAO" "O Microsoft Defender está desligado ou sem proteção em tempo real." "Segurança do Windows > Proteção contra vírus e ameaças: ligue a proteção em tempo real." }
        elseif ($idade -gt 7) { Item "Antivírus" "ATENCAO" "A lista de vírus do Defender está com $idade dias." "Segurança do Windows > Proteção contra vírus e ameaças > Atualizações de proteção." }
        else { Item "Antivírus" "OK" "Microsoft Defender ligado, lista de vírus de $idade dia(s)." }
    } catch {
        $produtos = @(Get-CimInstance -Namespace "root/SecurityCenter2" -ClassName AntivirusProduct -ErrorAction Stop | ForEach-Object { $_.displayName })
        if ($produtos.Count) { Item "Antivírus" "VERIFICAR" ("O Defender não responde; há outro antivírus: " + ($produtos -join ", ") + ". Confira se está ativo e atualizado.") "Abra o painel do antivírus e veja se está protegendo." }
        else { Item "Antivírus" "ATENCAO" "Não encontrei nenhum antivírus ativo." "Segurança do Windows > Proteção contra vírus e ameaças: ligue o Microsoft Defender." }
    }
}

# ------------------------------------------------------------------ rede
Tentar "Firewall do Windows" {
    $desligados = @(Get-NetFirewallProfile | Where-Object { -not $_.Enabled } | ForEach-Object { $_.Name })
    if ($desligados.Count) { Item "Firewall do Windows" "ATENCAO" ("Desligado em: " + ($desligados -join ", ") + ".") "Segurança do Windows > Firewall e proteção de rede: ligue em todos os perfis." }
    else { Item "Firewall do Windows" "OK" "Ligado nos três perfis (domínio, privado, público)." }
}
Tentar "Tipo de rede" {
    $perfil = Get-NetConnectionProfile | Where-Object { $_.IPv4Connectivity -ne "Disconnected" -or $_.IPv6Connectivity -ne "Disconnected" } | Select-Object -First 1
    if (-not $perfil) { Item "Tipo de rede" "VERIFICAR" "Sem rede conectada agora." }
    elseif ($perfil.NetworkCategory -eq "Public") { Item "Tipo de rede" "VERIFICAR" "A rede '$($perfil.Name)' está como Pública. O sistema funciona, mas os outros computadores podem não achar este pelo nome." "Configurações > Rede e Internet > (a rede) > Tipo de perfil de rede: Privada." }
    else { Item "Tipo de rede" "OK" "A rede '$($perfil.Name)' está como $($perfil.NetworkCategory)." }
}
Tentar "Portas abertas na rede" {
    $arriscadas = @{ 3389 = "área de trabalho remota"; 23 = "telnet"; 21 = "FTP"; 5985 = "gerenciamento remoto (WinRM)"; 5986 = "gerenciamento remoto (WinRM)"; 5900 = "VNC"; 445 = "compartilhamento de arquivos (SMB)"; 139 = "compartilhamento de arquivos (NetBIOS)" }
    $ouvindo = Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalAddress -notin @("127.0.0.1", "::1") } | Sort-Object LocalPort -Unique
    $achadas = @($ouvindo | Where-Object { $arriscadas.ContainsKey([int]$_.LocalPort) })
    $fortes = @($achadas | Where-Object { $_.LocalPort -notin 445, 139 })
    if ($fortes.Count) { Item "Portas abertas na rede" "ATENCAO" ("Abertas para a rede: " + (($fortes | ForEach-Object { "$($_.LocalPort) ($($arriscadas[[int]$_.LocalPort]))" }) -join ", ") + ".") "Desligue o que não usa (Configurações > Sistema > Área de Trabalho Remota; serviços do Windows)." }
    elseif ($achadas.Count) { Item "Portas abertas na rede" "VERIFICAR" "O compartilhamento de arquivos do Windows (portas 445/139) está aberto para a rede. Se este computador não compartilha pastas, é desnecessário." "Painel de Controle > Central de Rede > Alterar configurações de compartilhamento avançado: desligue o compartilhamento de arquivos e impressoras." }
    else { Item "Portas abertas na rede" "OK" ("Nenhuma porta de risco aberta para a rede. Portas ouvindo fora do próprio computador: " + $(if ($ouvindo) { (($ouvindo | Select-Object -ExpandProperty LocalPort -Unique | Sort-Object | Select-Object -First 12) -join ", ") } else { "nenhuma" }) + ".") }
}
Tentar "Área de trabalho remota" {
    $nega = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server" -Name fDenyTSConnections -ErrorAction Stop).fDenyTSConnections
    if ($nega -eq 0) { Item "Área de trabalho remota" "ATENCAO" "A área de trabalho remota (RDP) está LIGADA: é a porta preferida de quem ataca computador de escritório." "Configurações > Sistema > Área de Trabalho Remota: desligue (o acesso de fora é só pelo Tailscale)." }
    else { Item "Área de trabalho remota" "OK" "Desligada." }
}
Tentar "SMB 1 (protocolo antigo)" {
    if ((Get-SmbServerConfiguration -ErrorAction Stop).EnableSMB1Protocol) { Item "SMB 1 (protocolo antigo)" "ATENCAO" "O protocolo SMB1 está ligado (é o que os vírus de rede usam)." "Painel de Controle > Programas > Ativar ou desativar recursos do Windows: desmarque 'Suporte ao compartilhamento de arquivos SMB 1.0/CIFS'." }
    else { Item "SMB 1 (protocolo antigo)" "OK" "Desligado." }
}

# ------------------------------------------------------------------ contas e entrada
Tentar "Contas do Windows" {
    $problemas = New-Object System.Collections.ArrayList
    foreach ($u in (Get-LocalUser | Where-Object { $_.Enabled })) {
        if (-not $u.PasswordRequired) { [void]$problemas.Add("'$($u.Name)' pode entrar sem senha") }
        if ($u.SID.Value -like "*-501") { [void]$problemas.Add("a conta Convidado está ligada") }
    }
    $admins = @(Get-LocalGroupMember -SID "S-1-5-32-544" | Where-Object { $_.ObjectClass -eq "Usuário" -or $_.ObjectClass -eq "User" } | ForEach-Object { $_.Name })
    if ($problemas.Count) { Item "Contas do Windows" "ATENCAO" (($problemas -join "; ") + ".") "Painel de Controle > Contas de Usuário: ponha senha em todas e desligue o Convidado." }
    elseif ($admins.Count -gt 2) { Item "Contas do Windows" "VERIFICAR" ("Há " + $admins.Count + " contas de administrador no Windows: " + ($admins -join ", ") + ". Quanto menos, melhor.") "Deixe só a de quem cuida do computador como administradora; as de uso diário, como contas comuns." }
    else { Item "Contas do Windows" "OK" ("Todas as contas ligadas têm senha; administradores do Windows: " + ($admins -join ", ") + ".") }
}
Tentar "Entrada automática no Windows" {
    $auto = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name AutoAdminLogon -ErrorAction SilentlyContinue).AutoAdminLogon
    if ($auto -eq "1") { Item "Entrada automática no Windows" "ATENCAO" "O Windows entra sozinho na conta ao ligar: quem ligar o computador usa a sessão aberta. O sistema não precisa disso (as tarefas rodam sem ninguém logado)." "Execute netplwiz e marque 'Os usuários devem digitar um nome e uma senha'." }
    else { Item "Entrada automática no Windows" "OK" "Desligada." }
}
Tentar "Bloqueio de tela" {
    $tempo = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name InactivityTimeoutSecs -ErrorAction SilentlyContinue).InactivityTimeoutSecs
    if ($tempo -and $tempo -le 900) { Item "Bloqueio de tela" "OK" "O Windows bloqueia a tela depois de $([math]::Round($tempo / 60)) min sem uso." }
    else { Item "Bloqueio de tela" "VERIFICAR" "Não há tempo de bloqueio de tela definido pela política do Windows." "Configurações > Contas > Opções de entrada > 'Exigir entrada': ao acordar; e Configurações > Sistema > Energia: desligar a tela em 10 min. Ou aperte Win+L ao sair da sala." }
}
Tentar "Relógio (os códigos do autenticador dependem dele)" {
    $s = Get-Service w32time -ErrorAction Stop
    if ($s.Status -ne "Running") { Item "Relógio (os códigos do autenticador dependem dele)" "ATENCAO" "O serviço de hora do Windows está parado: o relógio pode desajustar e os códigos do aplicativo autenticador deixarem de valer." "Configurações > Hora e idioma > Data e hora: ligue 'Definir horário automaticamente' e 'Sincronizar agora'." }
    else { Item "Relógio (os códigos do autenticador dependem dele)" "OK" "Serviço de hora ligado." }
}

# ------------------------------------------------------------------ o sistema
Tentar "Pasta do sistema (instance)" {
    if (-not (Test-Path $instance)) { Item "Pasta do sistema (instance)" "VERIFICAR" "A pasta instance não existe aqui (o sistema está instalado neste computador?)."; return }
    $acl = Get-Acl $instance
    $largos = @($acl.Access | Where-Object { $_.IdentityReference.Value -match "Everyone|Todos|Authenticated Users|Usuários autenticados|BUILTIN\\Users|BUILTIN\\Usuários" -and $_.AccessControlType -eq "Allow" })
    if ($largos.Count) { Item "Pasta do sistema (instance)" "ATENCAO" ("O banco e as chaves estão abertos para: " + (($largos | ForEach-Object { $_.IdentityReference.Value }) -join ", ") + ".") "Rode implantacao\instalar.ps1 de novo (ele fecha a pasta só para o SISTEMA, os administradores e quem instalou)." }
    else { Item "Pasta do sistema (instance)" "OK" "Só o SISTEMA, os administradores e quem instalou alcançam o banco e as chaves." }
}
Tentar "Tarefas do sistema" {
    $tarefas = @(Get-ScheduledTask | Where-Object { $_.TaskName -like "Prontuario*" })
    if (-not $tarefas.Count) { Item "Tarefas do sistema" "VERIFICAR" "Não achei as tarefas 'Prontuario - ...' neste computador."; return }
    $paradas = @($tarefas | Where-Object { $_.State -eq "Disabled" } | ForEach-Object { $_.TaskName })
    if ($paradas.Count) { Item "Tarefas do sistema" "ATENCAO" ("Desativadas: " + ($paradas -join ", ") + ".") "Agendador de Tarefas: ative de novo (ou rode implantacao\instalar.ps1)." }
    else { Item "Tarefas do sistema" "OK" ("$($tarefas.Count) tarefas ativas (rodam como SISTEMA: é o limite conhecido, veja o roteiro).") }
}
Tentar "Backup do dia" {
    $arquivo = Join-Path $instance "ultimo_backup.txt"
    if (-not (Test-Path $arquivo)) { Item "Backup do dia" "ATENCAO" "Nunca rodou (não há registro do último backup)." "Rode implantacao\instalar.ps1 ou python backup.py; confira a tarefa 'Prontuario - backup diario'."; return }
    $quando = [datetime]::Parse((Get-Content $arquivo -Raw).Trim(), [Globalization.CultureInfo]::InvariantCulture)
    $dias = ((Get-Date) - $quando).Days
    if ($dias -gt 3) { Item "Backup do dia" "ATENCAO" "O último backup foi há $dias dias." "Veja logs\backup.log e se o HD externo está ligado." } else { Item "Backup do dia" "OK" "Último backup em $($quando.ToString('dd/MM/yyyy HH:mm'))." }
}
Tentar "Modo de rede do sistema" {
    $modo = "http"
    $arq = Join-Path $instance "rede.json"
    if (Test-Path $arq) { try { $modo = (Get-Content $arq -Raw | ConvertFrom-Json).modo } catch { } }
    if ($modo -eq "https") { Item "Modo de rede do sistema" "OK" "https: o sistema só atende por dentro do Tailscale." }
    elseif ($modo -eq "misto") { Item "Modo de rede do sistema" "VERIFICAR" "misto: http na rede local e https pelo Tailscale (escolha da casa, se for o caso)." "Para só https: implantacao\configurar-https.ps1 -FecharHttp." }
    else { Item "Modo de rede do sistema" "ATENCAO" "http: a senha trafega sem criptografia pela rede do escritório." "Veja a parte 5 do implantacao\LEIA-ME.md (Tailscale)." }
}

# ------------------------------------------------------------------ resultado
Write-Host ""
$cor = @{ OK = "Green"; ATENCAO = "Red"; VERIFICAR = "Yellow" }
foreach ($i in $itens) {
    Write-Host ("[{0,-9}] {1}" -f $i.situacao, $i.item) -ForegroundColor $cor[$i.situacao]
    Write-Host ("            " + $i.detalhe)
    if ($i.situacao -ne "OK" -and $i.corrigir) { Write-Host ("            O que fazer: " + $i.corrigir) -ForegroundColor DarkGray }
}
$contagem = $itens | Group-Object situacao | ForEach-Object { "$($_.Count) $($_.Name)" }
Write-Host ""
Write-Host ("Resumo: " + ($contagem -join ", ") + ".") -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path (Split-Path $Saida) | Out-Null
$json = @{ em = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss"); itens = $itens } | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText($Saida, $json, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Resultado guardado em $Saida (a página inicial lê dali)."
if (@($itens | Where-Object { $_.situacao -eq "ATENCAO" }).Count) { exit 1 }
