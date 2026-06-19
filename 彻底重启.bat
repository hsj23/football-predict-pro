@echo off
echo ============================================
echo  Step 1: Killing process on port 8000
echo ============================================
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING"') do (
    echo Killing PID %%a on port 8000
    taskkill /F /PID %%a 2>nul
)
echo Waiting 3 seconds...
timeout /t 3 /nobreak >nul

echo.
echo ============================================
echo  Step 2: Checking port 8000
echo ============================================
netstat -ano | findstr ":8000"
if %errorlevel% equ 0 (
    echo WARNING: Port 8000 still in use! Trying harder...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING"') do (
        echo Killing PID %%a
        taskkill /F /PID %%a 2>nul
    )
    timeout /t 2 /nobreak >nul
) else (
    echo Port 8000 is FREE
)

echo.
echo ============================================
echo  Step 3: Clearing Python cache
echo ============================================
cd /d "%~dp0backend"
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q *.pyc 2>nul
echo Cache cleared

echo.
echo ============================================
echo  Step 4: Verifying predict.py has v3-urllib
echo ============================================
findstr "v3-urllib" "app\api\predict.py"
if %errorlevel% equ 0 (
    echo [OK] predict.py has v3-urllib marker
) else (
    echo [ERROR] predict.py does NOT have v3-urllib marker!
)

echo.
echo ============================================
echo  Step 5: Starting backend
echo ============================================
start "足彩后端" cmd /c "py -m uvicorn app.main:app --host 127.0.0.1 --port 8000 2>&1"
echo Backend starting...

echo.
echo ============================================
echo  Step 6: Waiting for backend
echo ============================================
set /a WAIT=0
:LOOP
timeout /t 2 /nobreak >nul
set /a WAIT+=1
curl -s http://127.0.0.1:8000/health >nul 2>&1
if %errorlevel% equ 0 goto READY
if %WAIT% geq 10 goto TIMEOUT
goto LOOP

:READY
echo Backend is READY!
start http://127.0.0.1:8000
goto END

:TIMEOUT
echo WARNING: Backend may not have started. Check the black window for errors.

:END
echo.
pause
