@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo  NGO Databank Mobile — choose Backoffice URL
echo  (writes BACKEND_URL + FRONTEND_URL=https://website-databank.fly.dev into MobileApp\.env)
echo.

echo  Backoffice (Flask / API^):
echo    1^) https://databank.ifrc.org              (IFRC production — default prod API host^)
echo    2^) https://databank-stage.ifrc.org          (IFRC staging^)
echo    3^) https://backoffice-databank.fly.dev     (Fly.io preview — not the same as 1^)
echo    4^) http://10.0.2.2:5000   (Android emulator: host machine localhost:5000)
echo    5^) http://localhost:5000   (USB phone: adb reverse tcp:5000 tcp:5000 first^)
echo    6^) Custom URL
echo.
set /p "BO_CHOICE=  Choice [1-6]: "

set "BACKEND_URL="
if "!BO_CHOICE!"=="1" set "BACKEND_URL=https://databank.ifrc.org"
if "!BO_CHOICE!"=="2" set "BACKEND_URL=https://databank-stage.ifrc.org"
if "!BO_CHOICE!"=="3" set "BACKEND_URL=https://backoffice-databank.fly.dev"
if "!BO_CHOICE!"=="4" set "BACKEND_URL=http://10.0.2.2:5000"
if "!BO_CHOICE!"=="5" set "BACKEND_URL=http://localhost:5000"
if "!BO_CHOICE!"=="6" (
  set /p "BACKEND_URL=  Enter backoffice URL: "
)

if not defined BACKEND_URL (
  echo  Invalid or empty choice. Exiting.
  exit /b 1
)

set "FRONTEND_URL=https://website-databank.fly.dev"

echo.
echo  BACKEND_URL=!BACKEND_URL!
echo  FRONTEND_URL=!FRONTEND_URL! ^(fixed^)
echo.

REM Merge into .env (preserve other keys; replace BACKEND_URL / FRONTEND_URL)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$envFile = Join-Path (Get-Location) '.env';" ^
  "$b = $env:BACKEND_URL.Trim().TrimEnd('/');" ^
  "$f = $env:FRONTEND_URL.Trim().TrimEnd('/');" ^
  "$lines = @();" ^
  "if (Test-Path $envFile) { $lines = @(Get-Content -LiteralPath $envFile -Encoding UTF8 | Where-Object { $_ -notmatch '^(BACKEND_URL|FRONTEND_URL)=' }) };" ^
  "$lines += ('BACKEND_URL=' + $b);" ^
  "$lines += ('FRONTEND_URL=' + $f);" ^
  "Set-Content -LiteralPath $envFile -Value $lines -Encoding UTF8;"

if errorlevel 1 (
  echo  Failed to update .env
  exit /b 1
)

echo  Updated .env
echo.
echo  Starting Flutter (default org profile: IFRC). Extra args: %*
echo.

flutter run %*

endlocal
exit /b %ERRORLEVEL%
