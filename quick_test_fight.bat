@echo off
echo ========================================
echo   Testing Fight Issue
echo ========================================
echo.

echo [1/2] Uploading test script...
scp "C:\Users\lenovo\Desktop\card game\test_fight_issue.py" root@195.248.243.122:"/root/card game/"
if %errorlevel% neq 0 (
    echo ERROR: Failed to upload test script
    pause
    exit /b 1
)

echo [2/2] Running test on server...
echo.
ssh root@195.248.243.122 "cd '/root/card game' && python3 test_fight_issue.py"

echo.
echo ========================================
echo   Test Complete
echo ========================================
echo.
echo Next steps:
echo 1. Check the output above for warnings
echo 2. Follow recommendations in FIX_FIGHT_ISSUE.md
echo 3. Test /fight command in Telegram group
echo.
pause
