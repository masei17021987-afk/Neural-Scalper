# История изменений

Все заметные изменения проекта фиксируются в этом файле.

## [0.1.1] — 2026-08-02

### Ubuntu и Linux

- Ubuntu назначена основной пользовательской платформой сборки;
- добавлен однократный установщик `INSTALL_UBUNTU.sh`;
- добавлены верхнеуровневые `STOP.sh`, `RUN_TESTS.sh`, `CHECK_GPU.sh` и `PUBLISH_TO_GITHUB.sh`;
- создаются ярлыки меню приложений и, когда возможно, рабочего стола;
- запуск поддерживает Python 3.10–3.14 и автоматически выбирает интерпретатор;
- добавлен безопасный Linux PID-stop с проверкой командной строки процесса;
- добавлена установка официального GitHub CLI для Ubuntu/Debian;
- сценарий публикации проверяет секреты и запрещает отправку пользовательских файлов из `var/`;
- исправлена работа публикации после клонирования из Git bundle;
- добавлена детальная инструкция `docs/UBUNTU_RU.md`;
- установка, быстрый старт и публикация переписаны с приоритетом Ubuntu.

### Совместимость

- Windows-сценарии сохранены;
- live execution по-прежнему отсутствует;
- формат пользовательских данных и конфигурации не изменён.

## [0.1.0] — 2026-08-02

### Добавлено

- локальный FastAPI runtime и русскоязычный тёмный интерфейс;
- запуск Windows через `START.bat` и остановка через `STOP.bat`;
- synthetic demo market;
- публичный Binance USD-M Futures collector;
- локальная реконструкция L2-стакана и контроль последовательности;
- запись почасовых book/features JSONL.GZ;
- 36 признаков микроструктуры;
- CNN + residual + GRU + attention модель;
- direction, expected edge и volatility outputs;
- heuristic baseline;
- режимный router;
- семь объяснимых strategy components;
- queue/latency-aware fill model;
- paper broker с SL, TP, trailing и max holding time;
- независимый risk manager и kill switch;
- synthetic/recorded dataset и trainer;
- событийный backtest;
- SQLite audit trail;
- интеграционный слот CryptoHunter;
- полный комплект русской документации;
- GitHub Actions CI и сценарий private-публикации.

### Безопасность

- реальные ордера отсутствуют;
- `live_orders_enabled = false`;
- runtime bind по умолчанию только на localhost;
- runtime-данные и секреты исключены из Git.

### Известные ограничения

- один symbol;
- только Binance public market data;
- L2, не точный MBO;
- атомарный limit fill после модельной очереди;
- нет walk-forward orchestration/purge/embargo;
- нет live/testnet broker;
- нет доказанной доходности.
