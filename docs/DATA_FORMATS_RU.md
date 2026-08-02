# Форматы данных и файлов

## 1. Общая структура `var/`

```text
var/
├── data/
│   ├── config.json
│   ├── paper_state.json
│   ├── backtest_state.json
│   ├── router_memory.json
│   ├── backtest_router_memory.json
│   ├── neuroscalper.db
│   └── records/<SYMBOL>/
├── logs/neuroscalper.log
├── models/
├── reports/latest_backtest.json
└── cache/
```

Файлы runtime исключены из Git через `.gitignore`.

## 2. Почасовые JSONL.GZ записи

Recorder создаёт новый файл каждый UTC-час:

```text
book_YYYYMMDD_HH.jsonl.gz
features_YYYYMMDD_HH.jsonl.gz
raw_<kind>_YYYYMMDD_HH.jsonl.gz
```

Пример:

```text
var/data/records/BTCUSDT/book_20260802_14.jsonl.gz
```

Каждая строка gzip-файла — независимый JSON-объект. Такой формат позволяет:

- дописывать события без загрузки всего файла;
- читать потоково;
- переживать частичное повреждение одной строки;
- делить историю по часам;
- обрабатывать файлы параллельно.

## 3. Снимок стакана `book_*.jsonl.gz`

Типовая строка:

```json
{
  "symbol": "BTCUSDT",
  "exchange_ts_ms": 1785686400123,
  "local_ts_ms": 1785686400172,
  "sequence": 123456789,
  "bids": [
    {"price": 62100.1, "quantity": 1.25},
    {"price": 62100.0, "quantity": 0.84}
  ],
  "asks": [
    {"price": 62100.2, "quantity": 0.91},
    {"price": 62100.3, "quantity": 1.72}
  ],
  "last_trade_price": 62100.2,
  "last_trade_quantity": 0.015,
  "buyer_is_maker": false,
  "last_trade_ts_ms": 1785686400158,
  "liquidation_side": null,
  "liquidation_notional": 0.0,
  "liquidation_ts_ms": 0
}
```

### Временные метки

- `exchange_ts_ms` — время события, заявленное биржей;
- `local_ts_ms` — локальное время получения/сборки снимка;
- `last_trade_ts_ms` — время последней известной сделки;
- `liquidation_ts_ms` — время последней ликвидации.

Все значения — Unix milliseconds.

### Стакан

- `bids` должны идти от максимальной цены к меньшей;
- `asks` — от минимальной к большей;
- цены и количества сохраняются как числа с плавающей точкой;
- пустая сторона считается невалидной для обучения и бэктеста.

### `buyer_is_maker`

Для Binance aggTrade:

- `true` обычно означает, что покупатель был maker, следовательно агрессором был продавец;
- `false` означает агрессивную покупку.

Fill-модель использует этот признак для определения, какая сторона лимитной очереди потребляется.

## 4. Feature frame `features_*.jsonl.gz`

Пример:

```json
{
  "symbol": "BTCUSDT",
  "exchange_ts_ms": 1785686400123,
  "local_ts_ms": 1785686400172,
  "names": ["spread_bps", "imbalance_1", "microprice_delta_bps"],
  "values": [0.0161, 0.184, 0.0042],
  "regime": "TREND_UP",
  "metadata": {
    "feature_version": 1
  }
}
```

`names` и `values` должны иметь одинаковую длину и стабильный порядок. В версии 0.1.1 рассчитывается 36 значений. Подробности: [FEATURES_RU.md](FEATURES_RU.md).

Полный `lob_tensor` в feature-файл намеренно не записывается, чтобы снизить объём. При обучении он восстанавливается из `book` снимков.

## 5. Конфигурация `config.json`

Это UTF-8 JSON, соответствующий `AppConfig`. Полная схема описана в [CONFIGURATION_REFERENCE_RU.md](CONFIGURATION_REFERENCE_RU.md).

Не храните в нём API secret.

## 6. Paper state

`paper_state.json` имеет служебную версию:

```json
{
  "version": 1,
  "balance": 10000.0,
  "peak_balance": 10020.5,
  "position": null,
  "pending_orders": [],
  "trades": [],
  "last_event": "Ожидание"
}
```

