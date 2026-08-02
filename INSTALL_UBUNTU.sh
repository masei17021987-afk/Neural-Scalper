#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"

info()  { printf '\033[1;36m[CryptoHunter]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[Внимание]\033[0m %s\n' "$*" >&2; }
error() { printf '\033[1;31m[Ошибка]\033[0m %s\n' "$*" >&2; }

as_root() {
  if (( EUID == 0 )); then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    error "Нужны права администратора. Войдите под root или установите sudo."
    return 1
  fi
}

if [[ "$(uname -s)" != "Linux" ]]; then
  error "Этот установщик предназначен для Linux/Ubuntu."
  exit 1
fi

chmod +x \
  start.sh START_UBUNTU.sh STOP.sh STOP_UBUNTU.sh CHECK_GPU.sh RUN_TESTS.sh \
  PUBLISH_TO_GITHUB.sh UNINSTALL_UBUNTU_SHORTCUTS.sh \
  scripts/publish_to_github.sh

if command -v apt-get >/dev/null 2>&1; then
  packages=(curl ca-certificates git xdg-utils xdg-user-dirs desktop-file-utils)
  missing=()
  for package in "${packages[@]}"; do
    dpkg -s "$package" >/dev/null 2>&1 || missing+=("$package")
  done
  if (( ${#missing[@]} > 0 )); then
    info "Устанавливаю системные компоненты Ubuntu: ${missing[*]}"
    as_root apt-get update
    as_root apt-get install -y "${missing[@]}"
  fi
else
  warn "apt-get не найден. Системные зависимости автоматически не устанавливаются."
fi

if ! command -v curl >/dev/null 2>&1; then
  error "Нужен curl. Установите его через пакетный менеджер вашей системы."
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  info "Устанавливаю uv из официального установщика Astral…"
  installer="$(mktemp)"
  trap 'rm -f "${installer:-}"' EXIT
  curl -LsSf https://astral.sh/uv/install.sh -o "$installer"
  UV_NO_MODIFY_PATH=1 sh "$installer"
  rm -f "$installer"
  trap - EXIT
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v uv >/dev/null 2>&1; then
  error "uv установлен, но не найден в PATH. Откройте новый терминал и повторите запуск."
  exit 1
fi

info "Подготавливаю Python 3.12 и локальное окружение…"
uv python install 3.12
"$ROOT/start.sh" --prepare-only

BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
mkdir -p "$BIN_DIR" "$APP_DIR"

printf '#!/usr/bin/env bash\ncd %q\nexec ./start.sh\n' "$ROOT" \
  > "$BIN_DIR/cryptohunter-neural-scalper"
printf '#!/usr/bin/env bash\ncd %q\nexec ./STOP.sh\n' "$ROOT" \
  > "$BIN_DIR/cryptohunter-neural-scalper-stop"
printf '#!/usr/bin/env bash\ncd %q\nexec ./PUBLISH_TO_GITHUB.sh\n' "$ROOT" \
  > "$BIN_DIR/cryptohunter-neural-scalper-publish"
chmod +x \
  "$BIN_DIR/cryptohunter-neural-scalper" \
  "$BIN_DIR/cryptohunter-neural-scalper-stop" \
  "$BIN_DIR/cryptohunter-neural-scalper-publish"

cat > "$APP_DIR/cryptohunter-neural-scalper.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=CryptoHunter Neural Scalper
Comment=Нейросетевая лаборатория скальпинга и paper-trading
Exec="$BIN_DIR/cryptohunter-neural-scalper"
Icon=utilities-system-monitor
Terminal=true
Categories=Development;Finance;Utility;
Keywords=Crypto;Trading;Scalping;Neural;Binance;
StartupNotify=true
DESKTOP

cat > "$APP_DIR/cryptohunter-neural-scalper-stop.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=CryptoHunter Neural Scalper — Остановить
Comment=Безопасно завершить локальный сервер CryptoHunter
Exec="$BIN_DIR/cryptohunter-neural-scalper-stop"
Icon=process-stop
Terminal=true
Categories=Development;Finance;Utility;
StartupNotify=false
DESKTOP

cat > "$APP_DIR/cryptohunter-neural-scalper-publish.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=CryptoHunter Neural Scalper — Опубликовать на GitHub
Comment=Создать или обновить приватный GitHub-репозиторий проекта
Exec="$BIN_DIR/cryptohunter-neural-scalper-publish"
Icon=folder-git-symbolic
Terminal=true
Categories=Development;Finance;Utility;
StartupNotify=true
DESKTOP
chmod +x \
  "$APP_DIR/cryptohunter-neural-scalper.desktop" \
  "$APP_DIR/cryptohunter-neural-scalper-stop.desktop" \
  "$APP_DIR/cryptohunter-neural-scalper-publish.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

if command -v xdg-user-dir >/dev/null 2>&1; then
  DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
else
  DESKTOP_DIR="$HOME/Desktop"
fi
[[ -n "${DESKTOP_DIR:-}" ]] || DESKTOP_DIR="$HOME/Desktop"

if [[ -d "$DESKTOP_DIR" ]]; then
  cp "$APP_DIR/cryptohunter-neural-scalper.desktop" \
    "$DESKTOP_DIR/CryptoHunter Neural Scalper.desktop"
  cp "$APP_DIR/cryptohunter-neural-scalper-stop.desktop" \
    "$DESKTOP_DIR/CryptoHunter Neural Scalper — Остановить.desktop"
  cp "$APP_DIR/cryptohunter-neural-scalper-publish.desktop" \
    "$DESKTOP_DIR/CryptoHunter Neural Scalper — GitHub.desktop"
  chmod +x \
    "$DESKTOP_DIR/CryptoHunter Neural Scalper.desktop" \
    "$DESKTOP_DIR/CryptoHunter Neural Scalper — Остановить.desktop" \
    "$DESKTOP_DIR/CryptoHunter Neural Scalper — GitHub.desktop"
  if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_DIR/CryptoHunter Neural Scalper.desktop" metadata::trusted true >/dev/null 2>&1 || true
    gio set "$DESKTOP_DIR/CryptoHunter Neural Scalper — Остановить.desktop" metadata::trusted true >/dev/null 2>&1 || true
    gio set "$DESKTOP_DIR/CryptoHunter Neural Scalper — GitHub.desktop" metadata::trusted true >/dev/null 2>&1 || true
  fi
fi

info "Установка завершена."
printf '\nЗапуск из терминала:\n  %q/start.sh\n' "$ROOT"
printf '\nПубликация на GitHub:\n  %q/PUBLISH_TO_GITHUB.sh\n' "$ROOT"
printf '\nВ меню приложений появился ярлык «CryptoHunter Neural Scalper».\n'
printf 'Если Ubuntu попросит доверять ярлыку на рабочем столе, нажмите правой кнопкой → «Разрешить запуск».\n'
