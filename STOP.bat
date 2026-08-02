@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "PID_FILE=var\data\server.pid"
if not exist "%PID_FILE%" (
  echo CryptoHunter Neural Scalper не запущен или PID-файл отсутствует.
  pause
  exit /b 0
)
set /p APP_PID=<"%PID_FILE%"
if "%APP_PID%"=="" (
  echo PID-файл пуст.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Get-CimInstance Win32_Process -Filter 'ProcessId=%APP_PID%' -ErrorAction SilentlyContinue; if(-not $p){exit 2}; if(($p.CommandLine -notmatch 'neuroscalper[.]launcher') -and ($p.CommandLine -notmatch 'neuroscalper[.]web[.]api')){exit 3}; Stop-Process -Id %APP_PID% -Force -ErrorAction Stop"
set "STOP_CODE=%ERRORLEVEL%"
if "%STOP_CODE%"=="2" (
  echo Процесс %APP_PID% уже завершён.
) else if "%STOP_CODE%"=="3" (
  echo Защитная остановка: PID %APP_PID% принадлежит другой программе.
  echo Удалите устаревший файл var\data\server.pid вручную после проверки.
  pause
  exit /b 1
) else if not "%STOP_CODE%"=="0" (
  echo Не удалось остановить процесс %APP_PID%.
  pause
  exit /b 1
) else (
  echo CryptoHunter Neural Scalper остановлен.
)
del /q "%PID_FILE%" >nul 2>nul
timeout /t 2 >nul
