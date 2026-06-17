#!/usr/bin/env python3
"""
scripts/deploy_phase_4_4_xlsx.py
Деплоит Фазу 4.4 (поддержка .xlsx) на VPS:
1. Backup текущего bot.py
2. Загрузка нового bot.py через SFTP
3. Установка openpyxl в venv
4. Проверка синтаксиса Python
5. Перезапуск сервиса vibe-bot
6. Проверка статуса и логов
"""

import paramiko
import time
import os

HOST     = "178.105.1.60"
USER     = "root"
PASSWORD = "htTgTgtWrqdP"
BOT_DIR  = "/home/bridge/vibe-telegram-bot"

LOCAL_BOT_PY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "bot.py"
)


def run(client, cmd, description="", ignore_errors=False):
    print(f"\n{'─'*60}")
    if description:
        print(f"▶ {description}")
    print(f"$ {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, get_pty=False)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out)
    if err and not ignore_errors:
        print(f"[stderr] {err}")
    return out


def main():
    print("🔌 Подключаюсь к VPS...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
    print("✅ Подключено!")

    # 1. Backup текущего bot.py
    backup_name = f"bot.py.backup_before_phase_4_4_xlsx"
    run(client,
        f"cp {BOT_DIR}/bot.py {BOT_DIR}/{backup_name}",
        f"Создаём backup → {backup_name}")

    # 2. Загружаем новый bot.py через SFTP
    print(f"\n{'─'*60}")
    print(f"▶ Загружаем новый bot.py на VPS...")
    print(f"  Локальный: {LOCAL_BOT_PY}")
    sftp = client.open_sftp()
    sftp.put(LOCAL_BOT_PY, f"{BOT_DIR}/bot.py")
    sftp.close()
    print("✅ bot.py загружен!")

    # 3. Устанавливаем openpyxl
    run(client,
        f"cd {BOT_DIR} && source venv/bin/activate && pip install 'openpyxl>=3.1.0' --quiet",
        "Устанавливаем openpyxl в venv")

    # 4. Проверяем что openpyxl установлен
    run(client,
        f"cd {BOT_DIR} && source venv/bin/activate && python -c \"import openpyxl; print('openpyxl OK:', openpyxl.__version__)\"",
        "Проверяем openpyxl")

    # 5. Проверяем синтаксис Python
    run(client,
        f"cd {BOT_DIR} && source venv/bin/activate && python -m py_compile bot.py && echo 'Синтаксис OK'",
        "Проверяем синтаксис bot.py")

    # 6. Перезапускаем сервис
    run(client,
        "systemctl restart vibe-bot",
        "Перезапускаем vibe-bot")

    time.sleep(3)

    # 7. Статус сервиса
    out = run(client,
        "systemctl status vibe-bot --no-pager -l",
        "Статус сервиса vibe-bot")

    # 8. Последние логи
    run(client,
        "journalctl -u vibe-bot -n 20 --no-pager",
        "Последние 20 строк логов")

    # Проверяем что сервис active
    if "active (running)" in out:
        print("\n✅ Деплой Фазы 4.4 завершён успешно!")
        print("   Бот принимает .xlsx файлы.")
    else:
        print("\n⚠️  Сервис может быть не запущен, проверь логи выше.")

    client.close()


if __name__ == "__main__":
    main()
