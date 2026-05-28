@echo off
chcp 65001 > nul
echo ==============================================
echo  Cpolar 穿透启动脚本
echo ==============================================
echo.

REM 等待Flask服务器启动
timeout /t 3 > nul

REM 启动cpolar穿透到5000端口
echo [1/2] 正在启动cpolar http隧道（端口5000）...
start "Cpolar-SocialTietu" /min "C:\Program Files\cpolar\cpolar.exe" http 5000 -log "C:\Users\83718\.qclaw\workspace\social-to-tietu-web\cpolar_run.log" -log-level INFO

echo [2/2] 等待隧道建立（10秒）...
timeout /t 10 > nul

REM 读取日志获取公网地址
echo.
echo ==============================================
echo  公网地址（从日志提取）
echo ==============================================
if exist "C:\Users\83718\.qclaw\workspace\social-to-tietu-web\cpolar_run.log" (
    findstr /C:"http" "C:\Users\83718\.qclaw\workspace\social-to-tietu-web\cpolar_run.log" 2>nul | findstr /V "127.0.0.1" 2>nul
) else (
    echo 日志文件未生成，请手动查看：
    echo   http://127.0.0.1:4042
)

echo.
echo 提示：
echo   - 公网地址在上面的输出中，复制后发给自己
echo   - 免费版cpolar地址每次变化，需重新查看
echo   - 关闭cpolar窗口即停止穿透
echo ==============================================
pause
