@echo off
chcp 65001 >nul 2>nul
title 图文转贴图

REM ====== 设置Python UTF-8模式 ======
set PYTHONIOENCODING=utf-8:surrogateescape
set PYTHONUTF8=1

REM 切换到脚本所在目录
pushd "%~dp0"

echo ============================================
echo   图文转贴图 - 启动中...
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    pause
    exit /b 1
)

echo [INFO] Starting server on http://127.0.0.1:5000
echo [INFO] Open: http://127.0.0.1:5000
echo.

REM 启动Flask
python server.py
pause
