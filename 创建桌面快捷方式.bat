@echo off
chcp 65001 >nul
title 创建桌面快捷方式

echo.
echo 正在创建桌面快捷方式...

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"

echo.
echo 完成！桌面已创建快捷方式: 足彩预测系统
echo.
pause
