param([string]$Bundle = (Join-Path $PSScriptRoot "output\KortikListener"))
$ErrorActionPreference = "Stop"
$exe = Join-Path $bundle "KortikListener.exe"
$conflictingDll = Join-Path $bundle "_internal\icuuc.dll"
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "Nedostaje $exe"
}
if (Test-Path -LiteralPath $conflictingDll) {
    throw "Build sadrži nekompatibilni icuuc.dll: $conflictingDll"
}
$process = Start-Process -FilePath $exe -ArgumentList "--check-qt" -PassThru -WindowStyle Hidden
if (-not $process.WaitForExit(30000)) {
    Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
    throw "Qt provera nije završena za 30 sekundi."
}
if ($process.ExitCode -ne 0) {
    throw "Qt provera nije uspela (exit $($process.ExitCode))."
}
Write-Host "Qt provera builda je uspešna."
