@echo off
echo ========================================
echo   Quick Deploy to Server
echo ========================================
echo.

echo [1/3] Uploading web_api.py...
scp "C:\Users\lenovo\Desktop\card game\web_api.py" root@195.248.243.122:"/root/card game/"
if %errorlevel% neq 0 (
    echo ERROR: Failed to upload web_api.py
    pause
    exit /b 1
)

echo [2/3] Uploading admin_panel_offline.html...
scp "C:\Users\lenovo\Desktop\card game\admin_panel_offline.html" root@195.248.243.122:"/root/card game/"
if %errorlevel% neq 0 (
    echo ERROR: Failed to upload admin_panel_offline.html
    pause
    exit /b 1
)

echo [3/3] Restarting services on server...
ssh root@195.248.243.122 "cd '/root/card game' && pkill -9 -f web_api.py && pkill -9 -f telegram_bot.py && nohup python3 web_api.py > web_api.log 2>&1 & && sleep 2 && nohup python3 telegram_bot.py > bot.log 2>&1 & && echo 'Services restarted successfully!'"

echo.
echo ========================================
echo   Deployment Complete!
echo ========================================
echo.
echo Admin Panel: http://195.248.243.122:5000
echo.
pause
