#!/usr/bin/env bash
set -Eeuo pipefail

rm -f \
  "$HOME/.local/bin/cryptohunter-neural-scalper" \
  "$HOME/.local/bin/cryptohunter-neural-scalper-stop" \
  "$HOME/.local/bin/cryptohunter-neural-scalper-publish" \
  "$HOME/.local/share/applications/cryptohunter-neural-scalper.desktop" \
  "$HOME/.local/share/applications/cryptohunter-neural-scalper-stop.desktop" \
  "$HOME/.local/share/applications/cryptohunter-neural-scalper-publish.desktop"

if command -v xdg-user-dir >/dev/null 2>&1; then
  desktop_dir="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
else
  desktop_dir="$HOME/Desktop"
fi
[[ -n "${desktop_dir:-}" ]] || desktop_dir="$HOME/Desktop"
rm -f \
  "$desktop_dir/CryptoHunter Neural Scalper.desktop" \
  "$desktop_dir/CryptoHunter Neural Scalper — Остановить.desktop" \
  "$desktop_dir/CryptoHunter Neural Scalper — GitHub.desktop"

command -v update-desktop-database >/dev/null 2>&1 \
  && update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 \
  || true

echo "Ярлыки CryptoHunter удалены. Сам проект, модели и данные не затронуты."
