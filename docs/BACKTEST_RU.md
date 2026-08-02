# Событийный бэктест

## 1. Цель

Бэктест проверяет полную последовательность:

```text
snapshot
→ признаки
→ модель
→ роутер
→ сигнал
→ риск
→ заявка
→ задержка
→ очередь/fill
→ позиция
→ стоп/тейк/trailing/time exit
→ PnL
```

Он не просто смотрит, коснулась ли свеча цены заявки.

## 2. Источники

### Synthetic

Создаётся `SyntheticMarket` с seed 42. Подходит для воспроизводимой проверки механики.

### Recorded

Читаются почасовые `book_*.jsonl.gz` выбранного символа. Файлы идут в сортированном порядке.

## 3. Изоляция состояния

Бэктест использует отдельные файлы:

```text
var/data/backtest_router_memory.json
var/data/backtest_state.json
```

Paper-счёт обычного runtime не должен изменяться.

Перед прогоном backtest broker сбрасывается к initial balance.

## 4. Частота решения

В бэктесте решение формируется не чаще одного раза в 500 мс event time.

В обычном runtime — не чаще одного раза в секунду.

Это различие нужно учитывать при сравнении live-like paper и backtest. В будущей версии частота должна стать явным параметром.

## 5. Market order

После `assumed_latency_ms` заявка становится активной.

Fill-модель:

1. идёт по противоположной стороне книги;
2. забирает quantity уровней до заполнения;
3. рассчитывает VWAP;
4. при нехватке видимой глубины использует цену последнего доступного уровня для остатка;
5. добавляет slippage;
6. списывает taker fee.

Для BUY slippage повышает цену. Для SELL — понижает.

## 6. Limit и post-only

Цена заявки:

```text
BUY  → best bid
SELL → best ask
```

Оценка очереди:

```text
queue_ahead = top_level_quantity × queue_factor
```

После latency заявка ждёт агрессивную сделку на своём уровне.

Для BUY требуется агрессивная продажа по цене `<= limit`.

Для SELL требуется агрессивная покупка по цене `>= limit`.

Сначала trade quantity уменьшает queue ahead. После прохождения очереди оставшаяся заявка исполняется атомарно и получает maker fee.

### Важное ограничение

Текущая модель консервативна по факту допуска fill, но после прохождения очереди не моделирует частичное исполнение. Это упрощение MVP.

## 7. Отмена заявки

Для resting order:

```text
cancel time = created + latency + cancel_after_ms
```

Если до этого момента fill не получен, заявка получает `CANCELLED` с причиной `timeout`.

## 8. Защита от повторного учёта сделки

Для каждого order хранится ключ последней обработанной сделки:

```text
(trade timestamp, trade price, trade quantity)
```

Повторный snapshot с той же последней сделкой не уменьшает очередь второй раз.

## 9. Открытие позиции

После fill:

- direction определяется стороной;
- entry fee сразу вычитается из balance;
- stop и take рассчитываются от entry;
- trailing anchor равен entry;
- regime сохраняется для последующего обновления router memory.

## 10. Закрытие LONG

- выход моделируется SELL market order;
- stop/trailing проверяется по best bid;
- take profit проверяется по best bid;
- trailing anchor растёт вместе с mid;
- после активации stop подтягивается вверх;
- time exit срабатывает по event time.

## 11. Закрытие SHORT

- выход моделируется BUY market order;
- stop/trailing проверяется по best ask;
- take profit проверяется по best ask;
- trailing anchor уменьшается;
- stop подтягивается вниз;
- time exit аналогичен LONG.

## 12. PnL

LONG gross:

```text
(exit - entry) × quantity
```

SHORT gross:

```text
(entry - exit) × quantity
```

Fees:

```text
entry fee + exit taker fee
```

Net:

```text
gross - all fees
```

Entry fee уже вычиталась из balance при открытии. При закрытии balance увеличивается на gross минус exit fee, что не допускает повторного списания entry fee.

## 13. Риск в бэктесте

Проверяются те же ограничения, кроме wall-clock staleness. Параметр `check_staleness=false`, потому что исторические события по определению старые.

