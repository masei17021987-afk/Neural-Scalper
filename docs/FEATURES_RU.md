# 36 признаков микроструктуры

## 1. Общая схема

На каждом валидном snapshot `MicrostructureFeatureEngine` создаёт:

- вектор из 36 признаков;
- LOB-матрицу одного события `[levels, 4]`;
- последовательность LOB `[sequence_length, levels, 4]`;
- классификацию режима рынка;
- metadata.

LOB-каналы каждого уровня:

```text
0: относительная цена bid в б.п. от mid
1: log(1 + bid quantity)
2: относительная цена ask в б.п. от mid
3: log(1 + ask quantity)
```

Если история короче `sequence_length`, первая доступная строка повторяется слева. Полная готовность признака обозначается `engine.ready`.

## 2. Цена и спред

### 1. `mid_price`

```text
(best_bid + best_ask) / 2
```

Центр лучшего bid/ask. Используется как базовая цена нормализации.

### 2. `spread_bps`

```text
(best_ask - best_bid) / mid × 10 000
```

Чем выше, тем дороже немедленное исполнение и тем слабее качество скальпингового входа.

### 3. `microprice_delta_bps`

Microprice учитывает объёмы на лучшем уровне:

```text
microprice = (best_ask × bid_qty + best_bid × ask_qty)
             / (bid_qty + ask_qty)

delta = (microprice / mid - 1) × 10 000
```

Положительное значение означает давление вверх, отрицательное — вниз. Это локальный индикатор, а не гарантированный прогноз.

## 3. Дисбаланс стакана

Для N уровней:

```text
OBI_N = (sum_bid_qty - sum_ask_qty)
        / (sum_bid_qty + sum_ask_qty)
```

Диапазон приблизительно `[-1, 1]`.

### 4. `obi_1`

Дисбаланс только лучшего уровня. Быстрый, но шумный.

### 5. `obi_5`

Дисбаланс пяти уровней. Чуть устойчивее к перестановке на top-of-book.

### 6. `obi_10`

Основной средний LOB imbalance, используемый baseline и классификатором режима.

### 7. `obi_20`

Более широкий контекст глубины. Может медленнее реагировать на резкие изменения.

## 4. Глубина

### 8. `bid_depth_5`

Сумма quantity первых пяти bid.

### 9. `ask_depth_5`

Сумма quantity первых пяти ask.

### 10. `bid_depth_20`

Сумма quantity первых 20 bid либо доступной глубины.

### 11. `ask_depth_20`

Сумма quantity первых 20 ask.

Абсолютная глубина зависит от инструмента и масштаба quantity. Для универсальной мультисимвольной модели потребуется дополнительная нормализация.

### 12. `top_size_ratio`

```text
log((best_bid_qty + ε) / (best_ask_qty + ε))
```

Положительное значение — больше top bid, отрицательное — больше top ask.

## 5. Разрывы и форма книги

### 13. `bid_gap_bps`

Расстояние между первым и вторым bid в б.п.

Большой gap может означать слабую поддержку непосредственно под лучшей ценой.

### 14. `ask_gap_bps`

Расстояние между первым и вторым ask.

### 15. `depth_slope_bid`

```text
sum((index + 1) × bid_qty[index]) / sum(bid_qty)
```

Показывает, насколько bid-объём удалён от лучшей цены. Меньшее значение означает концентрацию ближе к top.

### 16. `depth_slope_ask`

Аналогично для ask.

Это не геометрический slope по цене; название отражает взвешенное положение объёма по номеру уровня.

## 6. Краткосрочные движения

Все return выражены в базисных пунктах mid-price.

### 17. `return_1_bps`

Изменение за одно snapshot-событие.

### 18. `return_3_bps`

Изменение за три события.

### 19. `return_10_bps`

Изменение за 10 событий. Используется многими стратегиями и режимами.

### 20. `return_30_bps`

Средний короткий контекст.

### 21. `return_60_bps`

Более длинный локальный контекст.

Важно: это event-time окна. При изменении event rate фактическая длительность окна меняется.

## 7. Волатильность

Сначала рассчитываются логарифмические доходности в б.п., затем population standard deviation.

### 22. `realized_vol_10_bps`

Волатильность последних примерно 10 переходов.

### 23. `realized_vol_30_bps`

Используется в классификации HIGH_VOL, momentum quality и mean-reversion pressure.

Это event-based volatility, а не годовая волатильность.

## 8. Агрессивный поток сделок

