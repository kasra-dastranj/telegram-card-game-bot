@echo off
cls
echo ========================================
echo   QUICK DEPLOY - Card Game Bot
echo ========================================
echo.

echo Uploading files...
echo.

scp "game_core.py" root@195.248.243.122:"/root/card game/" && echo [OK] game_core.py || echo [FAIL] game_core.py
scp "web_api.py" root@195.248.243.122:"/root/card game/" && echo [OK] web_api.py || echo [FAIL] web_api.py
scp "admin_panel_complete.html" root@195.248.243.122:"/root/card game/" && echo [OK] admin_panel_complete.html || echo [FAIL] admin_panel_complete.html
scp "test_api.html" root@195.248.243.122:"/root/card game/" && echo [OK] test_api.html || echo [FAIL] test_api.html

echo.
echo ========================================
echo   FILES UPLOADED!
echo ========================================
echo.
echo Now run on server:
echo   ssh root@195.248.243.122
echo.
echo Then:
echo   cd "/root/card game"
echo   pkill -9 -f telegram_bot.py
echo   pkill -9 -f web_api.py
echo   nohup python3 telegram_bot.py ^> bot.log 2^>^&1 ^&
echo   nohup python3 web_api.py ^> web.log 2^>^&1 ^&
echo.
echo Access:
echo   Main Panel: http://195.248.243.122:5000/
echo   API Test: http://195.248.243.122:5000/test
echo.
pause
