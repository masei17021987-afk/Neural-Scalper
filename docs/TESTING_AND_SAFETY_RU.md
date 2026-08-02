# Проверка и безопасность

## Порядок допуска

```text
unit tests
→ синтетическое демо
→ синтетический бэктест
→ сбор реального стакана
→ chronological train/validation/test
→ recorded-data backtest
→ длительный shadow/paper
→ stress test расходов
→ только затем проектирование отдельного live router
```

## Что считать

Минимум:

- net PnL после расходов;
- число сделок;
- profit factor;
- max drawdown;
- expectancy;
- fill rate;
- maker/taker ratio в будущей версии;
- результат по режимам;
- результат LONG/SHORT;
- чувствительность к комиссии и latency.

## Запрещённые выводы

Нельзя считать стратегию готовой, если:

- она проверена только на синтетике;
- test использовался для настройки;
- нет достаточного числа сделок;
- прибыль исчезает при комиссии ×1.5;
- лимитное исполнение считается по одному касанию цены;
- есть только accuracy без net PnL;
- данные случайно перемешаны во времени.

## Текущая безопасность live

В этой версии отсутствует код отправки реальных ордеров. `live_orders_enabled` всегда возвращает `false`. Binance collector обращается только к публичным market-data endpoint.

Для будущего live-модуля обязательны:

- отдельный API key без withdrawal;
- IP allowlist;
- testnet/dry-run;
- reconciliation позиции и ордеров;
- idempotency client order ID;
- one-position actor lock;
- stale snapshot guard;
- аварийное закрытие;
- подтверждение минимального реального размера вручную.
