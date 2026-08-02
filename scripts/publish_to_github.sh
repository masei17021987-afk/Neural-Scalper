#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"

REPO_NAME="${GITHUB_REPO:-CryptoHunter-Neural-Scalper}"
VISIBILITY="${GITHUB_VISIBILITY:-private}"
DESCRIPTION="${GITHUB_DESCRIPTION:-Локальная нейросетевая лаборатория скальпинга по стакану с paper-trading}"

info()    { printf '\033[1;36m[GitHub]\033[0m %s\n' "$*"; }
success() { printf '\033[1;32m[Готово]\033[0m %s\n' "$*"; }
warn()    { printf '\033[1;33m[Внимание]\033[0m %s\n' "$*" >&2; }
error()   { printf '\033[1;31m[Ошибка]\033[0m %s\n' "$*" >&2; }

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

case "$VISIBILITY" in
  private|public|internal) ;;
  *) error "GITHUB_VISIBILITY должен быть private, public или internal."; exit 2 ;;
esac

install_base_packages() {
  if ! command -v apt-get >/dev/null 2>&1; then
    error "Автоматическая установка поддерживается на Ubuntu/Debian. Установите git, curl и gh вручную."
    exit 1
  fi
  info "Устанавливаю Git, curl и системные сертификаты…"
  as_root apt-get update
  as_root apt-get install -y git curl ca-certificates
}

install_gh_official() {
  command -v curl >/dev/null 2>&1 || install_base_packages
  info "Устанавливаю GitHub CLI из официального APT-репозитория GitHub…"
  as_root install -m 0755 -d /etc/apt/keyrings
  tmp_key="$(mktemp)"
  trap 'rm -f "${tmp_key:-}"' EXIT
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o "$tmp_key"
  as_root install -m 0644 "$tmp_key" /etc/apt/keyrings/githubcli-archive-keyring.gpg
  rm -f "$tmp_key"
  trap - EXIT
  as_root install -m 0755 -d /etc/apt/sources.list.d
  tmp_list="$(mktemp)"
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\n' \
    "$(dpkg --print-architecture)" > "$tmp_list"
  as_root install -m 0644 "$tmp_list" /etc/apt/sources.list.d/github-cli.list
  rm -f "$tmp_list"
  as_root apt-get update
  as_root apt-get install -y gh
}

command -v git >/dev/null 2>&1 || install_base_packages
command -v gh >/dev/null 2>&1 || install_gh_official

if command -v python3 >/dev/null 2>&1; then
  info "Проверяю отсутствие секретов, runtime-файлов и слишком больших файлов…"
  python3 "$ROOT/scripts/prepublish_check.py"
else
  warn "python3 не найден: расширенная предпубликационная проверка пропущена."
fi

if ! gh auth status --hostname github.com >/dev/null 2>&1; then
  info "Откроется официальная авторизация GitHub в браузере."
  gh auth login --hostname github.com --git-protocol https --web
fi
gh auth setup-git >/dev/null 2>&1 || true

OWNER="${GITHUB_OWNER:-$(gh api user --jq .login)}"
FULL_REPO="$OWNER/$REPO_NAME"
USER_ID="$(gh api user --jq .id 2>/dev/null || printf '0')"
TARGET_URL="https://github.com/$FULL_REPO.git"

# Fail closed: пользовательские данные и типовые секреты не должны попадать в GitHub.
for secret_file in .env .env.local credentials.json secrets.json; do
  if [[ -e "$secret_file" ]]; then
    error "Перед публикацией удалите потенциально секретный файл: $secret_file"
    exit 1
  fi
done

info "Файлы var/ допускаются локально, но .gitignore и проверка Git index не позволят отправить их в репозиторий."

if [[ ! -d .git ]]; then
  info "Создаю локальный Git-репозиторий…"
  git init -b main
fi

git branch -M main
git config user.name >/dev/null 2>&1 || git config user.name "$OWNER"
git config user.email >/dev/null 2>&1 || git config user.email "${USER_ID}+${OWNER}@users.noreply.github.com"

# При клонировании из Git bundle origin может указывать на локальный файл.
if git remote get-url origin >/dev/null 2>&1; then
  current_origin="$(git remote get-url origin)"
  if [[ "$current_origin" != "$TARGET_URL" && "$current_origin" != "git@github.com:$FULL_REPO.git" ]]; then
    git remote remove source-bundle >/dev/null 2>&1 || true
    git remote rename origin source-bundle
  fi
fi

git add -A
if command -v python3 >/dev/null 2>&1; then
  info "Проверяю фактический Git index перед коммитом…"
  python3 "$ROOT/scripts/prepublish_check.py" --staged
fi
if ! git diff --cached --quiet; then
  info "Создаю коммит проекта и документации…"
  git commit -m "Первый релиз с полной русской документацией и поддержкой Ubuntu"
elif ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  git commit --allow-empty -m "Первый релиз с полной русской документацией и поддержкой Ubuntu"
fi

if gh repo view "$FULL_REPO" >/dev/null 2>&1; then
  warn "Репозиторий $FULL_REPO уже существует. Будет выполнен обычный push без force."
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$TARGET_URL"
  else
    git remote add origin "$TARGET_URL"
  fi
  git push -u origin main
else
  info "Создаю $VISIBILITY-репозиторий $FULL_REPO…"
  gh repo create "$FULL_REPO" \
    "--$VISIBILITY" \
    --description "$DESCRIPTION" \
    --source . \
    --remote origin \
    --push
fi

VERSION="$(awk -F': *' '/^Version:/ {print $2; exit}' VERSION.txt 2>/dev/null || true)"
[[ -n "$VERSION" ]] || VERSION="0.1.1"
TAG="v$VERSION"
if ! git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  git tag -a "$TAG" -m "CryptoHunter Neural Scalper $VERSION"
fi
git push origin "$TAG"

success "Проект загружен: https://github.com/$FULL_REPO"
success "Ветка: main · тег: $TAG · видимость: $VISIBILITY"
gh repo view "$FULL_REPO" --web
