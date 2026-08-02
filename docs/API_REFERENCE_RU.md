# HTTP API

## 1. Общая информация

Локальный сервер по умолчанию доступен по адресу:

```text
http://127.0.0.1:8094
```

API не предназначен для открытия в публичный интернет. В версии 0.1.1 нет аутентификации, TLS и разграничения ролей.

Формат запросов и ответов — JSON, кроме главной HTML-страницы и статических файлов.

## 2. Интерактивная схема

FastAPI обычно предоставляет:

```text
/docs
/redoc
/openapi.json
```

Используйте их только локально.

## 3. `GET /`

Возвращает основной интерфейс `index.html`.

## 4. `GET /health`

Лёгкая проверка процесса.

Пример ответа:

```json
{
  "ok": true,
  "running": true,
  "mode": "demo"
}
```

`ok: true` означает, что HTTP runtime отвечает, а не то, что модель прибыльна или Binance подключён.

## 5. `GET /api/status`

Возвращает полный текущий статус приложения. Состав может расширяться между версиями. Основные разделы:

```json
{
  "app": {
    "running": true,
    "mode": "demo",
    "symbol": "BTCUSDT",
    "live_orders_enabled": false
  },
  "market": {},
  "model": {},
  "signal": {},
  "risk_decision": {},
  "paper": {},
  "risk": {},
  "orderbook": {},
  "quality": {},
  "training": {},
  "backtest": {}
}
```

Ключ `live_orders_enabled` должен оставаться `false` в версии 0.1.1.

## 6. `GET /api/history`

Возвращает историю для интерфейса:

- последние сигналы;
- закрытые сделки;
- решения/отказы;
- кривую equity или другие накопленные данные.

Точный объём ограничен runtime и SQLite-запросами, чтобы интерфейс не загружал всю базу.

## 7. `GET /api/config`

Возвращает текущую конфигурацию в виде вложенного JSON.

Пример:

```bash
curl http://127.0.0.1:8094/api/config
```

## 8. `POST /api/config`

Применяет частичный patch.

Тело:

```json
{
  "patch": {
    "market": {
      "symbol": "ETHUSDT"
    },
    "risk": {
      "risk_per_trade_pct": 0.15
    }
  }
}
```

Пример PowerShell:

```powershell
$body = @{
  patch = @{
    market = @{ symbol = "ETHUSDT" }
    risk = @{ risk_per_trade_pct = 0.15 }
  }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8094/api/config" `
  -ContentType "application/json" `
  -Body $body
```

При некорректном значении сервер возвращает HTTP 422.

После изменения формы входа модели остановите поток, переобучите модель и проведите новый бэктест.

## 9. `POST /api/actions/start-demo`

Запускает синтетический рынок.

Тело не требуется.

```bash
curl -X POST http://127.0.0.1:8094/api/actions/start-demo
```

Демо предназначено для проверки механики и интерфейса.

## 10. `POST /api/actions/start-market`

Запускает публичный Binance USD-M Futures поток для выбранного символа.

```bash
curl -X POST http://127.0.0.1:8094/api/actions/start-market
```

API-ключ для публичных данных не требуется. Ошибки соединения появляются в статусе и журнале.

## 11. `POST /api/actions/stop`

Останавливает активный market/demo task и закрывает связанные ресурсы.

```bash
curl -X POST http://127.0.0.1:8094/api/actions/stop
```

## 12. `POST /api/actions/reset-paper`

Сбрасывает виртуальный счёт.

```bash
curl -X POST http://127.0.0.1:8094/api/actions/reset-paper
```

Операция изменяет `paper_state.json`; используйте осознанно.

## 13. `POST /api/actions/reset-kill-switch`

Сбрасывает аварийную блокировку и счётчик последовательных убытков.

```bash
curl -X POST http://127.0.0.1:8094/api/actions/reset-kill-switch
```

API не проверяет, устранена ли причина срабатывания. Это ответственность оператора.

## 14. `POST /api/actions/train`

Запускает асинхронное обучение.

Тело:

```json
{
  "source": "synthetic",
  "samples": 6000
}
```

Поля:

- `source`: `synthetic` либо `recorded`; иные значения приводятся к `synthetic`;
- `samples`: `800…100000`.

Пример:

```bash
curl -X POST http://127.0.0.1:8094/api/actions/train \
  -H "Content-Type: application/json" \
  -d '{"source":"recorded","samples":20000}'
```

Начальный ответ сообщает, что задача поставлена. Прогресс нужно читать через `GET /api/status`.

Если обучение уже идёт:

```json
{
  "ok": false,
  "message": "Обучение уже выполняется"
}
```

## 15. `POST /api/actions/backtest`

Запускает событийный бэктест в отдельной задаче.

Тело:

```json
{
  "source": "synthetic",
  "steps": 6000
}
```

Ограничения:

- `steps`: `500…2000000`;
- `source`: `synthetic` либо `recorded`.

Прогресс доступен в `/api/status`.

## 16. `GET /api/reports/latest-backtest`

Возвращает `var/reports/latest_backtest.json`.

Возможные ошибки:

- HTTP 404 — бэктест ещё не запускался;
- HTTP 500 — JSON отчёта повреждён.

## 17. Типовой сценарий автоматизации

```text
GET  /health
POST /api/config
POST /api/actions/start-market
GET  /api/status      — периодический опрос
POST /api/actions/stop
POST /api/actions/backtest
GET  /api/reports/latest-backtest
```

## 18. Python-пример

```python
from __future__ import annotations

import time
import httpx

BASE = "http://127.0.0.1:8094"

with httpx.Client(base_url=BASE, timeout=30.0) as client:
    health = client.get("/health")
    health.raise_for_status()
    print(health.json())

    response = client.post(
        "/api/config",
        json={"patch": {"market": {"symbol": "BTCUSDT"}}},
    )
    response.raise_for_status()

    client.post("/api/actions/start-demo").raise_for_status()
    time.sleep(3)

    state = client.get("/api/status").json()
    print(state["app"])
    print(state.get("paper"))

    client.post("/api/actions/stop").raise_for_status()
```

## 19. Правила безопасной интеграции

- не открывайте порт 8094 на внешний интерфейс;
- не добавляйте торговые API-ключи в frontend;
- не храните секреты в `config.json`;
- перед будущим live API добавьте аутентификацию, CSRF-защиту, TLS и audit log;
- любые write-команды должны быть идемпотентными либо иметь request ID;
- live order router должен быть отдельным модулем за feature flag;
- риск-менеджер должен оставаться обязательным шлюзом.
