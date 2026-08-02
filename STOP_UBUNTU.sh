#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAR_DIR="${NEUROSCALPER_VAR_DIR:-$ROOT/var}"
PID_FILE="$VAR_DIR/data/server.pid"

info()  { printf '\033[1;36m[CryptoHunter]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[Внимание]\033[0m %s\n' "$*" >&2; }
error() { printf '\033[1;31m[Ошибка]\033[0m %s\n' "$*" >&2; }

if [[ ! -f "$PID_FILE" ]]; then
  info "Программа не запущена или PID-файл уже удалён."
  exit 0
fi

pid="$(tr -d '[:space:]' < "$PID_FILE")"
if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
  error "Некорректный PID-файл: $PID_FILE"
  exit 1
fi

if ! kill -0 "$pid" 2>/dev/null; then
  warn "Процесс $pid уже завершён. Удаляю устаревший PID-файл."
  rm -f "$PID_FILE"
  exit 0
fi

command_line="$(ps -p "$pid" -o args= 2>/dev/null || true)"
if [[ "$command_line" != *"neuroscalper.launcher"* && "$command_line" != *"neuroscalper.web.api"* ]]; then
  error "Защитная остановка: PID $pid принадлежит другой программе."
  error "Команда процесса: $command_line"
  error "Проверьте процесс вручную; PID-файл не удалён."
  exit 1
fi

info "Останавливаю CryptoHunter Neural Scalper (PID $pid)…"
kill -TERM "$pid"
for _ in {1..50}; do
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    info "Программа остановлена."
    exit 0
  fi
  sleep 0.1
done

warn "Процесс не завершился после SIGTERM. Выполняю принудительную остановку."
kill -KILL "$pid" 2>/dev/null || true
rm -f "$PID_FILE"
info "Программа остановлена принудительно."
