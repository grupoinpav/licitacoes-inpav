# Notificador de Licitações INPAV para Windows
# Confere o painel e mostra uma notificação do Windows para cada licitação nova.
# Roda escondido pelo Agendador de Tarefas (veja instalar.bat).

param([switch]$Teste)

$ErrorActionPreference = "Stop"
$Painel = "https://grupoinpav.github.io/licitacoes-inpav/"
$Dados  = $Painel + "dados/licitacoes.json"
$Pasta  = Join-Path $env:LOCALAPPDATA "LicitacoesINPAV"
$ArqEstado = Join-Path $Pasta "estado.json"
$ArqLog    = Join-Path $Pasta "log.txt"
$DiasAvisoPrazo = 2      # avisa quando faltar até 2 dias para encerrar
$MaxIndividuais = 4      # acima disso, manda um resumo só

New-Item -ItemType Directory -Force -Path $Pasta | Out-Null

function Log($msg) {
    $linha = "{0:dd/MM/yyyy HH:mm} {1}" -f (Get-Date), $msg
    Add-Content -Path $ArqLog -Value $linha -Encoding UTF8
    # mantém o log pequeno
    $l = Get-Content $ArqLog -Encoding UTF8
    if ($l.Count -gt 300) { $l[-200..-1] | Set-Content $ArqLog -Encoding UTF8 }
}

function Esc($t) { [System.Security.SecurityElement]::Escape([string]$t) }

function Avisar([string]$titulo, [string]$linha1, [string]$linha2, [string]$link) {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
    if (-not $link) { $link = $Painel }
    $xml = @"
<toast activationType="protocol" launch="$(Esc $link)" duration="long">
  <visual><binding template="ToastGeneric">
    <text>$(Esc $titulo)</text>
    <text>$(Esc $linha1)</text>
    <text>$(Esc $linha2)</text>
  </binding></visual>
  <actions>
    <action content="Abrir painel" activationType="protocol" arguments="$(Esc $Painel)"/>
    $(if ($link -ne $Painel) { "<action content=`"Ver edital`" activationType=`"protocol`" arguments=`"$(Esc $link)`"/>" })
  </actions>
  <audio src="ms-winsoundevent:Notification.Default"/>
</toast>
"@
    $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
    $doc.LoadXml($xml)
    $toast = New-Object Windows.UI.Notifications.ToastNotification $doc
    $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
}

function Valor($v) {
    if (-not $v) { return "valor não informado" }
    $c = [Globalization.CultureInfo]::GetCultureInfo("pt-BR")
    $txt = ([double]$v).ToString("C2", $c)
    if ($v -ge 1e6) { $txt += " (≈ " + ([double]$v / 1e6).ToString("0.#", $c) + " mi)" }
    elseif ($v -ge 1e3) { $txt += " (≈ " + ([double]$v / 1e3).ToString("0", $c) + " mil)" }
    return $txt
}

function Prazo($l) {
    $p = if ($l.encerramento) { $l.encerramento } else { $l.abertura }
    if (-not $p) { return $null }
    if ($p -is [datetime]) { return $p }
    try { return [datetime]::Parse([string]$p, [Globalization.CultureInfo]::InvariantCulture) } catch { return $null }
}

function Curto([string]$t, [int]$n) {
    $t = ($t -replace '\s+', ' ').Trim()
    if ($t.Length -gt $n) { return $t.Substring(0, $n - 1) + "…" }
    return $t
}

if ($Teste) {
    Avisar "Licitações INPAV" "Notificações ativadas neste computador." "Você será avisado quando surgirem licitações novas." $Painel
    exit 0
}

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $resp = Invoke-WebRequest -Uri ($Dados + "?t=" + [DateTime]::Now.Ticks) -UseBasicParsing -TimeoutSec 60
    $texto = [Text.Encoding]::UTF8.GetString($resp.RawContentStream.ToArray())
    $json = $texto | ConvertFrom-Json
} catch {
    Log "sem conexão com o painel: $($_.Exception.Message)"
    exit 0
}

