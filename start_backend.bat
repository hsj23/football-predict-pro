@echo off
chcp 65001 >nul
title 足彩预测系统 - 后端服务

:: 自动检测实际所在盘符和路径
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
%SCRIPT_DIR:~0,1%:
cd /d "%SCRIPT_DIR%\backend"

echo ========================================================
echo   足彩预测系统 v2.0 - 混合预测引擎
echo   启动时间: %date% %time%
echo   路径: %CD%
echo ========================================================
echo.

echo [1/3] 检查MySQL...
sc query MySQL80 >nul 2>&1
if %errorlevel% equ 0 (
    net start MySQL80 >nul 2>&1
    echo   MySQL80 已启动
) else (
    sc query MySQL >nul 2>&1
    if %errorlevel% equ 0 (
        net start MySQL >nul 2>&1
        echo   MySQL 已启动
    ) else (
        echo   警告: MySQL未找到，预测将使用文件缓存模式
    )
)

echo [2/3] 清理旧进程并启动后端...
:: 清理旧进程
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING" 2^>nul') do taskkill /F /PID %%a >nul 2>&1
timeout /t 1 /nobreak >nul
start /b py -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning > "%SCRIPT_DIR%\logs\backend.log" 2>&1

echo [3/3] 启动完成!
echo.
echo    === 在浏览器中打开 ===
echo    http://localhost:8000/
echo.
echo    === API文档 ===
echo    http://localhost:8000/docs
echo.
echo   关闭此窗口不会影响后台服务
echo   完全停止请用任务管理器结束 python.exe
echo.
pause
