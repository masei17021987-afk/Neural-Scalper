# Руководство разработчика

## 1. Требования

Рекомендуемая среда:

- Python 3.11 x64;
- Git;
- Node.js только для синтаксической проверки frontend;
- CUDA-совместимый PyTorch опционально;
- Windows 10/11 или современный Linux.

## 2. Подготовка окружения

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

## 3. Запуск разработчика

```bash
python -m neuroscalper.launcher --host 127.0.0.1 --port 8094
```

Если пакет не установлен editable:

```bash
PYTHONPATH=src python -m neuroscalper.launcher
```

## 4. Модульные границы

| Папка | Ответственность |
|---|---|
| `market/` | получение, реконструкция и качество данных |
| `features/` | детерминированные признаки без будущего |
| `models/` | инференс, нейросеть, baseline, router |
| `strategies/` | объяснимые голосующие компоненты |
| `decision.py` | объединение прогнозов в сигнал |
| `risk/` | обязательный шлюз ограничений |
| `execution/` | модель заявок и paper-счёт |
| `training/` | построение dataset и обучение |
| `backtest/` | детерминированный replay |
| `web/` | API и UI |
| `runtime.py` | orchestration, но не бизнес-математика модулей |

## 5. Основной контракт данных

`BookSnapshot` → `FeatureFrame` → `ModelPrediction` + `StrategyVote` → `TradingSignal` → `RiskDecision` → `Order`/`Fill`/`ClosedTrade`.

Новые модули должны принимать и возвращать типизированные структуры, а не случайные словари.

## 6. Добавление биржи

Создайте adapter, который выдаёт корректный `BookSnapshot`:

- локальный монотонный timestamp;
- exchange timestamp;
- sequence;
- отсортированные bids/asks;
- last trade с aggressor side;
- ликвидации, если доступны.

Обязательные проверки:

- snapshot + diff bootstrap;
- gap detection;
- resync;
- heartbeat/reconnect;
- rate limits;
- формат decimal;
- crossed book;
- дубли событий.

Не подключайте новый источник напрямую к модели, минуя общий snapshot.

## 7. Добавление признака

1. Опишите экономический смысл.
2. Докажите отсутствие look-ahead.
3. Добавьте вычисление в `features/microstructure.py`.
4. Сохраните стабильный порядок `names`/`values`.
5. Обновите `FEATURES_RU.md` и feature version.
6. Добавьте unit test.
7. Переобучите модель.
8. Проведите ablation test.

Нельзя менять порядок признаков и продолжать использовать старый checkpoint.

## 8. Добавление стратегии-помощника

Стратегия возвращает `StrategyVote`:

- `strategy_id`;
- signed score;
- confidence;
- короткое русское explanation;
- metadata.

Правила:

- отсутствие сигнала должно давать score около нуля;
- confidence не должен маскировать экстремальный score;
- стратегия не отправляет ордер;
- стратегия не меняет risk state;
- все пороги документируются.

## 9. Изменение нейросети

Согласованно обновите:

- `models/network.py`;
- manager load/save;
- trainer;
- checkpoint metadata;
- shape tests;
- документацию;
- версию модели.

Добавьте migration или явный отказ для несовместимого checkpoint.

## 10. Изменение метки

Метка является частью торговой гипотезы. При изменении горизонта, fee formula или threshold:

- увеличьте dataset/label version;
- не смешивайте старые и новые samples;
- пересоздайте train/valid/test;
- сохраните точную формулу в experiment manifest;
- проведите walk-forward сравнение.

## 11. Добавление live execution

Не добавляйте отправку ордера в `PaperBroker`. Создайте отдельный интерфейс:

```python
class ExecutionBroker(Protocol):
    async def submit(...): ...
    async def cancel(...): ...
    async def reconcile(...): ...
    async def emergency_flatten(...): ...
```

Обязательные барьеры:

- feature flag, по умолчанию false;
- testnet implementation;
- API key из secret store;
- ключ без withdrawal permission;
- idempotency/client order ID;
- position/order reconciliation;
- user data stream;
- timeout и unknown-order state;
- circuit breaker;
- отдельное подтверждение в UI;
- маленький hard notional limit в executor;
- audit log до и после API call.

## 12. Runtime не должен становиться монолитом

`runtime.py` координирует задачи, но формулы должны оставаться в специализированных модулях. При добавлении крупной логики создавайте сервис/класс и покрывайте его тестом.

## 13. Логирование

Используйте стандартный `logging`:

```python
logger = logging.getLogger(__name__)
```

Уровни:

- DEBUG — детали разработки;
- INFO — нормальные lifecycle события;
- WARNING — восстановимая аномалия;
- ERROR/EXCEPTION — сбой операции.

Не логируйте secret, полный API signature или приватные заголовки.

## 14. Тесты

Минимум перед коммитом:

```bash
python -m compileall -q src tests integration
python -m pytest -q
node --check src/neuroscalper/web/static/app.js
```

Типы тестов:

- order book sequence/reconstruction;
- feature shape and finite values;
- dataset label causality;
- risk block reasons;
- queue/fill/fee math;
- paper state recovery;
- API smoke;
- deterministic backtest.

## 15. Детерминизм

Для synthetic data и backtest сохраняйте seed. Не считайте результаты сопоставимыми, если отличаются:

- seed;
- commit;
- config;
- dataset checksum;
- model checkpoint;
- dependency versions.

## 16. Код-стиль

- type hints для публичных функций;
- `from __future__ import annotations`;
- небольшие функции;
- `dataclass(slots=True)` для domain/config объектов;
- явная обработка ошибок;
- комментарии объясняют причину, а не повторяют код;
- пользовательские сообщения — понятный русский язык.

## 17. Pull request

PR должен содержать:

- проблему и цель;
- перечень изменений;
- влияние на данные/модель/риск;
- миграцию;
- тесты;
- результаты до/после;
- новые ограничения;
- скриншот при изменении UI.

## 18. Версионирование

Используйте semantic versioning:

- PATCH — исправление без изменения формата;
- MINOR — новая совместимая функция;
- MAJOR — несовместимая схема/архитектура/API.

Model schema и data schema должны иметь отдельные версии.
