@echo off
chcp 65001 >nul
title Majestic RP Parser Bot

echo ========================================
echo    Majestic RP Forum Parser Bot
echo ========================================
echo.

cd /d "%~dp0"

:: Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python не найден! Установите Python 3.10+
    pause
    exit /b 1
)

:: Установка если нет venv
if not exist "venv" (
    echo [*] Первый запуск - установка...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
    playwright install chromium
) else (
    call venv\Scripts\activate.bat
)

echo.
echo [*] Запуск бота...
echo.

python bot.py

pause
