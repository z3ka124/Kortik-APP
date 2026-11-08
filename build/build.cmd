@echo off
REM c:\Kortik\Kortik-Listener-App\build\build.cmd
REM Pokrece build.ps1 iz obicnog cmd.exe (bez menjanja ExecutionPolicy).
REM Koriscenje:  build\build.cmd -Version 1.0.0
setlocal

set "SCRIPT=%~dp0build.ps1"
if not exist "%SCRIPT%" (
    echo [GRESKA] Ne nalazim "%SCRIPT%"
    exit /b 1
)

where pwsh >nul 2>nul
if %errorlevel%==0 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
)

exit /b %errorlevel%
