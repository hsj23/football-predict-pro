@echo off
chcp 65001 >nul
title 足彩预测系统 - 安装向导

echo ============================================
echo   足彩预测系统 - 一键安装
echo ============================================
echo.

:: 检查Python
echo [1/5] 检查 Python...
py --version >nul 2>&1
if errorlevel 1 (
    echo   错误: 未找到 Python，请先安装 Python 3.9+
    echo   下载: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo   Python OK

:: 检查MySQL
echo [2/5] 检查 MySQL...
mysql --version >nul 2>&1
if errorlevel 1 (
    echo   警告: 未找到 mysql 命令，请确保 MySQL 8.0 已安装
    echo   下载: https://dev.mysql.com/downloads/mysql/
) else (
    echo   MySQL OK
)

:: 安装依赖
echo [3/5] 安装 Python 依赖包...
cd /d "%~dp0backend"
py -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo   错误: 依赖安装失败
    pause
    exit /b 1
)
echo   依赖安装完成

:: 创建数据库
echo [4/5] 初始化数据库...
echo   请输入 MySQL root 密码（默认123456）:
set /p MYSQL_PWD=
if "%MYSQL_PWD%"=="" set MYSQL_PWD=123456

py -c "import pymysql; conn=pymysql.connect(host='localhost',user='root',password='%MYSQL_PWD%'); cur=conn.cursor(); cur.execute('CREATE DATABASE IF NOT EXISTS football_predict CHARACTER SET utf8mb4'); conn.commit(); print('数据库创建成功'); cur.close(); conn.close()" 2>nul
if errorlevel 1 (
    echo   警告: 数据库创建失败，请手动执行:
    echo   mysql -u root -p
    echo   CREATE DATABASE football_predict CHARACTER SET utf8mb4;
)
py -c "import sys; sys.path.insert(0,'.'); from app.database import init_db; init_db(); print('数据表创建成功')"
if errorlevel 1 (
    echo   警告: 数据表创建失败
)

:: 创建桌面快捷方式
echo [5/5] 创建桌面快捷方式...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"

echo.
echo ============================================
echo   安装完成！
echo   双击桌面 "足彩预测系统" 启动
echo   或运行 launcher.bat
echo ============================================
pause
