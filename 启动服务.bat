@echo off
chcp 65001 >nul
title 足彩预测系统 - 启动中...

echo ============================================
echo    足彩预测系统 - 服务启动脚本
echo ============================================
echo.

:: 1. 启动 MySQL 服务
echo [1/3] 检查 MySQL 服务...
sc query MySQL57 | find "RUNNING" >nul
if %errorlevel% neq 0 (
    echo   正在启动 MySQL57 服务...
    net start MySQL57 2>nul
    if %errorlevel% neq 0 (
        echo   [错误] MySQL 启动失败，请检查 MySQL 是否安装
        pause
        exit /b 1
    )
    echo   MySQL 已启动
) else (
    echo   MySQL 已在运行中
)

:: 2. 停止旧的后端进程
echo.
echo [2/3] 清理旧进程并启动后端...
:: 只清理占用8000端口的进程（不误杀其他Python程序）
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING" 2^>nul') do (
    echo   清理端口8000占用 PID=%%a
    taskkill /F /PID %%a 2>nul
)
timeout /t 1 /nobreak >nul

:: 3. 启动后端
cd /d "D:\小黄的助手\足彩预测系统\backend"
start "" py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd /d "D:\小黄的助手\足彩预测系统"

:: 4. 等待服务就绪
echo   等待服务启动...
set /a count=0
:wait_loop
timeout /t 1 >nul
set /a count+=1
curl -s http://127.0.0.1:8000/health 2>nul | find "healthy" >nul
if %errorlevel% equ 0 goto success
if %count% lss 30 goto wait_loop

echo   [警告] 服务启动超时，请手动检查
goto done

:success
echo   后端服务已就绪 ✓

:: 5. 打开浏览器
echo.
echo [3/3] 打开浏览器...
start "" http://127.0.0.1:8000/

:done
echo.
echo ============================================
echo   服务地址: http://127.0.0.1:8000
echo   管理后台: http://127.0.0.1:8000/admin.html
echo   桌面挂件: http://127.0.0.1:8000/desktop_widget.html
echo   每日推荐: http://127.0.0.1:8000/daily.html
echo ============================================
echo.
echo 按任意键关闭此窗口（不会停止服务）
pause >nul
