@echo off
chcp 65001 > nul
title 图文转贴图 Web服务
echo ==============================================
echo   社交媒体图文 → 公众号贴图草稿
echo ==============================================
echo.

REM 1. 启动Flask服务器
echo [1/2] 启动Flask服务器（端口5000）...
start "Flask-SocialTietu" /min cmd /c "cd /d C:\Users\83718\.qclaw\workspace\social-to-tietu-web && python server.py"

REM 等3秒让Flask启动
timeout /t 3 > nul

REM 2. 启动cpolar穿透  
echo [2/2] 启动cpolar内网穿透...
start "Cpolar-SocialTietu" /min "C:\Program Files\cpolar\cpolar.exe" http 5000 -log "C:\Users\83718\.qclaw\workspace\social-to-tietu-web\cpolar_run.log" -log-level INFO

echo.
echo 等待cpolar建立隧道（15秒）...
echo.
timeout /t 15 > nul

echo ==============================================
echo   启动完成！
echo ==============================================
echo.
echo   本地访问：
echo     http://127.0.0.1:5000
echo     http://192.168.2.106:5000（局域网用）
echo.
echo   公网地址（用于手机访问）：
echo     正在从日志提取...
echo.

REM 查找cpolar输出的公网地址
if exist "C:\Users\83718\.qclaw\workspace\social-to-tietu-web\cpolar_run.log" (
    echo   cpolar日志内容：
    type "C:\Users\83718\.qclaw\workspace\social-to-tietu-web\cpolar_run.log" 2>nul
) else (
    echo   [提示] 日志尚未生成
    echo.
    echo   请手动打开 cpolar 管理界面查看：
    echo     http://127.0.0.1:4042
    echo     （可能需要登录cpolar账号）
)

echo.
echo ==============================================
echo   使用方式
echo ==============================================
echo.
echo   1. 复制上面的公网地址（如 https://xxx.cpolar.cn）
echo   2. 发到自己微信/手机浏览器打开
echo   3. 粘贴抖音/小红书链接 → 选择公众号 → 一键创建
echo.
echo   [警告] 关闭本窗口不会影响后台服务
echo   [提示] 免费版cpolar地址每次重启会变化
echo ==============================================
pause