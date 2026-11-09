<#
.SYNOPSIS
    Pravi Kortik Listener installer (PyInstaller + Inno Setup) i ispiše link.

.EXAMPLE
    .\build\build.ps1 -Version 1.0.0

.EXAMPLE
    # sa potpisanim update manifestom (Ed25519 kljuc iz env-a)
    $env:LISTENER_UPDATE_SIGNING_KEY = "<64 hex>"
    .\build\build.ps1 -Version 1.0.0 -CdnBase "https://cdn.kortikbot.xyz/listener"
#>
[CmdletBinding()]
param(
    [string]$Version = "1.0.0",
    [string]$CdnBase = "",
    [string]$PubKey = "",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# ── Lokalne tajne (van gita) ────────────────────────────────────────────────
$localSecrets = Join-Path $PSScriptRoot "secrets.local.ps1"
if (Test-Path $localSecrets) {
    . $localSecrets
    Write-Host "   ucitan build\secrets.local.ps1"
}

if ($PubKey) { $env:LISTENER_UPDATE_PUBKEY = $PubKey }
if (-not $CdnBase -and $env:LISTENER_CDN_BASE) { $CdnBase = $env:LISTENER_CDN_BASE }

Write-Host "== 1/7 Provera zavisnosti ==" -ForegroundColor Cyan
python -c "import PySide6, aiohttp, cryptography, PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Nedostaju zavisnosti. Pokreni: python -m pip install -r requirements.txt pyinstaller"
}
Write-Host "   python: " -NoNewline
python -c "import sys; print(sys.version.split()[0])"

Write-Host "== 2/7 Testovi ==" -ForegroundColor Cyan
if (-not $SkipTests) {
    python -m unittest discover -s tests -p "test_*.py"
    if ($LASTEXITCODE -ne 0) { throw "Testovi nisu prošli — prekidam build." }
}

Write-Host "== 3/7 Verzija i update kljuc ==" -ForegroundColor Cyan
$env:KORTIK_LISTENER_VERSION = $Version
$env:KORTIK_LISTENER_CHANNEL = "beta"
Set-Content -Path "app\_build_version.txt" -Value $Version -Encoding ascii -NoNewline
Write-Host "   verzija: $Version (beta) — upisana u app\_build_version.txt"

if (-not (Test-Path "app\kws\keywords_kortik.txt")) {
    throw "Nedostaje app\kws\keywords_kortik.txt — .exe ne bi imao wake word."
}

$pubkey = $env:LISTENER_UPDATE_PUBKEY
if ($pubkey) {
    $pubkey = $pubkey.Trim()
    if ($pubkey.Length -ne 64) {
        throw "LISTENER_UPDATE_PUBKEY mora imati 64 hex znaka (dobio $($pubkey.Length)). Generiši: python build\keygen.py"
    }
    if ($pubkey -notmatch '^[0-9a-fA-F]{64}$') {
        throw "LISTENER_UPDATE_PUBKEY mora biti heksadecimalan (0-9, a-f). Ne stavljaj uglaste zagrade <>."
    }
    if ($pubkey -match '^0{64}$') {
        throw @"
LISTENER_UPDATE_PUBKEY je jos uvek placeholder (sve nule) iz secrets.local.ps1.example.
Uradi ovo:
  1) python build\keygen.py
  2) otvori build\secrets.local.ps1 i upisi PUBLIC kljuc u LISTENER_UPDATE_PUBKEY
     (i PRIVATE u LISTENER_UPDATE_SIGNING_KEY)
  3) pokreni build ponovo
"@
    }
    Set-Content -Path "app\update_pubkey.txt" -Value $pubkey -Encoding ascii -NoNewline
    Write-Host "   update kljuc: ugrađen ($($pubkey.Substring(0,8))...)"
} else {
    if (Test-Path "app\update_pubkey.txt") { Remove-Item -Force "app\update_pubkey.txt" }
    Write-Warning "LISTENER_UPDATE_PUBKEY nije postavljen — .exe neće moći da verifikuje ažuriranja."
    Write-Warning "Generiši par ključeva: python build\keygen.py"
}

Write-Host "== 4/7 PyInstaller ==" -ForegroundColor Cyan
python -m PyInstaller build\pyinstaller.spec --noconfirm --clean --distpath build\output --workpath build\work
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller nije uspeo (exit $LASTEXITCODE). Detalji: build\work\KortikListener\warn-KortikListener.txt"
}
if (-not (Test-Path "build\output\KortikListener\KortikListener.exe")) {
    throw "PyInstaller nije napravio KortikListener.exe"
}

Write-Host "== 5/7 Inno Setup ==" -ForegroundColor Cyan
$iscc = $null
$candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe"
)
foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path $candidate)) { $iscc = $candidate; break }
}
if (-not $iscc) {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source }
}
if (-not $iscc) {
    foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, "$env:LOCALAPPDATA\Programs")) {
        if (-not $root -or -not (Test-Path $root)) { continue }
        $found = Get-ChildItem -Path $root -Filter "ISCC.exe" -Recurse -Depth 3 -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($found) { $iscc = $found.FullName; break }
    }
}

$installer = $null
if ($iscc) {
    Write-Host "   koristim: $iscc"
    & $iscc "/DMyAppVersion=$Version" "build\installer.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup nije uspeo (exit $LASTEXITCODE)." }
    $installer = "build\output\installer\KortikListener-$Version-setup.exe"
} else {
    Write-Warning "Inno Setup nije pronađen (https://jrsoftware.org/isdl.php) — preskačem installer."
    Write-Warning "EXE build ostaje u build\output\KortikListener\ i biće zapakovan u ZIP."
}

Write-Host "== 6/7 Update manifest ==" -ForegroundColor Cyan
if ($installer -and (Test-Path $installer) -and $env:LISTENER_UPDATE_SIGNING_KEY -and $CdnBase) {
    python build\make_manifest.py `
        --installer $installer `
        --version $Version `
        --url "$CdnBase/KortikListener-$Version-setup.exe" `
        --notes "Kortik Listener $Version" `
        --out listener_app_manifest.json
    Write-Host "   manifest: listener_app_manifest.json (kopiraj pored backend main.py)"
} else {
    Write-Host "   preskočeno (nema CdnBase ili LISTENER_UPDATE_SIGNING_KEY)"
}

Write-Host ""
Write-Host "== GOTOVO ==" -ForegroundColor Green
Write-Host "EXE       : build\output\KortikListener\KortikListener.exe"
if ($installer -and (Test-Path $installer)) {
    $size = [math]::Round((Get-Item $installer).Length / 1MB, 1)
    Write-Host "Installer : $installer  ($size MB)"
    if ($CdnBase) { Write-Host "Link      : $CdnBase/KortikListener-$Version-setup.exe" }
} else {
    $zip = "build\output\KortikListener-$Version-win64.zip"
    Compress-Archive -Path "build\output\KortikListener\*" -DestinationPath $zip -Force
    Write-Host "ZIP       : $zip  (bez Inno Setup-a)"
}

Write-Host ""
Write-Host "Sledeći koraci:"
Write-Host "  1) upload installer na CDN / GitHub Release"
Write-Host "  2) u frontend .env:  NEXT_PUBLIC_LISTENER_DOWNLOAD_URL=<link>"
Write-Host "                       NEXT_PUBLIC_LISTENER_VERSION=$Version"
Write-Host "  3) manifest (ako je pravljen) kopiraj pored backend main.py"
Write-Host "  4) restartuj frontend (Next.js čita NEXT_PUBLIC_* pri buildu)"
