#!/usr/bin/env python3
"""
deploy_smart_router.py
Загружает новый bot.py с Smart Router на VPS, делает backup, перезапускает сервис.
"""

import paramiko
import time

HOST = "178.105.1.60"
USER = "root"
PASSWORD = "htTgTgtWrqdP"
BOT_DIR = "/home/bridge/vibe-telegram-bot"
LOCAL_NEW_BOT = "/home/julija/Документы/Antigravity/Jade_Developer/scripts/new_bot.py"


def run(client, cmd, description=""):
    print(f"\n{'─'*50}")
    if description:
        print(f"▶ {description}")
    print(f"$ {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out)
    if err:
        print(f"[stderr] {err}")
    return out


def main():
    print("🔌 Подключаюсь к VPS...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    print("✅ Подключено!")

    # 1. Backup
    run(client,
        f"cp {BOT_DIR}/bot.py {BOT_DIR}/bot.py.backup_before_smart_router",
        "Создаём backup текущего bot.py")

    # 2. Загружаем новый файл через SFTP
    print(f"\n{'─'*50}")
    print("▶ Загружаем новый bot.py на VPS...")
    sftp = client.open_sftp()
    sftp.put(LOCAL_NEW_BOT, f"{BOT_DIR}/bot.py")
    sftp.close()
    print("✅ Файл загружен!")

    # 3. Проверяем синтаксис Python
    run(client,
        f"cd {BOT_DIR} && source venv/bin/activate && python -m py_compile bot.py && echo 'Синтаксис OK'",
        "Проверяем синтаксис Python")

    # 4. Перезапускаем сервис
    run(client,
        "systemctl restart vibe-bot",
        "Перезапускаем vibe-bot")

    time.sleep(3)

    # 5. Статус сервиса
    run(client,
        "systemctl status vibe-bot --no-pager -l",
        "Статус сервиса vibe-bot")

    # 6. Последние логи
    run(client,
        "journalctl -u vibe-bot -n 30 --no-pager",
        "Последние 30 строк логов")

    # 7. Показываем финальный bot.py
    print(f"\n{'═'*50}")
    print("📄 ФИНАЛЬНЫЙ bot.py на сервере:")
    print(f"{'═'*50}")
    run(client, f"cat {BOT_DIR}/bot.py")

    client.close()
    print("\n✅ Деплой завершён!")


if __name__ == "__main__":
    main()