$agora = Get-Date
$lista = @($json.licitacoes)
$abertas = @($lista | Where-Object { $p = Prazo $_; (-not $p) -or ($p -ge $agora) })

# estado: ids já avisados e prazos já lembrados
$estado = @{ vistos = @(); prazos = @() }
if (Test-Path $ArqEstado) {
    try {
        $e = Get-Content $ArqEstado -Raw -Encoding UTF8 | ConvertFrom-Json
        $estado.vistos = @($e.vistos); $estado.prazos = @($e.prazos)
    } catch { }
}
$primeiraVez = -not (Test-Path $ArqEstado)
$vistos = New-Object 'System.Collections.Generic.HashSet[string]'
$estado.vistos | ForEach-Object { [void]$vistos.Add([string]$_) }
$prazos = New-Object 'System.Collections.Generic.HashSet[string]'
$estado.prazos | ForEach-Object { [void]$prazos.Add([string]$_) }

$novas = @($abertas | Where-Object { -not $vistos.Contains([string]$_.id) })

if ($primeiraVez) {
    Avisar "Licitações INPAV: monitor ativado" "$($abertas.Count) licitações abertas agora no painel." "A partir de agora você recebe um aviso a cada licitação nova." $Painel
    Log "primeira execução: $($abertas.Count) abertas marcadas como vistas"
}
elseif ($novas.Count -gt $MaxIndividuais) {
    $soma = 0; foreach ($n in $novas) { if ($n.valor) { $soma += [double]$n.valor } }
    $muns = ($novas | ForEach-Object { $_.municipio } | Select-Object -Unique) -join ", "
    Avisar "$($novas.Count) licitações novas" (Curto "Municípios: $muns" 120) ("Soma: " + (Valor $soma)) ($Painel + "?novas=1")
    Log "$($novas.Count) novas (resumo)"
}
else {
    foreach ($l in $novas) {
        $p = Prazo $l
        $quando = if ($p) { "Abertura: " + $p.ToString("dd/MM 'às' HH:mm") } else { "Data: ver edital" }
        $titulo = "Nova licitação · $($l.municipio) · $($l.forma)"
        Avisar $titulo (Curto $l.objeto 150) ("$(Valor $l.valor) · $quando") $l.link
        Log "nova: $($l.municipio) - $(Curto $l.objeto 80)"
        Start-Sleep -Milliseconds 800
    }
}

# lembrete de prazo (uma vez por licitação)
if (-not $primeiraVez) {
    foreach ($l in $abertas) {
        $p = Prazo $l
        if (-not $p) { continue }
        $dias = ($p.Date - $agora.Date).Days
        if ($dias -le $DiasAvisoPrazo -and -not $prazos.Contains([string]$l.id)) {
            $txt = if ($dias -le 0) { "ENCERRA HOJE" } elseif ($dias -eq 1) { "encerra AMANHÃ" } else { "encerra em $dias dias" }
            Avisar "Prazo: $($l.municipio) $txt" (Curto $l.objeto 150) ("$(Valor $l.valor) · " + $p.ToString("dd/MM 'às' HH:mm")) $l.link
            [void]$prazos.Add([string]$l.id)
            Log "prazo: $($l.municipio) $txt"
            Start-Sleep -Milliseconds 800
        }
    }
}

# salva estado (só ids que ainda existem no painel, para não crescer sem fim)
$idsAtuais = New-Object 'System.Collections.Generic.HashSet[string]'
$lista | ForEach-Object { [void]$idsAtuais.Add([string]$_.id) }
$abertas | ForEach-Object { [void]$vistos.Add([string]$_.id) }
@{
    vistos = @($vistos | Where-Object { $idsAtuais.Contains($_) })
    prazos = @($prazos | Where-Object { $idsAtuais.Contains($_) })
    atualizado = $agora.ToString("s")
} | ConvertTo-Json | Set-Content -Path $ArqEstado -Encoding UTF8
