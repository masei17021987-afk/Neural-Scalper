# Решение проблем

## 0. Быстрая диагностика Ubuntu

Из корня проекта выполните:

```bash
chmod +x *.sh scripts/*.sh
./start.sh
```

Если запуск не удался:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git curl wget ca-certificates xdg-utils
rm -rf .venv
./start.sh
```

Полная Ubuntu-инструкция: [UBUNTU_RU.md](UBUNTU_RU.md).

## 1. Windows: `START.bat` сразу закрывается

Запустите его из `cmd`, чтобы увидеть ошибку:

```cmd
cd /d D:\CryptoHunter-Neural-Scalper
START.bat
```

Проверьте:

```cmd
py -0p
python --version
```

Поддерживаемый сценарий запуска рассчитан на Python 3.10–3.12 x64.

## 2. Python не найден

Установите Python x64 и включите Python Launcher. После установки закройте и откройте терминал.

Не используйте Microsoft Store alias, если он ведёт на пустую страницу. В Windows Settings → App execution aliases при необходимости отключите конфликтующие `python.exe` aliases.

## 3. Ошибка создания `.venv`

Удалите только `.venv` и повторите запуск:

```cmd
rmdir /s /q .venv
START.bat
```

Не удаляйте `var/`: там ваши данные.

## 4. Ошибка установки PyTorch

Причины:

- неподдерживаемая версия Python;
- нет места на диске;
- временная проблема PyPI;
- антивирус блокирует файлы;
- proxy/certificate.

Проверка:

```cmd
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt -v
```

## 5. Интерфейс не открывается

Откройте вручную:

```text
http://127.0.0.1:8094
```

Проверка:

```cmd
curl http://127.0.0.1:8094/health
```

Если порт занят:

```cmd
netstat -ano | findstr :8094
```

В Ubuntu выполните `./STOP.sh`; в Windows используйте `STOP.bat` либо Task Manager.

## 6. Пустая страница или старый интерфейс

- нажмите `Ctrl+F5`;
- откройте приватное окно;
- очистите cache для localhost;
- проверьте DevTools Console;
- выполните `node --check src\neuroscalper\web\static\app.js`.

## 7. Binance не подключается

Проверьте:

- доступность интернета;
- firewall;
- DNS;
- системное время;
- VPN/региональные ограничения;
- журнал `var/logs/neuroscalper.log`.

Запустите demo. Если demo работает, проблема находится во внешнем соединении, а не в базовом runtime.

## 8. `STALE_DATA`

- синхронизируйте системные часы Ubuntu/Windows;
- проверьте задержку сети;
- смотрите reconnect в логе;
- не увеличивайте порог только ради исчезновения ошибки;
- убедитесь, что нет пауз энергосбережения.

## 9. `DATA_QUALITY`

Откройте статус/журнал и найдите warnings. Возможны gap, crossed book, пустая сторона, широкий спред или price jump. Правильное действие — восстановить поток, а не отключать проверку.

## 10. Нет сигналов

Это может быть нормальным. Проверьте:

- прогрелась ли sequence length;
- confidence;
- min net edge;
- spread limit;
- какие стратегии включены;
- quality score;
- режим роутера;
- наличие checkpoint.

Сначала смотрите причины `FLAT`, `LOW_CONFIDENCE`, `NO_NET_EDGE`, а не снижайте все пороги одновременно.

## 11. Все сигналы отклоняются

В `Журнале` сгруппируйте коды отказов. Типовые причины описаны в `RISK_MANAGEMENT_RU.md`.

## 12. Модель не готова

До обучения работает heuristic baseline. Для нейросети:

1. запустите обучение;
2. дождитесь `stage=complete`;
3. проверьте `var/models/best_model.pt`;
4. перезапустите или убедитесь, что runtime загрузил модель;
5. смотрите ошибку load в логе.

## 13. CUDA не используется

В Ubuntu выполните `nvidia-smi` и `./CHECK_GPU.sh`. В Windows запустите `CHECK_GPU.bat`.

В Python:

```python
import torch
print(torch.__version__)
print(torch.cuda.is_available())
print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU")
```

Если `False`, возможно установлен CPU-only wheel. Переустановите PyTorch согласно вашей CUDA/драйверной конфигурации.

## 14. Out of memory

Уменьшайте по порядку:

1. `batch_size`;
2. `sequence_length`;
3. `hidden_size`;
4. число samples;
5. отключите параллельные GPU-программы.

После изменения sequence/hidden нужен новый checkpoint.

## 15. Recorded training пишет `No recorded book files`

Проверьте:

```text
var/data/records/<SYMBOL>/book_*.jsonl.gz
```

Символ в конфиге должен совпадать с папкой и полем события. Включите запись и некоторое время держите market stream.

## 16. `Too few valid snapshots for training`

После прогрева и горизонта требуется более 100 пригодных примеров, но для реального исследования этого недостаточно. Соберите больше непрерывной истории без разрывов.

## 17. Бэктест recorded не запускается

Проверьте gzip:

```bash
gzip -t var/data/records/BTCUSDT/book_*.jsonl.gz
```

Проверьте, что bids/asks не пусты и JSON валиден.

## 18. Paper balance странный

Учитывайте:

- входная fee вычитается сразу;
- equity включает unrealized;
- выход закрывается как taker;
- в trade net PnL входят обе комиссии;
- market fill проходит несколько уровней и slippage.

## 19. Kill switch не сбрасывается ожидаемо

Сброс выключает флаг, но последующий `sync_equity()` снова включит его, если equity всё ещё нарушает глобальный лимит. Это правильное поведение. Сначала сбросьте/исправьте paper account или параметры в исследовательской копии.

## 20. SQLite заблокирована

Убедитесь, что нет двух runtime, использующих одну папку `var/`. Не копируйте живую WAL-базу без остановки.

## 21. Повреждён config/paper/report

Следуйте [BACKUP_AND_RECOVERY_RU.md](BACKUP_AND_RECOVERY_RU.md). Не удаляйте файл до сохранения копии.

## 22. Тесты не видят пакет

```cmd
set PYTHONPATH=src
python -m pytest -q
```

Либо установите editable:

```cmd
python -m pip install -e .
```

## 23. После обновления стало хуже

Сравните:

- Git commit;
- `config.json`;
- checkpoint metadata;
- dataset period/checksum;
- dependency lock;
- комиссии/latency;
- rejection counts.

Откат кода без отката несовместимого checkpoint может не восстановить поведение.

## 24. Какие файлы приложить к отчёту об ошибке

- версия и commit;
- версия Ubuntu/Windows и Python;
- последние 100–300 строк лога;
- шаги воспроизведения;
- ожидаемое и фактическое поведение;
- sanitized config;
- скриншот;
- результат `./RUN_TESTS.sh` или `RUN_TESTS.bat`;
- без API keys и персональных данных.
