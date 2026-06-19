@echo off
chcp 65001 >nul
echo Stopping backend...
taskkill /IM python.exe /F 2>nul
taskkill /IM pythonw.exe /F 2>nul
timeout /t 3 >nul

echo Clearing cache...
for /d /r "backend" %%i in (__pycache__) do @rmdir /s /q "%%i" 2>nul
del /s /q "backend\*.pyc" 2>nul

echo Starting backend...
cd backend
start "" py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd ..

echo Waiting for server...
timeout /t 5 >nul

echo Done! Server should be running on http://127.0.0.1:8000
pause
