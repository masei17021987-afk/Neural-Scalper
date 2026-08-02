@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Сначала запустите START.bat.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
set "PYTHONPATH=%CD%\src"
.venv\Scripts\python.exe -m pytest
pause
