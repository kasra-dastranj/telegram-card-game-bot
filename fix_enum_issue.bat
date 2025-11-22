@echo off
echo ========================================
echo   Fixing Enum Type Issue
echo ========================================
echo.

echo [1/2] Uploading fixed game_core.py...
scp "C:\Users\lenovo\Desktop\card game\game_core.py" root@195.248.243.122:"/root/card game/"
if %errorlevel% neq 0 (
    echo ERROR: Failed to upload
    pause
    exit /b 1
)

echo [2/2] Restarting bot...
ssh root@195.248.243.122 "cd '/root/card game' && pkill -9 -f telegram_bot.py && sleep 2 && nohup python3 telegram_bot.py > bot.log 2>&1 & && sleep 3 && echo 'Checking logs...' && tail -20 bot.log"

echo.
echo ========================================
echo   Fix Complete!
echo ========================================
echo.
echo Now test /fight in Telegram group!
echo.
pause
