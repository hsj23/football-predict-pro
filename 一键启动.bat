@echo off
chcp 65001 >nul
title 足彩预测系统

echo ========================================
echo      足彩预测系统 - 正在启动...
echo ========================================
echo.

:: 切换到项目目录
cd /d "%~dp0backend"

:: 检查并启动 MySQL
echo [1/5] 检查 MySQL 数据库...
netstat -ano 2>nul | findstr ":3306.*LISTENING" >nul
if errorlevel 1 (
    echo   MySQL 未运行，正在启动...
    start /min "" "C:\Program Files\MySQL\MySQL Server 5.7\bin\mysqld.exe"
    echo   等待 MySQL 就绪...
    set /a MYSQL_WAIT=0
    :WAIT_MYSQL
    ping 127.0.0.1 -n 3 >nul
    set /a MYSQL_WAIT+=1
    netstat -ano 2>nul | findstr ":3306.*LISTENING" >nul
    if not errorlevel 1 goto MYSQL_OK
    if %MYSQL_WAIT% geq 20 (
        echo   [警告] MySQL 启动超时，继续尝试...
        goto MYSQL_OK
    )
    goto WAIT_MYSQL
    :MYSQL_OK
    echo   MySQL 已就绪
) else (
    echo   MySQL 已在运行
)

:: 检查 Python 是否可用
echo [2/5] 检查 Python 环境...
where py >nul 2>&1
if errorlevel 1 (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [失败] 未找到 Python，请确认已安装并添加到 PATH
        echo.
        echo 按任意键退出...
        pause >nul
        exit /b 1
    )
    set PY_CMD=python
) else (
    set PY_CMD=py
)
echo [2/5] Python 环境 OK

:: 检查 uvicorn 是否安装
echo [3/5] 检查依赖...
%PY_CMD% -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [失败] 未安装 uvicorn，正在安装依赖...
    %PY_CMD% -m pip install -r requirements.txt -q
    if errorlevel 1 (
        echo [失败] 依赖安装失败，请手动运行 setup.bat
        pause
        exit /b 1
    )
)
echo [3/5] 依赖 OK

:: 清理之前可能残留的进程
echo [4/5] 清理旧进程...
:: 按端口占用杀（精准，不误杀其他Python程序）
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING" 2^>nul') do (
    echo   清理端口8000占用 PID=%%a
    taskkill /F /PID %%a >nul 2>&1
)
:: 清理Python字节码缓存
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q *.pyc 2>nul
timeout /t 1 /nobreak >nul

:: 启动后端服务
echo [5/5] 启动后端服务...
start "足彩后端" cmd /c "%PY_CMD% -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
echo [5/5] 后端启动中...

:: 等待服务就绪
echo 等待服务就绪...
set WAIT_COUNT=0
:WAIT_LOOP
ping 127.0.0.1 -n 2 >nul
set /a WAIT_COUNT+=1
>nul 2>&1 curl http://127.0.0.1:8000/health
if not errorlevel 1 goto READY
if %WAIT_COUNT% geq 20 (
    echo [超时] 后端启动超时，请检查足彩后端窗口中的错误信息
    pause
    exit /b 1
)
goto WAIT_LOOP
:READY

:: 触发数据抓取（后台静默执行）
echo 正在拉取最新数据...
start /min "" cmd /c "cd /d "%~dp0backend" && %PY_CMD% -c "from services.real_scraper import run_full_update; run_full_update()" > ..\logs\scrape.log 2>&1"

:: 打开浏览器
echo.
echo ========================================
echo  系统已启动！正在打开浏览器...
echo  访问地址: http://127.0.0.1:8000
echo  后端日志窗口请勿关闭
echo ========================================
echo.
start "" http://127.0.0.1:8000

echo 按任意键关闭系统...
pause >nul
taskkill /F /FI "WINDOWTITLE eq 足彩后端*" >nul 2>&1
