#!/usr/bin/env python3
import paramiko
import time

HOST = "178.105.1.60"
USER = "root"
PASSWORD = "htTgTgtWrqdP"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=15)

def run(cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    return out + ("\n" + err if err else "")

print("═"*60)
print("СТАТУС СЕРВИСА:")
print("═"*60)
print(run("systemctl status vibe-bot --no-pager -l"))

print("\n" + "═"*60)
print("ПОСЛЕДНИЕ ЛОГИ (40 строк):")
print("═"*60)
print(run("journalctl -u vibe-bot -n 40 --no-pager"))

client.close()