Если позиция есть, направление хранится строкой `LONG` или `SHORT`. У заявки сериализуются `side` и `order_type`.

Файл записывается через `.tmp` и атомарную замену.

## 7. Router memory

Файл роутера хранит ограниченную статистическую память результатов по режимам рынка. Он не является checkpoint нейросети. При удалении роутер начнёт со стандартных приоритетов.

Не переносите router memory между несопоставимыми символами без отдельной проверки.

## 8. SQLite `neuroscalper.db`

База работает в WAL-режиме. Основные таблицы:

### `signals`

| Поле | Назначение |
|---|---|
| `id` | уникальный идентификатор |
| `ts_ms` | время сигнала |
| `symbol` | инструмент |
| `direction` | LONG/SHORT/FLAT |
| `confidence` | уверенность |
| `net_edge_bps` | ожидаемое преимущество после расходов |
| `status` | CREATED/ORDERED/REJECTED/OBSERVED и др. |
| `payload_json` | полный JSON сигнала |

### `trades`

Хранит закрытые сделки и полный `payload_json`.

### `runs`

Хранит запуск обучения/бэктеста:

- `started_ts_ms`;
- `finished_ts_ms`;
- `kind`;
- `status`;
- payload.

### `metrics`

Периодические runtime и backtest метрики.

### `decisions`

Audit trail действий: ORDERED, REJECTED, CLOSED и причины.

## 9. Checkpoint модели

Ожидаемые файлы:

```text
var/models/best_model.pt
var/models/best_model.json
var/models/lob_scalper_<timestamp>.pt
```

`.pt` содержит PyTorch state/config payload. `.json` содержит читаемые метаданные обучения и метрики.

Checkpoint совместим только при совпадении:

- архитектуры;
- hidden size;
- числа уровней;
- sequence length;
- порядка входных каналов;
- версии подготовки данных.

Перед загрузкой чужого `.pt` учитывайте риск небезопасной десериализации. Используйте только доверенные файлы.

## 10. Отчёт бэктеста

`latest_backtest.json`:

```json
{
  "source": "recorded",
  "steps": 50000,
  "elapsed_seconds": 12.34,
  "metrics": {
    "initial_balance": 10000.0,
    "final_equity": 10042.0,
    "net_profit": 42.0,
    "return_pct": 0.42,
    "trades": 18,
    "wins": 10,
    "losses": 8,
    "win_rate_pct": 55.556,
    "profit_factor": 1.21,
    "max_drawdown_pct": 0.38,
    "fill_rate_pct": 47.1
  },
  "equity_curve": [[1785686400000, 10000.0]],
  "trades": [],
  "regime_counts": {},
  "rejection_counts": {},
  "notes": []
}
```

Кривая downsampled примерно до 800 точек, а список сделок ограничен последними 500.

## 11. Лог

`var/logs/neuroscalper.log` — текстовый UTF-8 журнал. Он может содержать:

- запуск/остановку;
- соединение и переподключение;
- обучение;
- бэктест;
- fill и закрытие позиции;
- stack trace ошибки.

Секреты в лог писать запрещено.

## 12. Проверка JSONL

Пример Python:

```python
from __future__ import annotations

import gzip
import json
from pathlib import Path

path = Path("var/data/records/BTCUSDT/book_20260802_14.jsonl.gz")
valid = 0
invalid = 0

with gzip.open(path, "rt", encoding="utf-8") as stream:
    for number, line in enumerate(stream, start=1):
        try:
            row = json.loads(line)
            assert row["bids"] and row["asks"]
            assert row["bids"][0]["price"] < row["asks"][0]["price"]
            valid += 1
        except Exception as exc:
            invalid += 1
            print(f"Строка {number}: {exc}")

print({"valid": valid, "invalid": invalid})
```

## 13. Конвертация в Parquet

Для очень больших исследований JSONL.GZ удобно оставить как сырой audit trail, а производный датасет конвертировать в Parquet. Не удаляйте исходник до сверки количества событий, timestamps и контрольных сумм.

## 14. Правила версионирования данных

При изменении признаков или схемы добавляйте:

- `schema_version`;
- `feature_version`;
- commit SHA;
- symbol/exchange;
- временной диапазон;
- параметры комиссии;
- checksum исходных файлов.

Без этого невозможно надёжно воспроизвести эксперимент.
