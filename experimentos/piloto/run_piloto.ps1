# Piloto de recuperación de etiquetas (Validat3B).
# Local (sin tokens):        .\run_piloto.ps1
# Remoto, clave oculta:      .\run_piloto.ps1 -Remoto -MaxLlamadas 130 -PedirClave
# Remoto, clave ya en env:   .\run_piloto.ps1 -Remoto -MaxLlamadas 130 [-SoloSeleccion]
# Solo donde difieren:       .\run_piloto.ps1 -Remoto -MaxLlamadas 20 -SoloDiferencias -PedirClave
#                            (lee A y la vista elegida únicamente cuando el selector no eligió A)
param(
    [switch]$Remoto,
    [int]$MaxLlamadas = 0,
    [switch]$SoloSeleccion,
    [switch]$SoloDiferencias,
    [switch]$PedirClave,
    [string]$Datos = (Join-Path $PSScriptRoot '..\..'),
    [string]$Muestra = (Join-Path $PSScriptRoot 'muestra_dev.json'),
    [string]$Salida = (Join-Path $PSScriptRoot 'salida')
)
$ErrorActionPreference = 'Stop'
$py = Join-Path $PSScriptRoot 'piloto_etiquetas.py'
$argv = @($py, '--datos', $Datos, '--muestra', $Muestra, '--salida', $Salida)
$claveTemporal = $false
if ($Remoto) {
    if ($MaxLlamadas -le 0) { throw 'Con -Remoto indica -MaxLlamadas N (N > 0).' }
    if ($PedirClave -and -not $env:FOUNDRY_API_KEY) {
        # La clave solo vive en esta sesión de PowerShell y se borra al terminar; no se muestra ni se escribe a disco.
        $sec = Read-Host 'Clave de Azure AI Foundry (no se muestra ni se guarda)' -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        try { $env:FOUNDRY_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        $claveTemporal = $true
    }
    if (-not $env:FOUNDRY_API_KEY) { throw 'Falta la variable de entorno FOUNDRY_API_KEY (o usa -PedirClave).' }
    $argv += @('--remoto', '--max-llamadas', "$MaxLlamadas")
    if ($SoloSeleccion) { $argv += '--solo-seleccion' }
    if ($SoloDiferencias) { $argv += '--solo-diferencias' }
}
try {
    python @argv
    $codigo = $LASTEXITCODE
}
finally {
    if ($claveTemporal) { Remove-Item env:FOUNDRY_API_KEY -ErrorAction SilentlyContinue }
}
if ($codigo -ne 0) { exit $codigo }
Write-Host "`nResultados en: $Salida  (abrir comparacion_visual.html; tabla_piloto.csv; resumen.md)"
