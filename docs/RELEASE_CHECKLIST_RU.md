# Чек-лист релиза

## 1. Версия

- [ ] обновлён `pyproject.toml`;
- [ ] обновлён `VERSION.txt`;
- [ ] обновлён `CHANGELOG.md`;
- [ ] model/data schema versions зафиксированы;
- [ ] build date корректна.

## 2. Код

- [ ] нет временных debug hacks;
- [ ] live execution по-прежнему заблокирован, если релиз paper-only;
- [ ] risk manager не обходится;
- [ ] ошибки обрабатываются fail-closed;
- [ ] публичные функции типизированы;
- [ ] нет секретов.

## 3. Тесты

```bash
python -m compileall -q src tests integration
python -m pytest -q
node --check src/neuroscalper/web/static/app.js
```

- [ ] все проверки зелёные;
- [ ] demo start/stop проверен;
- [ ] API health/status/config проверены;
- [ ] backtest synthetic проверен;
- [ ] training smoke проверен;
- [ ] state recovery проверено.

## 4. Данные

- [ ] runtime `var/` не попал в Git;
- [ ] нет записанного рынка в release zip;
- [ ] нет SQLite пользователя;
- [ ] нет checkpoint неизвестного происхождения;
- [ ] schema описана.

## 5. UI

- [ ] 1366×768 без критического overflow;
- [ ] 1920×1080;
- [ ] тёмная тема читаема;
- [ ] все кнопки имеют понятные подписи;
- [ ] опасные действия выделены;
- [ ] ошибки отображаются на русском;
- [ ] нет JavaScript console errors;
- [ ] hard refresh проверен.

## 6. Документация

- [ ] README соответствует коду;
- [ ] installation протестирован на чистом окружении;
- [ ] все ссылки docs работают;
- [ ] параметры и диапазоны совпадают с validator;
- [ ] API примеры валидны;
- [ ] ограничения перечислены;
- [ ] roadmap обновлён.

## 7. Безопасность

- [ ] bind host 127.0.0.1;
- [ ] `.env` исключён;
- [ ] Git secret scan чистый;
- [ ] зависимости проверены;
- [ ] checksum создан;
- [ ] архив повторно распакован и протестирован;
- [ ] публикация private, если содержит торговые наработки.

## 8. Git

- [ ] рабочее дерево чистое;
- [ ] commit message понятен;
- [ ] tag создан;
- [ ] CI прошёл;
- [ ] release notes добавлены;
- [ ] bundle/zip сохранены локально.

## 9. Финальная ручная проверка

1. Распаковать release zip в новую папку.
2. На Ubuntu выполнить `./INSTALL_UBUNTU.sh` и `./start.sh`; на Windows запустить `START.bat`.
3. Запустить demo.
4. Остановить demo.
5. Запустить тесты.
6. Проверить отсутствие личного `var/`.
7. Сравнить SHA-256.
