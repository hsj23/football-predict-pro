@echo off
chcp 65001 >nul
title Football Predict System

echo Starting Football Predict System...
echo.

taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM py.exe >nul 2>&1
timeout /t 2 /nobreak >nul

cd /d "D:\小黄的助手\足彩预测系统\backend"
start "FootballPredictBackend" cmd /c "py -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo Waiting for server...
ping 127.0.0.1 -n 11 >nul

echo Opening browser...
start "" http://127.0.0.1:8000

echo.
echo System started! http://127.0.0.1:8000
echo Keep the backend window open.
timeout /t 5 /nobreak >nul
exit
