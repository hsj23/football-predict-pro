@echo off
chcp 65001 >nul
cd /d "%~dp0backend"

:: 等待 MySQL 就绪（最多等20秒）
set RETRY=0
:WAIT_MYSQL
ping 127.0.0.1 -n 2 >nul
set /a RETRY+=1
py -c "import pymysql; pymysql.connect(host='localhost',user='root',password='123456',database='football_predict',connect_timeout=2); print('OK')" >nul 2>&1
if not errorlevel 1 goto MYSQL_OK
if %RETRY% geq 10 goto MYSQL_SKIP
goto WAIT_MYSQL
:MYSQL_OK
echo MySQL connected (retry %RETRY%)
:MYSQL_SKIP

:: 强制释放 8000 端口
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING" 2^>nul') do taskkill /F /PID %%a >nul 2>&1
ping 127.0.0.1 -n 1 >nul

:: 清除旧缓存
if exist "%~dp0data\.pred_cache" del /q "%~dp0data\.pred_cache" >nul 2>&1
if exist "%~dp0data\.last_scrape" del /q "%~dp0data\.last_scrape" >nul 2>&1

:: 启动后端
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
