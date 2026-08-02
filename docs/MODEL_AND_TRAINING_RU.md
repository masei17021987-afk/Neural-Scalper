# Нейросеть и обучение

## 1. Две модели поведения

Программа всегда может сформировать прогноз.

### Heuristic baseline

Используется, когда checkpoint отсутствует или не может быть загружен. Он объединяет:

- microprice delta;
- OBI 10;
- trade imbalance 20;
- return 10;
- momentum quality.

Baseline нужен для демонстрации интерфейса и проверки pipeline. Он не считается обученной нейросетью.

### RiskAwareLOBNet

После успешного обучения или загрузки checkpoint используется PyTorch-модель.

## 2. Вход нейросети

Форма:

```text
[batch, time, levels, 4]
```

Каналы:

```text
relative bid price, log bid size, relative ask price, log ask size
```

Значения цены выражены в базисных пунктах относительно mid. Quantity преобразована через `log1p`.

Типичные значения по умолчанию:

```text
time   = 64
levels = 20
channels = 4
```

Один пример содержит `64 × 20 × 4 = 5 120` чисел.

## 3. Архитектура

```text
LOB tensor
  ↓ permute to [B, 4, T, L]
Conv2D kernel (5,3)
  ↓
BatchNorm + SiLU
  ↓
2 × ResidualConvBlock
  ↓
mean pooling по levels
  ↓ [B,T,C]
2-layer GRU
  ↓
attention по времени
  ↓
shared LayerNorm + Linear + SiLU + Dropout
  ├── direction head: 3 logits
  ├── edge head: signed bps в диапазоне примерно [-60,60]
  └── volatility head: non-negative bps
```

### Direction head

Классы расположены строго в порядке:

```text
0 SHORT
1 FLAT
2 LONG
```

### Edge head

```text
tanh(linear) × 60
```

Знак описывает направление ожидаемого исполнимого движения.

### Volatility head

```text
softplus(linear) × 10
```

Выход неотрицателен.

## 4. Формирование датасета

### Synthetic

`SyntheticMarket` генерирует snapshot, затем `MicrostructureFeatureEngine` накапливает LOB sequence.

Для прогрева добавляются:

```text
sequence_length + horizon + 20
```

событий сверх желаемого числа примеров.

### Recorded

Читаются `book_*.jsonl.gz` и `book_*.jsonl` из `var/data/records`. Повреждённые строки пропускаются. Используются только записи текущего symbol.

## 5. Метки, основанные на исполнимых ценах

Текущий горизонт:

```text
horizon = 12 snapshot-событий
```

LONG:

```text
вход = current ask
выход = future bid
long_net_bps = (future_bid / current_ask - 1) × 10 000 - round_trip_cost
```

SHORT:

```text
вход = current bid
выход = future ask
short_net_bps = (current_bid / future_ask - 1) × 10 000 - round_trip_cost
```

Round-trip cost при построении меток:

```text
maker_fee_bps + taker_fee_bps + slippage_bps
```

Класс:

```text
LONG  если long_net > threshold и long_net >= short_net
SHORT если short_net > threshold
FLAT  иначе
```

Порог:

```text
max(0.5, min_net_edge_bps)
```

Это консервативнее, чем метка по будущему mid, но всё ещё не моделирует фактическую вероятность лимитного fill.

## 6. Auxiliary targets

### Edge target

Для LONG хранится положительный long net edge.

Для SHORT в массив edge записывается отрицательный short edge.

Для FLAT сохраняется более сильная из двух слабых signed-величин. Это позволяет auxiliary head учить форму движения даже при нейтральном классе.

### Volatility target

Внутри текущего горизонта рассчитывается standard deviation логарифмических mid-return в б.п.

## 7. Хронологическое разделение

Данные не перемешиваются перед split:

```text
первые 70%  → train
следующие 15% → validation
последние 15% → test
```

Внутри train DataLoader использует shuffle. Validation и test не перемешиваются.

Ограничение версии 0.1.1: нет purge/embargo между соседними разделами, поэтому перекрывающиеся последовательности около границы могут быть коррелированы. Для исследовательского релиза 0.2 это необходимо исправить.

## 8. Функция потерь

```text
loss = cross_entropy(direction)
     + 0.20 × smooth_l1(edge)
     + 0.08 × smooth_l1(volatility)
```

Direction остаётся основной задачей. Edge и volatility формируют risk-aware embedding.

