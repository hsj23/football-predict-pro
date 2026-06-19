@echo off
echo Killing old backend on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING"') do taskkill /F /PID %%a >nul 2>&1
timeout /t 2 /nobreak >nul

echo Clearing cache...
cd /d "%~dp0backend"
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q *.pyc 2>nul

echo Starting backend...
start "足彩后端" cmd /c "py -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo Waiting...
timeout /t 5 /nobreak >nul

echo Opening browser...
start http://127.0.0.1:8000
echo Done!
pause
