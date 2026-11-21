# Levanta la API (server.py) en este PC y la publica en https://api.jamp.digital con el túnel de Cloudflare.
# Uso (desde validat3b):  $env:FOUNDRY_API_KEY = "<api-key>";  .\iniciar_publico.ps1   [-NoLlm]
# Ctrl+C detiene el túnel y la API.
param([switch]$NoLlm)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Token de la API: la API queda en internet, así que siempre se exige X-Api-Key. Se genera una vez en .env (ignorado por git).
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) { "VALIDAT3B_TOKEN=" + [guid]::NewGuid().ToString("N") | Set-Content $envFile -Encoding ascii }
foreach ($l in Get-Content $envFile) { if ($l -match '^\s*([A-Z0-9_]+)=(.+)$') { Set-Item "env:$($Matches[1])" $Matches[2].Trim() } }
if (-not $env:VALIDAT3B_TOKEN) { throw "Falta VALIDAT3B_TOKEN en $envFile" }
if (-not $NoLlm -and -not $env:FOUNDRY_API_KEY) { throw "Define FOUNDRY_API_KEY (o usa -NoLlm)." }

$serverArgs = @("server.py") + $(if ($NoLlm) { @("--no-llm") } else { @() })
$server = Start-Process python -ArgumentList $serverArgs -PassThru -NoNewWindow
$ErrorActionPreference = "Continue"  # cloudflared escribe sus logs en stderr; con "Stop" PowerShell 5.1 los toma como error
try {
    & "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel run validat3b
} finally {
    Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
}
