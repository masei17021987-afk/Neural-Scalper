# Дорожная карта

## Принцип развития

Новые функции добавляются только после того, как предыдущий уровень измерим, воспроизводим и защищён. Переход к live не должен опережать качество данных и симуляции.

## Этап 0 — текущая версия 0.1.1

- один Binance Futures symbol;
- public market data;
- L2 reconstruction;
- 36 features;
- CNN/GRU/attention;
- heuristic baseline;
- regime router;
- paper broker;
- event backtest;
- русская UI/документация;
- no live orders.

## Этап 1 — качество данных 0.2

- отдельное сохранение raw depth/trade/liquidation;
- checksum и schema version;
- recorder health dashboard;
- gaps/resync statistics;
- exchange/local latency distribution;
- disk quota/rotation;
- Parquet conversion;
- replay validation.

Критерий готовности: любой час можно воспроизвести с одинаковым итоговым стаканом.

## Этап 2 — исследовательский pipeline 0.3

- внешний dataset manifest;
- фиксированные time horizons;
- multi-horizon targets;
- purge/embargo;
- walk-forward orchestrator;
- calibration;
- class/regime balancing;
- experiment registry;
- reproducible seeds/dependency lock;
- ablation reports.

## Этап 3 — execution simulation 0.4

- partial fills;
- amend/cancel lifecycle;
- вероятностная очередь;
- empirical latency model;
- adverse selection metrics;
- maker/taker policy comparison;
- stochastic missed events;
- stress scenario runner;
- L3 adapter для источников, где доступно MBO.

## Этап 4 — multi-model 0.5

- DeepLOB/TCN/Transformer baselines;
- CatBoost/LightGBM tabular baseline;
- model ensemble;
- uncertainty/calibration head;
- fill probability model;
- expected adverse move model;
- regime specialists;
- router evaluation.

## Этап 5 — portfolio/multi-symbol 0.6

- несколько symbols;
- isolated runtime per symbol;
- shared feature bus;
- portfolio risk;
- correlation and concentration limits;
- GPU batching;
- symbol scanner;
- dynamic universe based on measured liquidity.

## Этап 6 — testnet execution 0.7

- exchange abstraction;
- Binance testnet broker;
- client order IDs;
- reconciliation;
- private user stream;
- unknown-order handling;
- cancel-all/flatten;
- hard notional cap;
- key vault;
- explicit UI arming;
- testnet-only build flag.

Критерий: после любого disconnect локальное состояние автоматически совпадает с биржей либо система блокируется.

## Этап 7 — shadow validation 0.8

- live predictions without orders;
- expected vs observed fills;
- actual latency telemetry;
- drift detection;
- daily report;
- alerting;
- model rollback;
- champion/challenger.

## Этап 8 — execution agent 0.9

- SAC/DSAC только для размера/агрессивности/отмены;
- action constraints;
- offline pretraining;
- conservative reward;
- simulator randomization;
- rule-based fallback;
- policy audit.

RL не получает права обходить risk manager.

## Этап 9 — ограниченный live 1.0

Только после независимой проверки:

- отдельный subaccount;
- минимальный капитал;
- без withdrawal permissions;
- IP whitelist;
- manual approval;
- server-side caps;
- 24/7 monitoring;
- rollback;
- emergency procedures;
- signed release.

## Долгосрочные направления

- Bybit/OKX/Bitget adapters;
- funding/basis/OI/mark/index;
- options/implied volatility context;
- cross-exchange lead-lag;
- news only as slow context, не как HFT input;
- локальная LLM для объяснений и анализа журнала;
- интеграция с основным CryptoHunter;
- desktop shell и автообновление;
- multi-user research server.

## Что не является приоритетом

- красивый live toggle без reconciliation;
- увеличение плеча;
- огромная LLM в основном сигнале;
- сотни индикаторов без ablation;
- оптимизация по одному короткому бэктесту;
- автоматическое online learning без rollback.
