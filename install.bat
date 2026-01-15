@echo off
chcp 65001 >nul
title Установка

echo ========================================
echo    Установка зависимостей
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] Создание виртуального окружения...
python -m venv venv

echo [2/3] Установка пакетов Python...
call venv\Scripts\activate.bat
pip install -r requirements.txt

echo [3/3] Установка браузера для Playwright...
playwright install chromium

echo.
echo ========================================
echo    ГОТОВО!
echo ========================================
echo.
echo Теперь запусти test.bat для проверки
echo Или start.bat для запуска бота
echo.

pause
