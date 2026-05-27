@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ============================================
echo    Start Public Tunnel (cpolar)
echo ============================================
echo.

REM Check if server is running
python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=3)" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Server not running! Please run start.bat first
    pause
    exit /b 1
)

echo [1/3] Cleaning old process...
taskkill /f /im cpolar.exe >nul 2>&1
timeout /t 2 >nul

echo [2/3] Starting cpolar tunnel: social-tietu...
start "cpolar" /min "C:\Program Files\cpolar\cpolar.exe" run -config "C:\Users\83718\.cpolar\cpolar.yml" social-tietu

echo [3/3] Waiting for tunnel (20s)...
timeout /t 20 >nul

echo.
echo ============================================
echo    Public URL:
echo.
echo    Open cpolar dashboard to get URL:
echo    http://127.0.0.1:4042
echo.
echo    Or check online at:
echo    https://dashboard.cpolar.com/status
echo.
echo    Send this URL to your phone!
echo    Press Ctrl+C to stop tunnel
echo ============================================
pause