После закрытия сделки обновляются:

- daily realized PnL;
- серия убытков;
- cooldown time в event time;
- router memory по regime.

## 14. Метрики

### `initial_balance`

Начальный виртуальный капитал.

### `final_equity`

Последний equity.

### `net_profit`

```text
final_equity - initial_balance
```

### `return_pct`

Net profit в процентах initial balance.

### `trades`, `wins`, `losses`

Число закрытых сделок.

### `win_rate_pct`

Доля прибыльных сделок.

### `profit_factor`

```text
gross profit / gross loss
```

При отсутствии убытков используется упрощённое конечное значение, поэтому результат на малом числе сделок нельзя интерпретировать как устойчивый.

### `expectancy`

Средний net PnL одной сделки в USDT.

### `average_win`, `average_loss`

Средняя прибыль и абсолютный средний убыток.

### `max_drawdown_pct`

Максимальная просадка equity от предыдущего high-water peak.

### `sharpe_proxy`, `sortino_proxy`

Прокси по event-to-event equity returns с множителем `sqrt(number_of_returns)`. Это не стандартный годовой Sharpe и не должен сравниваться напрямую с дневными отчётами других систем.

### `signals`

Число сформированных решений.

### `orders`

Число созданных виртуальных заявок.

### `fills`

Число fill events.

### `rejected_signals`

Число случаев, когда risk/equity state не разрешил новую заявку. FLAT также попадает в reject counter текущего backtest loop.

### `fill_rate_pct`

```text
fills / max(orders, 1) × 100
```

## 15. Дополнительные результаты

Отчёт содержит:

- equity curve;
- последние 500 сделок;
- количество событий по regime;
- причины отклонений;
- примечания;
- source;
- processed steps;
- elapsed seconds.

Файл:

```text
var/reports/latest_backtest.json
```

Каждый новый прогон перезаписывает этот файл. Для сравнения копируйте отчёты под отдельными именами.

## 16. Минимальный стресс-тест

Сделайте несколько одинаковых прогонов, меняя только один блок.

### Сценарий A — базовый

Текущие комиссии, latency и slippage.

### Сценарий B — расходы выше

```text
maker fee × 1.5
taker fee × 1.5
slippage × 2
```

### Сценарий C — сеть хуже

```text
latency + 50–150 ms
cancel timeout без изменения или меньше
```

### Сценарий D — очередь хуже

```text
queue_factor: 0.65 → 0.85 или 1.0
```

### Сценарий E — более строгий edge

Увеличить `min_net_edge_bps`.

Если прибыль исчезает при небольшом ухудшении, стратегия хрупкая.

## 17. Как сравнивать прогоны

Зафиксируйте:

- commit;
- source;
- список файлов;
- symbol;
- steps;
- active checkpoint hash;
- полный config;
- random seed;
- дату запуска;
- metrics;
- notes.

Текущая версия не формирует такой manifest автоматически. Сохраняйте копию `config.json`, checkpoint sidecar и report.

## 18. Типичные ошибки интерпретации

- оценивать synthetic PnL как реальный;
- считать высокий win rate достаточным;
- не учитывать число сделок;
- подбирать параметры по test-периоду;
- сравнивать разные steps;
- игнорировать fill rate;
- считать proxy Sharpe стандартным годовым;
- использовать один рыночный режим;
- не учитывать перезапись router memory;
- не проверять комиссию конкретного аккаунта.

## 19. Ограничения 0.1.1

- L2, а не MBO;
- queue factor вместо реальной очереди;
- атомарный resting fill;
- отсутствие cancel/replace стратегии;
- нет funding и liquidation price;
- нет mark price;
- нет maintenance margin;
- нет биржевых фильтров lot/tick/min notional;
- нет сетевых ошибок order API;
- нет rejected exchange orders;
- один symbol;
- нет portfolio-level risk;
- нет walk-forward runner;
- нет Monte Carlo и bootstrap;
- нет attribution по стратегии/feature;
- нет отдельного test dataset orchestration.