## 9. Оптимизация

- optimizer: AdamW;
- weight decay: `1e-4`;
- learning rate по умолчанию: `0.0008`;
- gradient clipping: `2.0`;
- batch size: `128`;
- epochs: `8`;
- mixed precision: FP16 только при CUDA и включённом параметре;
- checkpoint выбирается по минимальному validation loss.

## 10. Оценка

На validation и test рассчитываются:

- total loss;
- accuracy;
- macro F1.

Macro F1 важнее обычной accuracy при дисбалансе классов, но ни одна из этих метрик не заменяет торговый бэктест.

Модель с высокой accuracy может быть убыточной, если:

- неверно предсказывает редкие сильные движения;
- edge меньше расходов;
- fill невозможен;
- сигнал появляется слишком поздно;
- тест содержит утечку;
- рыночный режим изменился.

## 11. Сохранение модели

Создаются два набора файлов.

### Версионный checkpoint

```text
var/models/lob_scalper_<unix_timestamp>.pt
var/models/lob_scalper_<unix_timestamp>.json
```

### Активный checkpoint

```text
var/models/best_model.pt
var/models/best_model.json
```

`.pt` содержит:

- `model_state`;
- `metadata`;
- `metrics`.

JSON sidecar позволяет посмотреть metadata без загрузки PyTorch.

## 12. Metadata

Сохраняются:

- источник;
- samples;
- horizon ticks;
- seed или число файлов;
- тип метки;
- hidden size;
- dropout;
- sequence length;
- levels;
- classes;
- Unix-время обучения.

Перед загрузкой модель восстанавливает hidden size и dropout из metadata.

## 13. Автоматическая загрузка

При старте `ModelManager`:

1. загружает путь из `config.model.checkpoint`, если он задан;
2. иначе ищет `var/models/best_model.pt`;
3. при отсутствии использует baseline.

После нового обучения runtime пытается сразу загрузить `best_model.pt`.

## 14. Использование GPU

Устройство выбирается:

```text
cuda, если use_gpu=true и torch.cuda.is_available()
иначе cpu
```

Mixed precision включается только на CUDA.

Для RTX 3090 полезно:

- начать с batch 128;
- увеличить batch после наблюдения за VRAM;
- не менять одновременно batch и learning rate без отдельного эксперимента;
- следить за температурой и стабильностью питания;
- хранить dataset на SSD.

## 15. Как правильно проводить эксперимент

1. Зафиксировать commit и конфигурацию.
2. Зафиксировать список файлов и период данных.
3. Не изменять test при подборе параметров.
4. Обучить baseline-модель.
5. Сохранить class distribution.
6. Сравнить validation и test.
7. Выполнить recorded backtest.
8. Увеличить расходы в стресс-тесте.
9. Проверить новый временной период.
10. Сравнить с простым heuristic baseline.

## 16. Рекомендуемые дополнительные метрики

Текущая версия их не считает, но для развития нужны:

- confusion matrix;
- precision/recall каждого класса;
- balanced accuracy;
- Matthews correlation coefficient;
- Brier score;
- calibration curve;
- edge MAE по направлениям;
- volatility MAE;
- PnL by confidence bucket;
- PnL by predicted edge bucket;
- PnL by regime;
- turnover;
- adverse selection после fill.

## 17. Типичные признаки переобучения

- train loss падает, validation растёт;
- test значительно хуже validation;
- результат держится на нескольких сделках;
- небольшое изменение комиссии уничтожает PnL;
- модель работает только на одном дне;
- один symbol доминирует в общей метрике;
- high confidence не соответствует лучшему net result;
- повторное обучение с другим seed сильно меняет итог.

## 18. Ограничения обучения 0.1.1

- фиксированный горизонт 12 событий;
- нет multi-horizon targets;
- нет class weighting;
- нет early stopping patience;
- нет scheduler learning rate;
- нет reproducibility seed для PyTorch training loop;
- нет DataLoader workers/pinned memory;
- нет normalization statistics;
- нет purge/embargo;
- нет walk-forward orchestration;
- нет dataset manifest/hash;
- нет experiment registry;
- checkpoint `best_model.pt` перезаписывается каждым успешным обучением;
- модель не использует 36-feature vector напрямую;
- нет исполнения-aware fill probability target.

Эти ограничения не скрываются и должны учитываться при интерпретации результата.
