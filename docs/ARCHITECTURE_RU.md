# Архитектура

## Поток данных

```text
Binance public WebSocket / SyntheticMarket
                    │
                    ▼
           LocalOrderBook + sequence gate
                    │
                    ├── EventRecorder
                    ├── DataQualityMonitor
                    ▼
       MicrostructureFeatureEngine (36 features)
                    │
                    ├── LOB tensor [T, L, 4]
                    └── regime classification
                    ▼
        RiskAwareLOBNet / heuristic fallback
                    │
                    ├── SHORT / FLAT / LONG
                    ├── expected edge in bps
                    └── volatility head
                    ▼
      HierarchicalRegimeRouter + 7 rule experts
                    │
                    ▼
               DecisionEngine
                    │
                    ▼
                RiskManager
                    │
                    ▼
       QueueAwareFillModel + PaperBroker
                    │
                    ├── SQLite audit trail
                    ├── atomic paper state
                    └── local web dashboard
```

## LocalOrderBook

Последовательность:

1. WebSocket запускается до REST snapshot.
2. События временно складываются в очередь.
3. Загружается `lastUpdateId`.
4. Старые diff-события отбрасываются.
5. Первое применяемое событие должно перекрывать snapshot.
6. Для следующих USD-M событий проверяется `pu`.
7. При разрыве соединение закрывается, и книга строится заново.

## Признаки

Основные группы:

- spread и microprice;
- imbalance на 1/5/10/20 уровнях;
- глубина и наклон стакана;
- доходности на нескольких коротких окнах;
- realized volatility;
- trade-flow imbalance;
- интенсивность и ускорение объёма;
- price impact;
- задержка;
- давление ликвидаций;
- liquidity score;
- momentum / mean-reversion pressure;
- event rate.

## Нейросеть

`RiskAwareLOBNet`:

1. Conv2D обрабатывает время и уровни стакана.
2. Residual blocks выделяют локальные паттерны.
3. Усреднение по уровням создаёт временную последовательность.
4. Двухслойная GRU моделирует развитие рынка.
5. Attention выбирает наиболее важные моменты.
6. Три головы возвращают направление, edge и volatility.

При отсутствии checkpoint используется прозрачный `microstructure_baseline`, поэтому интерфейс и paper-тест доступны до обучения.

## Иерархический роутер

Режимы:

- `RANGE`;
- `TREND_UP` / `TREND_DOWN`;
- `BREAKOUT_UP` / `BREAKOUT_DOWN`;
- `HIGH_VOL`;
- `LOW_LIQUIDITY`.

Для каждого режима задаются:

- вес модели;
- вес правил;
- стиль исполнения;
- множитель позиции;
- понятное объяснение.

После закрытия сделки ограниченная память обновляет среднюю награду режима. Изменение веса ограничено, чтобы короткая серия сделок не могла резко перестроить систему.

## Исполнение

Рыночная заявка проходит книгу по уровням и получает VWAP плюс модельное проскальзывание.

Лимитная заявка:

1. появляется после `assumed_latency_ms`;
2. получает оценку объёма перед собой;
3. ждёт агрессивные сделки на своём уровне;
4. сначала списывает очередь;
5. исполняется после прохождения очереди;
6. отменяется после `cancel_after_ms`.

## Риск

Риск-менеджер не является нейросетью и не может быть обойдён её прогнозом.

Проверки:

- FLAT;
- kill switch;
- устаревшие данные;
- широкий спред;
- минимальная уверенность;
- net edge после расходов;
- лимит позиций;
- запрещённый режим;
- серия убытков;
- cooldown;
- data quality.

Размер позиции берётся как минимум между размером по стоп-риску и максимальным notional.

## Хранилище

SQLite работает в WAL-режиме и хранит:

- signals;
- decisions;
- trades;
- training/backtest runs;
- periodic metrics.

Paper state пишется через временный файл с последующей атомарной заменой.
