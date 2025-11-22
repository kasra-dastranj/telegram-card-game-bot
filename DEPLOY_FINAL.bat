@echo off
cls
echo ========================================
echo   FINAL DEPLOYMENT
echo   Card Game Bot - Complete System
echo ========================================
echo.

echo [1/3] Uploading game_core.py...
scp "game_core.py" root@195.248.243.122:"/root/card game/"
echo.

echo [2/3] Uploading web_api.py...
scp "web_api.py" root@195.248.243.122:"/root/card game/"
echo.

echo [3/3] Uploading admin_panel_final.html...
scp "admin_panel_final.html" root@195.248.243.122:"/root/card game/"
echo.

echo ========================================
echo   ALL FILES UPLOADED!
echo ========================================
echo.
echo Now SSH to server and run:
echo   ssh root@195.248.243.122
echo.
echo Then execute:
echo   cd "/root/card game"
echo   pkill -9 -f telegram_bot.py
echo   pkill -9 -f web_api.py
echo   nohup python3 telegram_bot.py ^> bot.log 2^>^&1 ^&
echo   nohup python3 web_api.py ^> web.log 2^>^&1 ^&
echo   tail -f bot.log
echo.
echo Access panel at:
echo   http://195.248.243.122:5000/
echo.
pause
