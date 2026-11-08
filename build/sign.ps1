# c:\Kortik\Kortik-Listener-App\build\sign.ps1
<#
.SYNOPSIS
    Potpisuje KortikListener.exe i installer Authenticode sertifikatom.

.EXAMPLE
    $env:SIGN_CERT_PATH = "C:\secrets\kortik-ev.pfx"
    $env:SIGN_CERT_PASSWORD = "***"
    .\build\sign.ps1 -Version 0.2.0
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root "build\output\KortikListener\KortikListener.exe"
$installerDir = Join-Path $root "build\output\installer"
$installer = Join-Path $installerDir "KortikListener-$Version-setup.exe"

$signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
if (-not $signtool) {
    $candidates = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "x64" } | Select-Object -First 1
    if ($candidates) { $signtool = $candidates.FullName }
}

if (-not $signtool) { throw "signtool.exe nije pronadjen (Windows SDK)." }
if (-not (Test-Path $exe)) { throw "Nema EXE fajla: $exe" }
if (-not (Test-Path $installer)) { throw "Nema installera: $installer" }
if (-not $env:SIGN_CERT_PATH) { throw "Postavi SIGN_CERT_PATH (putanja do .pfx)." }

foreach ($target in @($exe, $installer)) {
    Write-Host "Potpisujem: $target"
    & $signtool sign /fd SHA256 /td SHA256 /tr $TimestampUrl `
        /f $env:SIGN_CERT_PATH /p $env:SIGN_CERT_PASSWORD `
        /d "Kortik Listener" $target
}

Write-Host "Verifikacija potpisa..."
foreach ($target in @($exe, $installer)) {
    $status = (Get-AuthenticodeSignature -FilePath $target).Status
    Write-Host "  $target -> $status"
    if ($status -ne "Valid") { throw "Potpis nije validan: $target ($status)" }
}

Write-Host "Sledeci korak: python build\make_manifest.py --installer `"$installer`" --version $Version --url https://cdn.kortikbot.xyz/listener/..."
