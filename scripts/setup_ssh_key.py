#!/usr/bin/env python3
"""
setup_ssh_key.py — копирует публичный SSH-ключ на VPS через paramiko.
Используется ОДИН РАЗ для настройки беспарольного подключения.
После этого подключение через ключ работает без пароля.
"""

import os
import sys
import paramiko

# ─── Конфигурация ────────────────────────────────────────────────────────────
VPS_HOST = "178.105.1.60"
VPS_USER = "root"
VPS_PASSWORD = os.environ.get("VPS_PASSWORD")
PUB_KEY_PATH = os.path.expanduser("~/.ssh/vps_jade_developer.pub")

# ─── Проверки ─────────────────────────────────────────────────────────────────
if not VPS_PASSWORD:
    print("❌ Ошибка: переменная VPS_PASSWORD не задана в окружении.")
    print("   Запусти: export VPS_PASSWORD=<твой_пароль>")
    sys.exit(1)

if not os.path.exists(PUB_KEY_PATH):
    print(f"❌ Ошибка: публичный ключ не найден: {PUB_KEY_PATH}")
    sys.exit(1)

# ─── Читаем публичный ключ ────────────────────────────────────────────────────
with open(PUB_KEY_PATH, "r") as f:
    pub_key = f.read().strip()

print(f"✅ Публичный ключ прочитан: {PUB_KEY_PATH}")
print(f"   Ключ: {pub_key[:50]}...")

# ─── Подключаемся к VPS через пароль ─────────────────────────────────────────
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

print(f"\n🔌 Подключаюсь к {VPS_USER}@{VPS_HOST} (через пароль)...")

try:
    client.connect(
        hostname=VPS_HOST,
        username=VPS_USER,
        password=VPS_PASSWORD,
        timeout=15,
    )
    print("✅ Подключение по паролю успешно!")
except Exception as e:
    print(f"❌ Ошибка подключения: {e}")
    sys.exit(1)

# ─── Настройка authorized_keys на VPS ────────────────────────────────────────
commands = [
    "mkdir -p ~/.ssh",
    "chmod 700 ~/.ssh",
    f'echo "{pub_key}" >> ~/.ssh/authorized_keys',
    "chmod 600 ~/.ssh/authorized_keys",
    "sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys",  # убираем дубли
]

print("\n🔧 Настраиваю authorized_keys на VPS...")
for cmd in commands:
    stdin, stdout, stderr = client.exec_command(cmd)
    exit_code = stdout.channel.recv_exit_status()
    err = stderr.read().decode().strip()
    if exit_code != 0 and err:
        print(f"   ⚠️  Команда: {cmd}")
        print(f"      Ошибка: {err}")
    else:
        display_cmd = cmd if len(cmd) < 60 else cmd[:57] + "..."
        print(f"   ✅ {display_cmd}")

# ─── Проверка — читаем authorized_keys ───────────────────────────────────────
print("\n📋 Проверяю authorized_keys на VPS...")
stdin, stdout, stderr = client.exec_command("cat ~/.ssh/authorized_keys")
content = stdout.read().decode().strip()
if pub_key[:40] in content:
    print("✅ Публичный ключ успешно добавлен в authorized_keys!")
else:
    print("❌ Ключ НЕ найден в authorized_keys — что-то пошло не так!")
    print(f"   Содержимое файла:\n{content}")
    client.close()
    sys.exit(1)

client.close()
print("\n🎉 Готово! Теперь можно подключаться через ключ:")
print(f"   ssh -i ~/.ssh/vps_jade_developer {VPS_USER}@{VPS_HOST}")
