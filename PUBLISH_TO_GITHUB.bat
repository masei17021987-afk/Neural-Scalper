@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================================
echo   CryptoHunter Neural Scalper - публикация на GitHub
echo ============================================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\publish_to_github.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
  echo Публикация не завершена. Код ошибки: %EXIT_CODE%
  echo Подробности находятся выше.
) else (
  echo Репозиторий успешно подготовлен и отправлен на GitHub.
)
echo.
pause
exit /b %EXIT_CODE%
