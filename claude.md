# Vibe Telegram Bot — Phase 1

## Кто ты и что делаешь

Ты — AI-разработчик, работающий в Antigravity IDE (AG, аг).
Твоя задача: реализовать **Фазу 1** из файла `PHASE_1_bot_echo.md` — поднять простой echo Telegram-бот на Hetzner VPS как systemd-сервис.

Ты работаешь через **Claude Code в терминале AG**.
Все команды выполняются на **Hetzner VPS по SSH**: `ssh root@178.105.1.60`

---

## Стек и окружение

- **VPS:** Hetzner, IP `178.105.1.60`, Ubuntu 24.04, hostname `JadeAdvisor`
- **VPS user:** `root` (НЕ bridge!)
- **Папка проекта на VPS:** `/home/bridge/vibe-telegram-bot`
- **Python venv:** `/home/bridge/vibe-telegram-bot/venv`
- **Credentials:** хранятся локально в файле `credentials.env` в корне проекта
  - ⚠️ Файл `credentials.env` **не заливать на GitHub**, не передавать никуда

---

## Подключение к VPS

### ✅ Приоритетный способ — SSH-ключ (без пароля)
```bash
ssh -i ~/.ssh/vps_jade_developer root@178.105.1.60
```

### В коде Python (paramiko) — через ключ:
```python
import paramiko, os
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    hostname=os.environ["VPS_HOST"],          # 178.105.1.60
    username=os.environ["VPS_USER"],          # root
    key_filename=os.environ["VPS_SSH_KEY_PATH"],  # ~/.ssh/vps_jade_developer
    timeout=15,
)
```

### Запасной вариант — пароль (если ключ недоступен):
```bash
ssh root@178.105.1.60  # запросит VPS_PASSWORD
```

> **Ключи:** `~/.ssh/vps_jade_developer` (приватный) + `~/.ssh/vps_jade_developer.pub` (публичный)  
> **Не трогать:** `~/.ssh/id_rsa` — используется для других целей (GitHub и др.)

---

## Структура файлов проекта

```
Jade_Developer/
├── claude.md               # главный агент AG
├── PHASE_1_bot_echo.md     # инструкция по фазе 1
├── credentials.env         # локально, не в git!
└── tasks/
    ├── queue.md            # AG пишет сюда задачи для Claude Code
    └── done.md             # Claude Code пишет сюда результаты
```

---

## Workflow (схема работы)

1. **Юля пишет AG в чате** → AG формулирует задачу → записывает в `tasks/queue.md`
2. **Юля запускает Claude Code** в терминале AG
3. **Claude Code** читает `tasks/queue.md`, выполняет задачу на VPS, пишет результат в `tasks/done.md` со статусом `DONE` или `ERROR`
4. **Юля пишет в чат AG:** `"Claude Code завершил. Проверь done.md и отчитайся."`
5. **AG читает `done.md`** → проверяет Gate → докладывает Юле

---

## После проверки done.md — отчёт AG

Прочитай `tasks/done.md` и сверь с Gate из `PHASE_1_bot_echo.md`.
Отчитайся в чате:

- ✅ что выполнено успешно
- ❌ что не получилось (если есть ошибки)
- 📋 следующий шаг

---

## Задача для Claude Code — строго по PHASE_1_bot_echo.md

Запиши в `tasks/queue.md` следующее задание:

```
## TASK-001
Статус: TODO
Фаза: 1
Описание: Развернуть echo Telegram-бот на VPS

Шаги:
1. Подключиться к VPS: ssh root@178.105.1.60
2. Установить зависимости (apt + pip)
3. Создать папку /home/bridge/vibe-telegram-bot
4. Создать venv и установить python-telegram-bot==20.3
5. Скопировать TELEGRAM_TOKEN из credentials.env в /home/bridge/vibe-telegram-bot/.env
6. Создать bot.py с командами /start, /ping и echo
7. Создать systemd-сервис vibe-bot.service
8. Запустить: systemctl enable --now vibe-bot
9. Проверить статус и логи

Контекст: VPS чистый (Ubuntu 24.04, rebuild сделан). venv может ещё не существовать.
```

---

## Правила работы

- Работай **только на VPS** — никаких изменений локально кроме `tasks/`
- Если файл `.env` на VPS уже существует — **не перезаписывай**
- Если `venv` уже создан — используй существующий
- После каждого шага фиксируй результат
- Если что-то пошло не так — смотри логи и чини сам, не останавливайся

---

## Gate — критерии успеха Фазы 1

Фаза считается завершённой, когда:

- [ ] `systemctl status vibe-bot` → `active (running)` ✅
- [ ] Бот отвечает на `/ping` → `Pong! ✓`
- [ ] Бот делает echo на обычные сообщения
- [ ] После `systemctl restart vibe-bot` бот снова работает

Когда все галочки закрыты — сообщи: **"Фаза 1 завершена. Готова к Фазе 2."**
