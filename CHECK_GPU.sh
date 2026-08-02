#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
"$ROOT/start.sh" --prepare-only
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if command -v nvidia-smi >/dev/null 2>&1; then
  echo
  echo "=== NVIDIA DRIVER ==="
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
else
  echo
  echo "nvidia-smi не найден. Это нормально для CPU-режима."
fi

echo
echo "=== PYTORCH ==="
"$ROOT/.venv/bin/python" - <<'PY'
import platform
import torch

print(f"Python: {platform.python_version()}")
print(f"PyTorch: {torch.__version__}")
print(f"CUDA доступна: {torch.cuda.is_available()}")
print(f"CUDA в сборке PyTorch: {torch.version.cuda}")
if torch.cuda.is_available():
    print(f"Устройство: {torch.cuda.get_device_name(0)}")
    total = torch.cuda.get_device_properties(0).total_memory / 1024**3
    print(f"Видеопамять: {total:.1f} ГБ")
else:
    print("Обучение будет выполняться на CPU, пока CUDA не станет доступна PyTorch.")
PY
