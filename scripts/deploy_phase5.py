#!/usr/bin/env python3
"""
scripts/deploy_phase5.py
Деплой Фазы 5: загружает bot.py + topic_router.py на VPS,
обновляет .env с новыми TOPIC_*_ID и перезапускает бота.

Использование:
    python3 scripts/deploy_phase5.py
"""
import os
import re
import paramiko

HOST     = "178.105.1.60"
USER     = "root"
KEY_FILE = "/home/julija/.ssh/vps_jade_developer"
VPS_DIR  = "/home/bridge/vibe-telegram-bot"

LOCAL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRED_PATH  = os.path.join(LOCAL_ROOT, "credentials.env")

# Файлы, которые нужно загрузить на VPS
FILES_TO_UPLOAD = [
    "bot.py",
    "topic_router.py",
    "tests/test_phase_5_topics.py",
]

# Переменные из credentials.env, которые идут в удалённый .env
ENV_KEYS = [
    "BOT_TOKEN",          # → TELEGRAM_TOKEN
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    # Фаза 5: топики
    "SUPERGROUP_ID",
    "TOPIC_TEXTS_ID",
    "TOPIC_TABLES_ID",
    "TOPIC_IMAGES_ID",
    "TOPIC_ARCHIVES_ID",
    "TOPIC_ATTENTION_ID",
]


def load_credentials() -> dict:
    """Читает credentials.env, возвращает словарь ключ→значение."""
    env_vars = {}
    if not os.path.exists(CRED_PATH):
        raise FileNotFoundError(f"Файл не найден: {CRED_PATH}")
    with open(CRED_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip()
    return env_vars


def build_remote_env(creds: dict) -> str:
    """Строит содержимое удалённого .env."""
    lines = []
    # BOT_TOKEN → TELEGRAM_TOKEN (бот читает TELEGRAM_TOKEN)
    bot_token = creds.get("BOT_TOKEN", "")
    if bot_token:
        lines.append(f"TELEGRAM_TOKEN={bot_token}")

    for key in ENV_KEYS[1:]:  # остальные ключи — напрямую
        val = creds.get(key, "")
        if val:
            lines.append(f"{key}={val}")

    return "\n".join(lines) + "\n"


def mask_secrets(text: str, creds: dict) -> str:
    """Маскирует чувствительные данные в тексте (токены, ключи)."""
    # Маскируем Telegram bot-токены
    text = re.sub(r"bot[0-9]{8,}:[a-zA-Z0-9_-]{30,}", "bot[REDACTED]", text)
    # Маскируем OpenRouter ключи
    text = re.sub(r"sk-or-v1-[a-f0-9]+", "sk-or-v1-[REDACTED]", text)
    # Маскируем Groq ключи
    text = re.sub(r"gsk_[a-zA-Z0-9]+", "gsk_[REDACTED]", text)
    return text


def run_cmd(client: paramiko.SSHClient, cmd: str) -> tuple[str, str]:
    """Выполняет команду и возвращает (stdout, stderr)."""
    _, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    return out, err


def main():
    print("=" * 60)
    print("🚀 Деплой Фазы 5: маршрутизация по топикам Jade_Developer")
    print("=" * 60)

    # 1. Загружаем credentials
    try:
        creds = load_credentials()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return

    bot_token = creds.get("BOT_TOKEN")
    if not bot_token:
        print("❌ BOT_TOKEN не найден в credentials.env")
        return

    topic_ids = {k: creds.get(k) for k in [
        "SUPERGROUP_ID", "TOPIC_TEXTS_ID", "TOPIC_TABLES_ID",
        "TOPIC_IMAGES_ID", "TOPIC_ARCHIVES_ID", "TOPIC_ATTENTION_ID"
    ]}
    missing = [k for k, v in topic_ids.items() if not v]
    if missing:
        print(f"⚠️  Предупреждение: не заданы в credentials.env: {', '.join(missing)}")

    # 2. Подключаемся
    print(f"\n🔌 Подключаюсь к {HOST} по SSH-ключу...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(HOST, username=USER, key_filename=KEY_FILE, timeout=15)
        print("✅ Подключено!")

        sftp = client.open_sftp()

        # 3. Загружаем файлы
        print(f"\n📦 Загрузка файлов в {VPS_DIR}/...")
        for fname in FILES_TO_UPLOAD:
            local_path = os.path.join(LOCAL_ROOT, fname)
            remote_path = f"{VPS_DIR}/{fname}"
            if not os.path.exists(local_path):
                print(f"  ⚠️  Локальный файл не найден: {local_path} — пропускаю")
                continue
            sftp.put(local_path, remote_path)
            size_kb = os.path.getsize(local_path) / 1024
            print(f"  ✅ {fname} ({size_kb:.1f} KB)")

        # 4. Обновляем .env на VPS
        print(f"\n📝 Обновление .env на VPS...")
        remote_env = build_remote_env(creds)
        with sftp.file(f"{VPS_DIR}/.env", "w") as f:
            f.write(remote_env)

        # Считаем переменные (без секретных значений)
        env_count = len([l for l in remote_env.strip().split("\n") if "=" in l])
        print(f"  ✅ .env записан ({env_count} переменных)")
        print(f"  📋 Топики: SUPERGROUP={topic_ids.get('SUPERGROUP_ID', 'не задан')}")
        for k in ["TOPIC_TEXTS_ID", "TOPIC_TABLES_ID", "TOPIC_IMAGES_ID",
                  "TOPIC_ARCHIVES_ID", "TOPIC_ATTENTION_ID"]:
            v = topic_ids.get(k, "—")
            label = k.replace("TOPIC_", "").replace("_ID", "")
            print(f"    {label}: {v}")

        sftp.close()

        # 5. Перезапускаем бота
        print("\n🔄 Перезапуск vibe-bot...")
        out, err = run_cmd(client, "systemctl restart vibe-bot")
        if err.strip():
            print(f"  ⚠️  stderr: {err.strip()}")

        # 6. Проверяем статус
        print("\n📊 Статус vibe-bot:")
        out, _ = run_cmd(client, "systemctl status vibe-bot --no-pager -l")
        out = mask_secrets(out, creds)
        # Выводим только ключевые строки
        for line in out.split("\n"):
            if any(kw in line for kw in ["Active:", "Main PID", "vibe-bot", "Started", "Error", "error"]):
                print(f"  {line.strip()}")

        # 7. Последние логи
        print("\n📜 Последние 5 строк логов:")
        out, _ = run_cmd(client, "journalctl -u vibe-bot -n 5 --no-pager")
        out = mask_secrets(out, creds)
        for line in out.strip().split("\n"):
            print(f"  {line}")

        print("\n✅ Деплой Фазы 5 завершён!")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
    finally:
        client.close()
        print("🔌 Соединение закрыто.")


if __name__ == "__main__":
    main()
