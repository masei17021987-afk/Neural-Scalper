# Интеграция с CryptoHunter

Сборка уже следует границам вашего `cryptohunter`:

- отдельный program identity;
- config schema;
- runtime status;
- общий market/execution/risk принцип;
- fail-closed execution;
- отдельные данные, логи и модели;
- AI-программа не объявляется готовой к live.

В `integration/cryptohunter_program/` находится шаблон слота `neural_scalper`.

## Рекомендуемый способ

На первом этапе держите Neural Scalper отдельным локальным приложением. После стабильного paper-прогона:

1. добавьте manifest в `programs/neural_scalper/`;
2. перенесите schema и UI schema;
3. подключите runtime как отдельный actor/process;
4. выдайте ему только общий public market snapshot bus;
5. оставьте exchange executor в mock/paper режиме;
6. включите пользователя только после тестов из `docs/TESTING_AND_SAFETY_RU.md`.

## Почему не включён прямой live-мост

Ваш CryptoHunter является многопользовательской системой с tenant isolation. Локальная версия Neural Scalper — single-user. Прямое включение без отдельного namespace данных, process lease, fencing и per-user key isolation нарушило бы уже принятые границы безопасности.

Шаблон намеренно помечает:

```text
ready = false
live_execution = false
paper_ready = true
```
