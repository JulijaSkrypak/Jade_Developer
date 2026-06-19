#!/usr/bin/env python3
import paramiko

HOST = "178.105.1.60"
USER = "root"
KEY_FILE = "/home/julija/.ssh/vps_jade_developer"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, key_filename=KEY_FILE, timeout=15)

stdin, stdout, stderr = client.exec_command("cat /home/bridge/vibe-telegram-bot/bot.py")
content = stdout.read().decode()
err = stderr.read().decode()
if err:
    print("STDERR:", err)
else:
    print(content)

client.close()
