@echo off
echo ========================================
echo   Quick Fix for Fight Command
echo ========================================
echo.

echo [1/3] Uploading fixed game_core.py...
scp "C:\Users\lenovo\Desktop\card game\game_core.py" root@195.248.243.122:"/root/card game/"
if %errorlevel% neq 0 (
    echo ERROR: Failed to upload
    pause
    exit /b 1
)

echo [2/3] Restarting bot on server...
ssh root@195.248.243.122 "cd '/root/card game' && pkill -9 -f telegram_bot.py && sleep 2 && nohup python3 telegram_bot.py > bot.log 2>&1 & && echo 'Bot restarted!'"

echo [3/3] Checking status...
timeout /t 3 >nul
ssh root@195.248.243.122 "cd '/root/card game' && ps aux | grep telegram_bot | grep -v grep && echo '' && echo 'Checking last 10 lines of log:' && tail -10 bot.log"

echo.
echo ========================================
echo   Fix Complete!
echo ========================================
echo.
echo Now test /fight in your Telegram group!
echo.
pause
