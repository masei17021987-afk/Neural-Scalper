# Публикация проекта на GitHub

## 1. Рекомендуемый способ в Ubuntu

Из корня проекта выполните:

```bash
chmod +x PUBLISH_TO_GITHUB.sh scripts/publish_to_github.sh
./PUBLISH_TO_GITHUB.sh
```

По умолчанию будет создан закрытый репозиторий:

```text
Владелец: пользователь, вошедший через GitHub CLI
Название: CryptoHunter-Neural-Scalper
Видимость: private
Основная ветка: main
Тег: версия из VERSION.txt
```

## 2. Что делает Ubuntu-сценарий

```text
проверяет git и gh
→ при необходимости устанавливает GitHub CLI
  из официального APT-репозитория GitHub
→ запускает gh auth login --web
→ определяет текущего пользователя GitHub
→ инициализирует локальный Git
→ создаёт ветку main
→ добавляет только файлы, разрешённые .gitignore
→ создаёт коммит
→ создаёт private-репозиторий через gh repo create
→ отправляет main
→ создаёт и отправляет тег
→ открывает страницу репозитория
```

Сценарий **не выполняет force push**. Если репозиторий с таким именем уже существует и содержит несовместимую историю, обычный `git push` остановится вместо перезаписи.

## 3. Авторизация

При первом запуске откроется официальная авторизация GitHub CLI. В зависимости от текущего сеанса браузера GitHub может попросить:

1. войти в аккаунт;
2. подтвердить код устройства;
3. разрешить GitHub CLI доступ;
4. вернуться в терминал.

Сценарий не просит вручную вставлять Personal Access Token и не сохраняет токен в проекте.

Проверить авторизацию:

```bash
gh auth status
```

## 4. Настройка имени и видимости

Публичный репозиторий:

```bash
GITHUB_VISIBILITY=public ./PUBLISH_TO_GITHUB.sh
```

Другое имя:

```bash
GITHUB_REPO=CryptoHunter-Scalper ./PUBLISH_TO_GITHUB.sh
```

Явный владелец:

```bash
GITHUB_OWNER=masei17021987-afk ./PUBLISH_TO_GITHUB.sh
```

Комбинация:

```bash
GITHUB_OWNER=masei17021987-afk \
GITHUB_REPO=CryptoHunter-Neural-Scalper \
GITHUB_VISIBILITY=private \
./PUBLISH_TO_GITHUB.sh
```

## 5. Ручной способ в Ubuntu

После установки `git` и `gh`:

```bash
gh auth login --hostname github.com --git-protocol https --web

git init -b main
git config user.name "masei17021987-afk"
git config user.email "267742595+masei17021987-afk@users.noreply.github.com"
git add -A
git commit -m "Первый релиз с полной русской документацией и поддержкой Ubuntu"
git tag -a v0.1.1 -m "CryptoHunter Neural Scalper 0.1.1"

gh repo create masei17021987-afk/CryptoHunter-Neural-Scalper \
  --private \
  --description "Локальная нейросетевая лаборатория скальпинга по стакану с paper-trading" \
  --source . \
  --remote origin \
  --push

git push origin v0.1.1
```

## 6. Автоматический способ на Windows

Дважды щёлкните:

```text
PUBLISH_TO_GITHUB.bat
```

Windows-сценарий вызывает PowerShell-реализацию и при необходимости использует `winget` для установки Git/GitHub CLI.

## 7. Проверка после загрузки

Проверьте:

- репозиторий имеет ожидаемую видимость;
- default branch — `main`;
- README отображается на русском;
- GitHub Actions запустился;
- `.venv` отсутствует в репозитории;
- папки `var/data`, `var/models`, `var/logs` не содержат пользовательские runtime-файлы;
- нет `.env`, ключей API и секретов;
- `docs/INTERFACE_PREVIEW.png` отображается;
- тег `v0.1.1` существует;
- проект клонируется в чистую папку.

Проверка через CLI:

```bash
gh repo view masei17021987-afk/CryptoHunter-Neural-Scalper
gh run list --repo masei17021987-afk/CryptoHunter-Neural-Scalper
git status
git tag --list
```

## 8. Клонирование в Ubuntu

```bash
gh repo clone masei17021987-afk/CryptoHunter-Neural-Scalper
cd CryptoHunter-Neural-Scalper
chmod +x INSTALL_UBUNTU.sh
./INSTALL_UBUNTU.sh
```

Обычный Git:

```bash
git clone https://github.com/masei17021987-afk/CryptoHunter-Neural-Scalper.git
cd CryptoHunter-Neural-Scalper
./INSTALL_UBUNTU.sh
```

Для private-репозитория Git должен быть авторизован через GitHub CLI либо SSH.

## 9. Следующие обновления

Перед коммитом:

```bash
git status
git diff
```

Затем:

```bash
git add -A
git commit -m "Описание изменения"
git push
```

Перед `git add -A` обязательно убедитесь, что не появились:

- API key/secret;
- `.env`;
- пользовательские датасеты;
- SQLite-журнал;
- checkpoint-файлы;
- paper-состояние;
- большие архивы.

`.gitignore` уже исключает стандартные runtime-файлы, но ручная проверка остаётся обязательной.

## 10. Если репозиторий уже существует

Сценарий настроит `origin` и выполнит обычный push:

```bash
git remote -v
git push -u origin main
```

Если истории несовместимы, не применяйте `--force` автоматически. Сначала изучите:

```bash
git fetch origin
git log --oneline --graph --decorate --all
```

## 11. Удаление неверного remote

```bash
git remote remove origin
```

После этого можно повторно запустить `PUBLISH_TO_GITHUB.sh`.

## 12. Безопасность GitHub

Рекомендуется:

- private visibility на этапе разработки;
- включить двухфакторную аутентификацию GitHub;
- не хранить ключи биржи в Git;
- использовать GitHub Secrets только для CI;
- регулярно проверять Dependabot и Actions;
- не публиковать реальные торговые данные без отдельного решения.
