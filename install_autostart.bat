@echo off
:: 安装足彩预测系统开机自启
:: 右键以管理员身份运行此文件

chcp 65001 >nul
echo ========================================
echo   足彩预测系统 - 开机自启安装
echo ========================================
echo.

set "BAT_PATH=D:\小黄的助手\足彩预测系统\start_backend.bat"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

:: 方法1: 复制到启动文件夹
echo [方法1] 添加到启动文件夹...
copy /Y "%BAT_PATH%" "%STARTUP_FOLDER%\足球预测系统.bat" >nul 2>&1
if %errorlevel% equ 0 (
    echo   已添加到启动文件夹
) else (
    echo   启动文件夹添加失败，尝试方法2...
)

:: 方法2: 注册表 Run键
echo [方法2] 添加注册表启动项...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "FootballPredict" /t REG_SZ /d "\"%BAT_PATH%\"" /f >nul 2>&1
if %errorlevel% equ 0 (
    echo   已添加注册表启动项
)

:: 方法3: 计划任务（最可靠）
echo [方法3] 创建计划任务...
schtasks /create /tn "FootballPredict_Backend" /tr "\"%BAT_PATH%\"" /sc onlogon /delay 0000:30 /rl highest /f >nul 2>&1
if %errorlevel% equ 0 (
    echo   已创建计划任务 (延迟30秒启动)
) else (
    echo   计划任务创建失败，可能权限不足
)

echo.
echo ========================================
echo   安装完成!
echo.
echo   下次重启电脑后，后端服务将自动启动
echo   浏览器访问: http://localhost:8000/
echo ========================================
echo.
pause
