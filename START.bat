@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title CryptoHunter Neural Scalper

echo.
echo ==============================================================
echo   CryptoHunter Neural Scalper - автоматический запуск
echo ==============================================================
echo.

set "PY_CMD="
py -3.12 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.12"
if not defined PY_CMD py -3.11 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.11"
if not defined PY_CMD py -3.10 -c "import sys" >nul 2>nul && set "PY_CMD=py -3.10"
if not defined PY_CMD python -c "import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,13) else 1)" >nul 2>nul && set "PY_CMD=python"
if not defined PY_CMD (
  echo [ОШИБКА] Подходящий Python не найден.
  echo Нужен Python 3.10, 3.11 или 3.12 с пунктом "Add Python to PATH".
  start "" "https://www.python.org/downloads/windows/"
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Создаю изолированное окружение...
  %PY_CMD% -m venv .venv
  if errorlevel 1 goto :fail
)

set "PY=.venv\Scripts\python.exe"
if not exist ".venv\.dependencies-installed" (
  echo [2/3] Устанавливаю необходимые библиотеки. Это выполняется только в первый раз...
  "%PY%" -m pip install --upgrade pip setuptools wheel
  if errorlevel 1 goto :fail
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
  "%PY%" -c "import fastapi,uvicorn,aiohttp,numpy,sklearn,torch; print('Dependencies OK')"
  if errorlevel 1 goto :fail
  echo ready> ".venv\.dependencies-installed"
) else (
  echo [2/3] Библиотеки уже установлены.
)

echo [3/3] Запускаю программу и открываю браузер...
set "PYTHONPATH=%CD%\src"
"%PY%" -m neuroscalper.launcher
exit /b %errorlevel%

:fail
echo.
echo [ОШИБКА] Автоматический запуск не завершён.
echo Посмотрите текст ошибки выше. Интернет нужен только для первой установки библиотек.
echo.
pause
exit /b 1
