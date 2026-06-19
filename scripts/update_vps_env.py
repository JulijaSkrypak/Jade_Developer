#!/usr/bin/env python3
"""
scripts/update_vps_env.py
Обновляет файл .env на VPS данными из локального credentials.env и перезапускает бота.
"""
import os
import paramiko

HOST = "178.105.1.60"
USER = "root"
KEY_FILE = "/home/julija/.ssh/vps_jade_developer"

def main():
    cred_path = "/home/julija/Документы/Antigravity/Jade_Developer/credentials.env"
    env_vars = {}
    
    if not os.path.exists(cred_path):
        print(f"❌ Ошибка: Локальный файл {cred_path} не найден.")
        return
        
    with open(cred_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip()

    bot_token = env_vars.get("BOT_TOKEN")
    openrouter_key = env_vars.get("OPENROUTER_API_KEY")
    groq_key = env_vars.get("GROQ_API_KEY")

    if not bot_token:
        print("❌ Ошибка: BOT_TOKEN не найден в credentials.env")
        return

    # Формируем контент для удаленного .env
    remote_env_content = f"TELEGRAM_TOKEN={bot_token}\n"
    if openrouter_key:
        remote_env_content += f"OPENROUTER_API_KEY={openrouter_key}\n"
    if groq_key:
        remote_env_content += f"GROQ_API_KEY={groq_key}\n"

    print("🔌 Подключаюсь к VPS по ключу...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(HOST, username=USER, key_filename=KEY_FILE, timeout=15)
        print("✅ Успешно подключено!")

        # Пишем удаленный .env
        sftp = client.open_sftp()
        with sftp.file("/home/bridge/vibe-telegram-bot/.env", "w") as f:
            f.write(remote_env_content)
        sftp.close()
        print("✅ Удаленный .env обновлен!")

        # Перезапускаем бота
        print("🔄 Перезапускаю vibe-bot...")
        stdin, stdout, stderr = client.exec_command("systemctl restart vibe-bot")
        stdout.read() # ждем завершения команды
        print("✅ Бот перезапущен!")
        
        # Проверяем статус
        print("ℹ️  Статус vibe-bot:")
        stdin, stdout, stderr = client.exec_command("systemctl status vibe-bot --no-pager -l")
        status_out = stdout.read().decode()
        
        # Маскируем токен в выводе статуса, если вдруг он там проскочит
        if "bot" in status_out:
            import re
            status_out = re.sub(r"bot[0-9]+:[a-zA-Z0-9_-]+", "bot[REDACTED]", status_out)
        print(status_out)

    except Exception as e:
        print(f"❌ Произошла ошибка: {e}")
    finally:
        client.close()
        print("🔌 Соединение закрыто.")

if __name__ == "__main__":
    main()
