# Установка и запуск

## 1. Поддерживаемая среда

Основной сценарий этой сборки подготовлен для **Ubuntu/Linux**. Windows-скрипты сохранены для совместимости.

Минимальные требования:

- Ubuntu или совместимый Debian-based Linux;
- интернет при первой установке зависимостей;
- современный браузер;
- 8 ГБ RAM для демо и небольших экспериментов;
- свободное место для Python, PyTorch, данных и моделей.

Рекомендуется для обучения:

- 32–64 ГБ RAM;
- SSD/NVMe;
- NVIDIA GPU с поддерживаемым драйвером;
- отдельный диск для длительной записи стакана.

Программа поддерживает Python 3.10–3.13, но автоматический Ubuntu-установщик создаёт контролируемое окружение на Python 3.12 через `uv`.

## 2. Автоматическая установка в Ubuntu

Рекомендуемый архив — `.tar.gz`, потому что он сохраняет права выполнения.

```bash
cd /путь/к/CryptoHunter-Neural-Scalper
chmod +x INSTALL_UBUNTU.sh
./INSTALL_UBUNTU.sh
```

Сценарий:

- устанавливает недостающие `curl`, `git`, сертификаты и xdg-компоненты;
- устанавливает `uv` в профиль пользователя;
- загружает Python 3.12;
- создаёт `.venv`;
- устанавливает зависимости;
- создаёт ярлыки запуска и остановки.

После этого программу можно открыть из меню Ubuntu или командой:

```bash
./start.sh
```

Подробное руководство для Ubuntu: [UBUNTU_RU.md](UBUNTU_RU.md).

## 3. Запуск в Ubuntu

```bash
./start.sh
```

Альтернативное имя:

```bash
./START_UBUNTU.sh
```

По умолчанию интерфейс доступен только локально:

```text
http://127.0.0.1:8094/
```

Если браузер не открылся, введите адрес вручную.

## 4. Повторный запуск и зависимости

`start.sh` рассчитывает SHA-256 от `requirements.txt` и `pyproject.toml`. Зависимости переустанавливаются только при изменении этих файлов.

Подготовить окружение без запуска сервера:

```bash
./start.sh --prepare-only
```

Полностью пересобрать окружение:

```bash
./STOP.sh
mv .venv ".venv-backup-$(date +%Y%m%d-%H%M%S)"
./start.sh
```

Папку `var/` не удаляйте: в ней хранятся настройки, история, модели и paper-состояние.

## 5. Остановка в Ubuntu

В терминале сервера нажмите `Ctrl+C` или выполните:

```bash
./STOP.sh
```

Сценарий проверяет PID и командную строку процесса перед остановкой.

## 6. Проверка GPU

```bash
./CHECK_GPU.sh
```

Будут показаны:

- `nvidia-smi`, если он доступен;
- версия PyTorch;
- CUDA availability;
- модель GPU;
- объём видеопамяти.

CUDA не обязательна для запуска интерфейса, демо, записи и paper-trading.

## 7. Тесты в Ubuntu

```bash
./RUN_TESTS.sh
```

Ручной вариант:

```bash
./start.sh --prepare-only
export PYTHONPATH="$PWD/src"
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

## 8. Публикация на GitHub из Ubuntu

```bash
./PUBLISH_TO_GITHUB.sh
```

Сценарий при необходимости устанавливает официальный GitHub CLI, выполняет браузерную авторизацию и создаёт private-репозиторий.

Подробности: [GITHUB_PUBLICATION_RU.md](GITHUB_PUBLICATION_RU.md).

## 9. Ручная установка в Ubuntu без `INSTALL_UBUNTU.sh`

С установленным Python 3.10–3.13:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt
export PYTHONPATH="$PWD/src"
.venv/bin/python -m neuroscalper.launcher
```

С `uv`:

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
export PYTHONPATH="$PWD/src"
.venv/bin/python -m neuroscalper.launcher
```

## 10. Автоматическая установка на Windows

1. Установите Python 3.10–3.12 и включите `Add Python to PATH`.
2. Распакуйте проект полностью.
3. Дважды щёлкните `START.bat`.

Для остановки используйте `STOP.bat`. Для ярлыка — `CREATE_DESKTOP_SHORTCUT.bat`. Для проверки — `RUN_TESTS.bat`.

## 11. Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---:|---|
| `NEUROSCALPER_HOST` | `127.0.0.1` | адрес локального сервера |
| `NEUROSCALPER_PORT` | `8094` | порт интерфейса |
| `PYTHON_BIN` | автоопределение | явный Python для `start.sh` |
| `GITHUB_REPO` | `CryptoHunter-Neural-Scalper` | имя создаваемого репозитория |
| `GITHUB_OWNER` | текущий пользователь `gh` | владелец репозитория |
| `GITHUB_VISIBILITY` | `private` | `private`, `public` или `internal` |

Пример другого порта:

```bash
NEUROSCALPER_PORT=8194 ./start.sh
```

Не публикуйте API на `0.0.0.0` без внешнего контура безопасности.

## 12. Что можно удалять

Можно пересоздать:

- `.venv`;
- `var/logs/*`;
- `var/reports/*` после копирования;
- старые неиспользуемые checkpoint-файлы после резервной копии.

Не удаляйте без проверки:

- `var/data/records`;
- `var/models/best_model.pt`;
- `var/data/paper_state.json`;
- `var/data/neuroscalper.db`;
- `var/data/config.json`.

## 13. Сетевая безопасность

Версия 0.1.1 не имеет пользовательской аутентификации HTTP API и должна работать на `127.0.0.1`. Для удалённого сервера используйте SSH-туннель, а не открытый порт.
