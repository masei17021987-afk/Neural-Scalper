@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Сначала запустите START.bat хотя бы один раз.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -c "import torch; print('PyTorch:',torch.__version__); print('CUDA доступна:',torch.cuda.is_available()); print('Устройство:',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
echo.
echo Если CUDA недоступна, откройте официальный мастер установки PyTorch
choice /C YN /M "Открыть страницу PyTorch"
if errorlevel 2 exit /b 0
start "" "https://pytorch.org/get-started/locally/"
