# Шаблон программного слота CryptoHunter

Это reference-шаблон, а не автоматически смонтированный production-модуль.

Перед включением обязательны:

- уникальный `var_dir` на пользователя и программу;
- уникальный порт или unix socket;
- process lease/fencing;
- authenticated proxy вместо прямого порта;
- запрет пользовательского доступа к чужим данным;
- mock/paper executor;
- smoke/replay/fault/security тесты.

`MANIFEST["ready"]` оставлен `False` намеренно.
