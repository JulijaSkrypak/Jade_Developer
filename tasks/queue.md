## TASK-001
Статус: DONE (перенесено в tasks/done.md 2026-06-12)
Описание: Выполнить все шаги из PHASE_1_bot_echo.md на VPS 178.105.1.60 для развертывания echo Telegram-бота.
Шаги для выполнения на VPS:
1. Подключиться к VPS по SSH: `ssh root@178.105.1.60` (пароли см. в разделе Контекст)
2. Установить зависимости: `apt update && apt upgrade -y` и `apt install -y python3 python3-pip python3-venv git curl wget`
3. Создать папку проекта: `/home/bridge/vibe-telegram-bot`
4. Создать python-окружение venv и установить библиотеку `python-telegram-bot==20.3`
5. Создать файл `/home/bridge/vibe-telegram-bot/.env` с переменной `TELEGRAM_TOKEN` (значение указано в Контексте)
6. Создать файл `bot.py` с обработчиками для команд `/start`, `/ping` и функцией `echo` (код приведен в PHASE_1_bot_echo.md)
7. Создать systemd-сервис `vibe-bot.service` в `/etc/systemd/system/vibe-bot.service`
8. Запустить и добавить сервис в автозагрузку: `systemctl daemon-reload && systemctl enable --now vibe-bot`
9. Проверить статус службы и убедиться, что бот работает корректно.

Контекст:
- VPS: чистая Ubuntu 24.04 (rebuild сделан).
- IP: `178.105.1.60`
- Учетные данные для SSH:
  - Пользователь: `root`
  - Пароль (строка 1 из credentials.env): `htTgTgtWrqdP`
  - Пароль/доп. строка (строка 2 из credentials.env): `hhaGT8Gkb-nv.bksjgbw!ks.l`
- Значение `TELEGRAM_TOKEN` для записи в файл `/home/bridge/vibe-telegram-bot/.env` на VPS: `8880056885:AAFa5Gzzs7fGuqbADQ-fLiek1iDdNkEMBvc` (взято из переменной `BOT_TOKEN` локального `credentials.env`).
- Полное руководство и код для `bot.py` находятся в локальном файле [PHASE_1_bot_echo.md](file:///home/julija/Документы/Antigravity/Jade_Developer/PHASE_1_bot_echo.md).
- Успешный запуск проверяется прохождением Gate:
  - `systemctl status vibe-bot` возвращает `active (running)`.
  - Бот отвечает на `/start` -> `Привет! Я твой бот. Напиши что-нибудь.`.
  - Бот отвечает на `/ping` -> `Pong! ✓`.
  - Бот делает эхо на обычные сообщения: `Ты сказал: [текст]`.
  - Бот стабильно возобновляет работу после `systemctl restart vibe-bot`.
- После завершения выполнения перенесите эту задачу со статусом `DONE` или `ERROR` в локальный файл `tasks/done.md`.

## TASK-004
Статус: IN_PROGRESS
Описание: Подключиться к VPS (178.105.1.60, пользователь bridge) по SSH через paramiko, выполнить аудит названий моделей в проекте vibe-telegram-bot и вывести результаты в таблице.
Шаги:
1. Создать локальный python-скрипт в `scratch` для выполнения удаленных команд SSH через `paramiko`.
2. Подключиться под пользователем `bridge` (или войти под `root` и переключиться, если у `bridge` нет прямого доступа по паролю).
3. Найти все файлы `.py`, `.env`, `.md`, `.json`, `.yaml`, `.yml` в `/home/bridge/vibe-telegram-bot`, содержащие слово "model".
4. Выполнить grep-поиск для выявления конкретных упоминаний моделей (`gemini`, `gpt`, `claude`, `whisper`, `llama`, `mistral`, `groq`).
5. Сформировать markdown-таблицу с полями: Файл, Строка №, Текущая модель.
6. Вывести таблицу пользователю и ожидать дальнейших указаний по замене моделей.

