@echo off
echo ========================================
echo   COMPLETE DEPLOYMENT SCRIPT
echo   Telegram Card Game Bot
echo ========================================
echo.

echo [1/4] Uploading game_core.py...
scp "C:\Users\lenovo\Desktop\card game\game_core.py" root@195.248.243.122:"/root/card game/"
if %errorlevel% neq 0 (
    echo ERROR: Failed to upload game_core.py
    pause
    exit /b 1
)
echo SUCCESS: game_core.py uploaded
echo.

echo [2/4] Uploading web_api.py...
scp "C:\Users\lenovo\Desktop\card game\web_api.py" root@195.248.243.122:"/root/card game/"
if %errorlevel% neq 0 (
    echo ERROR: Failed to upload web_api.py
    pause
    exit /b 1
)
echo SUCCESS: web_api.py uploaded
echo.

echo [3/4] Uploading admin_panel_complete.html...
scp "C:\Users\lenovo\Desktop\card game\admin_panel_complete.html" root@195.248.243.122:"/root/card game/"
if %errorlevel% neq 0 (
    echo ERROR: Failed to upload admin_panel_complete.html
    pause
    exit /b 1
)
echo SUCCESS: admin_panel_complete.html uploaded
echo.

echo [4/4] Restarting services on server...
echo.
echo Please run these commands on the server:
echo.
echo cd "/root/card game"
echo pkill -9 -f telegram_bot.py
echo pkill -9 -f web_api.py
echo nohup python3 telegram_bot.py ^> bot.log 2^>^&1 ^&
echo nohup python3 web_api.py ^> web.log 2^>^&1 ^&
echo tail -f bot.log
echo.
echo ========================================
echo   FILES UPLOADED SUCCESSFULLY!
echo   Now connect to server and restart
echo ========================================
echo.
echo Connect with: ssh root@195.248.243.122
echo.
pause
