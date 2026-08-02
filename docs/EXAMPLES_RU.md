# Практические сценарии

## Сценарий 1. Знакомство без биржи

Цель: убедиться, что программа запускается и интерфейс понятен.

1. В Ubuntu запустите `./start.sh`; в Windows — `START.bat`.
2. На «Главной» нажмите «Запустить демо».
3. Подождите заполнения последовательности из 64 состояний.
4. Наблюдайте стакан, режим, сигнал и причины отказов.
5. Через 10 минут остановите поток.

Оставьте настройки по умолчанию. Не делайте вывод о доходности.

## Сценарий 2. Проверка событийного бэктеста

```text
Источник: synthetic
Шагов: 6 000–20 000
Seed: 42 (в коде)
```

Проверьте:

- появились ли signals/orders/fills;
- рассчиталась ли equity curve;
- нет ли NaN/inf;
- заполнены ли rejection counts;
- создаётся ли `latest_backtest.json`.

## Сценарий 3. Первое тестовое обучение

```text
Источник: synthetic
Samples: 6 000
Epochs: 3–8
Batch: 128
Sequence: 64
Hidden: 96
```

Цель: проверить dataset, GPU, loss, checkpoint и загрузку модели.

Синтетический checkpoint не считается готовым для реального рынка.

## Сценарий 4. Сбор BTCUSDT

```text
symbol: BTCUSDT
depth_levels: 20
update_ms: 100
record_raw_events: true
record_features: true
```

1. Освободите место на диске.
2. Запустите публичный рынок.
3. Проверьте quality score.
4. Убедитесь, что создаются почасовые `book_*.jsonl.gz`.
5. Периодически копируйте закрытые часовые файлы.
6. После остановки проверьте gzip и timestamps.

## Сценарий 5. Recorded training

Перед стартом:

- данные идут строго по времени;
- нет смешения символов;
- достаточно разных рыночных режимов;
- config соответствует записанным levels;
- комиссии заданы реалистично.

Начните с меньшей выборки, затем увеличивайте.

## Сценарий 6. Консервативный execution stress

Базовая конфигурация:

```text
maker_fee_bps: 2.0
taker_fee_bps: 5.0
latency: 65 ms
queue_factor: 0.65
slippage: 0.5 bps
```

Стресс:

```text
maker_fee_bps: 3.0
taker_fee_bps: 7.5
latency: 165 ms
queue_factor: 1.0
slippage: 1.0 bps
```

Стратегия считается хрупкой, если небольшое ухудшение полностью уничтожает результат.

## Сценарий 7. Проверка порога confidence

Запустите одинаковый recorded backtest с:

```text
0.55
0.62
0.70
0.80
```

Сравните:

- число сделок;
- expectancy;
- profit factor;
- drawdown;
- regime distribution;
- устойчивость на следующем временном отрезке.

Не выбирайте порог по одному и тому же test-набору многократно.

## Сценарий 8. Проверка min net edge

Сравните 0.5, 1.2, 2.0, 3.0 б.п. при неизменных расходах. Смотрите не только PnL, но и сколько сигналов отфильтровано как `NO_NET_EDGE`.

## Сценарий 9. Низкий риск paper

```text
initial_balance: 10 000
risk_per_trade_pct: 0.10
max_position_notional_pct: 5
max_daily_loss_pct: 1
max_drawdown_pct: 5
max_consecutive_losses: 3
cooldown_seconds: 60
```

Такой профиль подходит для проверки поведения, а не максимизации результата.

## Сценарий 10. Проверка stop/take

Сформируйте сетку экспериментов, например:

```text
SL 12 / TP 20
SL 18 / TP 30
SL 25 / TP 40
```

Для каждого варианта используйте одинаковые данные и execution assumptions. Проверяйте распределение причин выхода.

## Сценарий 11. Изучение rejection counts

Если сделок нет, выгрузите частоты:

```text
FLAT
LOW_CONFIDENCE
NO_NET_EDGE
SPREAD_TOO_WIDE
DATA_QUALITY
COOLDOWN
REGIME_BLOCK
```

Оптимизация должна устранять причину, а не просто отключать фильтр.

## Сценарий 12. Проверка нового символа

1. Создайте отдельную копию `var/` через `NEUROSCALPER_VAR_DIR`.
2. Укажите новый symbol.
3. Соберите отдельную историю.
4. Обучите отдельный checkpoint.
5. Не используйте router memory BTC для другой монеты.
6. Сравните ликвидность, tick size и расходы.

## Сценарий 13. Изолированные эксперименты

Linux/macOS shell:

```bash
NEUROSCALPER_VAR_DIR="$PWD/experiments/btc_run_01" ./start.sh
```

Ubuntu:

```bash
NEUROSCALPER_VAR_DIR="$PWD/experiments/btc_run_01" ./start.sh
```

Windows PowerShell:

```powershell
$env:NEUROSCALPER_VAR_DIR = "$PWD\experiments\btc_run_01"
.\START.bat
```

Каждый эксперимент получает отдельные data/models/logs/reports.

## Сценарий 14. Проверка восстановления

1. Запустите demo.
2. Дождитесь виртуальной сделки.
3. Корректно остановите.
4. Скопируйте `paper_state.json`.
5. Запустите снова.
6. Убедитесь, что balance и история восстановились.

Не имитируйте аварийное выключение на единственной копии важных данных.

## Сценарий 15. Минимальный walk-forward вручную

```text
Период A: train
Период B: validation
Период C: test

Затем:
Период B: добавляется в train
Период C: validation
Период D: test
```

Текущий trainer использует внутренний 70/15/15 split. Для строгого walk-forward нужны внешние наборы/расширение pipeline — это пункт дорожной карты.
