# Подробное описание программы

## 1. Наименование

**CryptoHunter Neural Scalper** — локальная программная платформа для исследования нейросетевого скальпинга на криптовалютных рынках по данным стакана и потока сделок.

Версия документа: 0.1.1.

## 2. Назначение

Система создаёт единый воспроизводимый контур:

```text
получение рыночных событий
→ восстановление стакана
→ контроль качества
→ расчёт микроструктурных признаков
→ прогноз модели
→ объяснимые правила
→ решение LONG/SHORT/FLAT
→ проверка риска
→ виртуальное исполнение
→ журнал и отчёт
```

Цель — не «показать стрелку», а проверить, остаётся ли торговая гипотеза жизнеспособной после комиссии, спреда, задержки, очереди и проскальзывания.

## 3. Для кого предназначена

### Оператор без глубоких технических знаний

Получает понятный тёмный интерфейс, запуск двойным щелчком, простые подсказки и объяснение каждого отказа.

### Исследователь/квант

Получает сырой рынок, feature frames, хронологический dataset, checkpoint, event replay, execution assumptions и audit trail.

### Разработчик CryptoHunter

Получает модульные границы, API, integration slot и основу для multi-symbol/testnet/live расширений.

## 4. Основные задачи

- собирать непрерывную историю L2-стакана;
- сохранять биржевое и локальное время;
- обнаруживать рассинхронизацию и плохие данные;
- рассчитывать 36 признаков;
- прогнозировать направление, edge и volatility;
- добавлять контекст детекторов импульса, drop, pump, liquidation, volume, spread и waves;
- запрещать слабые/опасные входы;
- моделировать заявки и позиции;
- обучать на synthetic и recorded data;
- воспроизводить историю;
- объяснять решение человеку.

## 5. Принципы продукта

### Простота

Сложная математика скрыта за понятными словами. Пользователь видит не только число, но и смысл: «спред слишком широкий», «данные устарели», «после расходов преимущества нет».

### Локальность

Исходники, датасеты, модели, журналы и paper-счёт находятся на компьютере пользователя.

### Безопасность

Модель не может самостоятельно отключить риск-менеджер. Реальный executor отсутствует.

### Воспроизводимость

Результат связывается с config, source, seed, checkpoint, timestamps и отчётом.

### Объяснимость

Signal содержит reasons, warnings, regime, probabilities и strategy votes.

## 6. Функциональные подсистемы

### Market subsystem

- synthetic market;
- Binance public collector;
- REST snapshot bootstrap;
- WebSocket diff processing;
- trades/liquidations;
- reconnect/resync;
- hourly compressed recorder.

### Feature subsystem

Создаёт числовой вектор и последовательность LOB `[time, level, channel]`. Все признаки рассчитываются только из текущего и прошлого состояния.

### Intelligence subsystem

- heuristic baseline;
- RiskAwareLOBNet;
- regime router;
- strategy ensemble;
- decision engine.

### Risk subsystem

- confidence/edge/spread/data filters;
- position sizing;
- daily loss;
- high-water drawdown;
- cooldown/loss streak;
- kill switch.

### Execution subsystem

- market/limit/post-only abstractions;
- latency;
- queue ahead;
- maker/taker fees;
- slippage;
- timeout;
- paper position lifecycle.

### Research subsystem

- dataset creation;
- conservative executable labels;
- train/validation/test;
- multi-head loss;
- checkpoint selection;
- event backtest and metrics.

### Presentation subsystem

- FastAPI;
- HTML/CSS/JavaScript dashboard;
- seven logical sections;
- Russian hints;
- REST API.

## 7. Входные данные

- depth snapshot/diffs;
- aggregate trades;
- aggressor side;
- liquidation events;
- timestamps;
- параметры исполнения и риска.

Будущие источники: OI, funding, basis, mark/index, multi-exchange lead-lag.

## 8. Выходные данные

- market status;
- quality report;
- feature frames;
- model prediction;
- trading signal;
- risk decision;
- virtual order/fill/position/trade;
- SQLite audit;
- training checkpoint;
- backtest report.

## 9. Нефункциональные требования

- запуск на Windows в два клика;
- работа без GPU;
- локальный bind;
- безопасное восстановление;
- отсутствие secrets в исходниках;
- понятные ошибки;
- модульность;
- тестируемость;
- возможность длительной записи;
- переносимость `var/`.

## 10. Типичный жизненный цикл

```text
Установка
→ Demo smoke test
→ Synthetic backtest
→ Synthetic training smoke
→ Public market recording
→ Data validation
→ Recorded training
→ Recorded backtest
→ Stress tests
→ Long paper/shadow validation
→ только затем проектирование testnet executor
```

## 11. Чем программа не является

- готовым HFT colocated engine;
- гарантированно прибыльным ботом;
- биржевым терминалом;
- хранителем реальных API-ключей;
- полноценной маржинальной моделью;
- multi-user SaaS;
- доказательством результата сторонних исследований.

## 12. Критерии успешности проекта

На текущем этапе успех — это:

- непрерывная и проверяемая история;
- отсутствие утечки будущего;
- реалистичные расходы;
- воспроизводимый backtest;
- объяснимые rejection counts;
- устойчивость на новых периодах;
- совпадение shadow predictions с наблюдаемым рынком;
- безопасное поведение при сбоях.
