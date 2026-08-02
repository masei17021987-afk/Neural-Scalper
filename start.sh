#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"
export PIP_DISABLE_PIP_VERSION_CHECK=1

PREPARE_ONLY=false
if [[ "${1:-}" == "--prepare-only" || "${1:-}" == "--install-only" ]]; then
  PREPARE_ONLY=true
fi

info()  { printf '\033[1;36m[CryptoHunter]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[Внимание]\033[0m %s\n' "$*" >&2; }
error() { printf '\033[1;31m[Ошибка]\033[0m %s\n' "$*" >&2; }

python_supported() {
  local bin="$1"
  [[ -x "$bin" ]] || command -v "$bin" >/dev/null 2>&1 || return 1
  "$bin" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 15) else 1)
PY
}

find_python() {
  local candidate
  if [[ -n "${PYTHON_BIN:-}" ]] && python_supported "$PYTHON_BIN"; then
    printf '%s\n' "$PYTHON_BIN"
    return 0
  fi
  for candidate in python3.12 python3.13 python3.11 python3.10 python3.14 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && python_supported "$(command -v "$candidate")"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

ensure_venv() {
  if [[ -x .venv/bin/python ]] && python_supported "$ROOT/.venv/bin/python"; then
    return 0
  fi

  if [[ -d .venv ]]; then
    local backup=".venv.unsupported.$(date +%Y%m%d-%H%M%S)"
    warn "Старое виртуальное окружение использует неподдерживаемый Python."
    warn "Оно будет сохранено как $backup."
    mv .venv "$backup"
  fi

  if command -v uv >/dev/null 2>&1; then
    info "Создаю изолированное окружение Python 3.12 через uv…"
    uv venv --python 3.12 .venv
    return 0
  fi

  local py
  if ! py="$(find_python)"; then
    error "Не найден Python 3.10–3.14 и не установлен uv."
    error "Сначала запустите ./INSTALL_UBUNTU.sh"
    return 1
  fi

  info "Создаю виртуальное окружение через $py…"
  if ! "$py" -m venv .venv; then
    error "Не удалось создать .venv. В Ubuntu обычно не установлен пакет python3-venv."
    error "Запустите ./INSTALL_UBUNTU.sh — он установит всё необходимое автоматически."
    return 1
  fi
}

install_dependencies() {
  local requirements_hash marker current
  requirements_hash="$(cat requirements.txt pyproject.toml | sha256sum | awk '{print $1}')"
  marker=".venv/.dependencies-sha256"
  current=""
  [[ -f "$marker" ]] && current="$(tr -d '[:space:]' < "$marker")"

  if [[ "$requirements_hash" == "$current" ]]; then
    return 0
  fi

  info "Устанавливаю или обновляю зависимости. Это требуется только после первого запуска или обновления проекта…"
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$ROOT/.venv/bin/python" -r requirements.txt
  else
    if ! "$ROOT/.venv/bin/python" -m pip --version >/dev/null 2>&1; then
      "$ROOT/.venv/bin/python" -m ensurepip --upgrade
    fi
    "$ROOT/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
    "$ROOT/.venv/bin/python" -m pip install -r requirements.txt
  fi
  printf '%s\n' "$requirements_hash" > "$marker"
}

ensure_venv
install_dependencies
mkdir -p var/data var/logs var/models var/reports var/cache

if [[ "$PREPARE_ONLY" == true ]]; then
  info "Окружение готово. Программу можно запускать через ./start.sh"
  exit 0
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
info "Запускаю локальный интерфейс. Браузер откроется автоматически…"
exec "$ROOT/.venv/bin/python" -m neuroscalper.launcher
