@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo.
echo ============================================
echo    Start Public Tunnel (cpolar)
echo ============================================
echo.

python -c "import requests; requests.get('http://127.0.0.1:5000/api/health', timeout=3)" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Server not running! Please run start.bat first
    pause
    exit /b 1
)

echo [1/3] Cleaning old process...
taskkill /f /im cpolar.exe >nul 2>&1

echo [2/3] Starting cpolar...
start "cpolar" /min "C:\Program Files\cpolar\cpolar.exe" http 5000 -log "%TEMP%\cpolar_url.log" -log-level INFO

echo [3/3] Waiting for tunnel (15s)...
timeout /t 15 >nul

echo.
echo ============================================
echo    Public URL:
echo.

if exist "%TEMP%\cpolar_url.log" (
    findstr /C:"Tunnel established" "%TEMP%\cpolar_url.log"
) else (
    echo    Check: http://127.0.0.1:4042
)

echo.
echo    Send this URL to your phone!
echo    Press Ctrl+C to stop tunnel
echo ============================================
pause