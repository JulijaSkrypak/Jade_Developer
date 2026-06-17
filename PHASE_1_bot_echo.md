# Фаза 1: Бот живёт — и просто отвечает

**Цель:** Создать простой Telegram-бот, который запущен на Hetzner VPS как systemd (фоновый процесс) и стабильно отвечает на сообщения.

**Никаких усложнений:** только Telegram, только echo (повтор), только VPS. Никакого Claude, никаких агентов.

---

## Условия входа

- [ ] Hetzner VPS с Ubuntu 24.04 — чистый (rebuild сделан)
- [ ] SSH доступ работает: `ssh root@178.105.1.60`
- [ ] Телефон с Telegram установлен
- [ ] Токен бота от @BotFather уже есть

---

## Шаг 1: Создать бота в Telegram

1. Открой Telegram на телефоне
2. Найди **@BotFather**
3. Отправь `/newbot`
4. BotFather попросит имя бота (например, `VibeCoderBot`)
5. BotFather попросит username (например, `vibecoder_julia_bot`)
6. **Скопируй токен** — выглядит как `123456:ABCdefGHIjklMNOpqrSTuvWXYZ`

Сохрани токен, он понадобится на шаге 4.

---

## Шаг 2: Подготовить окружение на VPS

Подключись по SSH на MSI компьютере:

```bash
ssh root@178.105.1.60
```

Установить зависимости и создать папку проекта:

```bash
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv git curl wget
mkdir -p /home/bridge/vibe-telegram-bot
cd /home/bridge/vibe-telegram-bot
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install python-telegram-bot==20.3
```

---

## Шаг 3: Создать bot.py на VPS

Находясь в `/home/bridge/vibe-telegram-bot`:

```bash
cat > bot.py << 'EOFPYTHON'
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Привет! Я твой бот. Напиши что-нибудь.")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text
    await update.message.reply_text(f"Ты сказал: {user_text}")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Pong! ✓")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
EOFPYTHON
```

---

## Шаг 4: Создать .env файл с токеном

Замени `YOUR_TOKEN_HERE` на реальный токен от BotFather:

```bash
cat > .env << 'EOFENV'
TELEGRAM_TOKEN=YOUR_TOKEN_HERE
EOFENV
```

---

## Шаг 5: Создать systemd сервис

Systemd (менеджер служб Linux) запустит бота в фоне и автоматически перезапустит при падении:

```bash
cat > /etc/systemd/system/vibe-bot.service << 'EOFSVC'
[Unit]
Description=Vibe Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/bridge/vibe-telegram-bot
EnvironmentFile=/home/bridge/vibe-telegram-bot/.env
ExecStart=/home/bridge/vibe-telegram-bot/venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOFSVC
```

---

## Шаг 6: Запустить бота

```bash
systemctl daemon-reload
systemctl enable vibe-bot
systemctl start vibe-bot
systemctl status vibe-bot
```

Должно быть `Active: active (running)` зелёным цветом.

---

## Шаг 7: Проверка работы

С телефона в Telegram:

1. Найди своего бота по username
2. Отправь `/start`
3. Отправь `/ping` → должно прийти `Pong! ✓`
4. Напиши `Привет` → должно прийти `Ты сказал: Привет`

---

## Логирование и отладка

Смотреть логи в реальном времени (на VPS по SSH):

```bash
journalctl -u vibe-bot -f
```

Посмотреть последние 50 строк:

```bash
journalctl -u vibe-bot -n 50
```

Перезапустить бота:

```bash
systemctl restart vibe-bot
```

Остановить бота:

```bash
systemctl stop vibe-bot
```

Проверить статус:

```bash
systemctl status vibe-bot
```

### Типичные ошибки:

**`Token is invalid`** → проверь .env файл:
```bash
cat /home/bridge/vibe-telegram-bot/.env
```

**`ModuleNotFoundError`** → venv не активирован в systemd. Проверь путь в ExecStart:
```bash
ls /home/bridge/vibe-telegram-bot/venv/bin/python
```

**`Bot не отвечает`** → проверь логи:
```bash
journalctl -u vibe-bot -n 20
```

---

## Gate: Переход к фазе 2

✅ **Можно переходить к следующей фазе**, когда:

- [ ] `systemctl status vibe-bot` показывает `active (running)`
- [ ] Бот отвечает на `/ping` стабильно
- [ ] Бот отвечает на обычные сообщения (echo работает)
- [ ] Бот работает с телефона
- [ ] После `systemctl restart vibe-bot` бот снова отвечает

**Если что-то не работает:**
- Смотри `journalctl -u vibe-bot -n 50`
- Проверь что токен в `.env` правильный
- Проверь что путь к python правильный: `ls /home/bridge/vibe-telegram-bot/venv/bin/python`

---

## Типичные вопросы

**Q: Как изменить код бота?**
A: Отредактируй `bot.py` на VPS, потом `systemctl restart vibe-bot`

**Q: Бот упал сам по себе, что делать?**
A: Systemd перезапустит его автоматически через 10 секунд. Посмотри причину: `journalctl -u vibe-bot -n 30`

**Q: Как добавить переменные окружения?**
A: Добавь строку в `.env` файл, потом `systemctl restart vibe-bot`

---

## Резюме фазы 1

- ✅ Бот создан и работает на Hetzner VPS
- ✅ Запущен как systemd сервис (автозапуск, автоперезапуск)
- ✅ Логи доступны через journalctl
- ✅ Отвечает стабильно
- ➡️ Переходим к **Фаза 2: Бот спрашивает LLM через OpenRouter**
