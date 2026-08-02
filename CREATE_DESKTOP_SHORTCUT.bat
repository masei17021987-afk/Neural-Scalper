@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "TARGET=%~dp0START.bat"
set "WORKDIR=%~dp0"
set "LINK=%USERPROFILE%\Desktop\CryptoHunter Neural Scalper.lnk"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LINK%');$s.TargetPath='%TARGET%';$s.WorkingDirectory='%WORKDIR%';$s.Description='CryptoHunter Neural Scalper';$s.Save()"
if errorlevel 1 (
  echo Не удалось создать ярлык.
  pause
  exit /b 1
)
echo Ярлык создан на рабочем столе.
pause