Сделка получает знак:

```text
aggressive buy  → +quantity
aggressive sell → -quantity
```

Trade imbalance:

```text
sum(signed_quantity) / sum(abs(quantity))
```

### 24. `trade_imbalance_5`

Очень короткий поток.

### 25. `trade_imbalance_20`

Основной поток, используемый baseline.

### 26. `trade_imbalance_50`

Более устойчивый контекст.

Если сделок ещё нет, признаки равны нулю.

## 9. Интенсивность и ускорение объёма

### 27. `trade_intensity_20`

Средний notional последних 20 сделок, преобразованный:

```text
log(1 + mean(notional_20))
```

### 28. `volume_acceleration`

```text
(mean_notional_last20 - mean_notional_previous20)
/ max(mean_notional_previous20, 1)
```

Ограничивается диапазоном `[-5, 5]`.

Положительное значение — активность ускоряется.

## 10. Реакция цены

### 29. `price_impact_bps`

Упрощённая оценка движения на единицу недавнего notional:

```text
return_3_bps / max(1, sum(last 3 notionals)) × 100 000
```

Ограничивается `[-50, 50]`.

Высокий абсолютный impact при небольшом объёме может указывать на тонкую ликвидность.

## 11. Качество канала

### 30. `latency_ms`

```text
max(0, local_ts_ms - exchange_ts_ms)
```

Это индикатор возраста события, но не полноценное измерение round-trip latency.

## 12. Ликвидации

За последние 10 секунд суммируется notional и нормируется на общий объём либо 1.

### 31. `liquidation_buy_pressure`

Доля BUY liquidation events.

### 32. `liquidation_sell_pressure`

Доля SELL liquidation events.

Значение направления force order следует интерпретировать вместе со спецификой биржевого события и реакцией рынка.

## 13. Производные оценки

### 33. `liquidity_score`

```text
clamp(
  tanh((bid_depth_20 + ask_depth_20) / 50)
  × exp(-spread_bps / 6),
  0, 1
)
```

Растёт при большой глубине и узком spread.

### 34. `momentum_quality`

```text
tanh(
  return_10_bps × (0.45 + abs(trade_imbalance_20))
  / max(1, realized_vol_30_bps × 3)
)
```

Высокое абсолютное значение означает направленное движение относительно локального шума.

### 35. `mean_reversion_pressure`

Если `abs(return_30_bps) < 8`:

```text
-tanh(return_10_bps / max(2, realized_vol_30_bps × 4))
```

В сильном 30-event движении признак обнуляется, чтобы не бороться с выраженным трендом.

### 36. `event_rate_hz`

```text
(number_of_snapshots - 1) / elapsed_seconds
```

Показывает фактическую интенсивность snapshot-потока внутри окна истории.

## 14. Рыночные режимы

### `LOW_LIQUIDITY`

```text
spread > 5 б.п. или bid_depth_20 + ask_depth_20 < 2
```

Новые входы блокируются роутером.

### `HIGH_VOL`

```text
realized_vol_30_bps > 3
```

Размер позиции уменьшается.

### `BREAKOUT_UP/DOWN`

```text
abs(return_10_bps) > 6 и vol > 1.1
```

### `TREND_UP/DOWN`

```text
abs(return_30_bps) > 7 и abs(obi_10) > 0.12
```

### `RANGE`

Все остальные состояния.

Порядок условий важен: LOW_LIQUIDITY и HIGH_VOL проверяются раньше breakout/trend.

## 15. Что нейросеть получает напрямую

`RiskAwareLOBNet` получает только LOB tensor `[T, L, 4]`.

Вектор 36 признаков используется:

- heuristic baseline;
- стратегиями-помощниками;
- классификатором режима;
- расчётом gross/net edge;
- risk/quality отображением.

Текущая нейросеть не получает 36-feature vector отдельной ветвью. Это важная точка для будущего расширения.

## 16. Нормализация и ограничения

Плюсы текущего LOB tensor:

- цена нормирована относительно mid;
- quantity логарифмирована;
- форма одинакова для разных ценовых уровней.

Ограничения:

- quantity не нормирована по типичной ликвидности конкретного символа;
- нет tick-size embedding;
- нет времени между событиями как входа модели;
- нет open interest/funding/basis;
- нет cancel/add decomposition;
- нет cross-symbol context;
- нет feature normalization, рассчитанной только на train.

Перед построением общей модели на многих инструментах эти ограничения нужно устранить.
