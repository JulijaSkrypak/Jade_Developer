#!/usr/bin/env python3
"""
scripts/read_remote_logs.py
Безопасное чтение логов с удаленного VPS с использованием SSH-ключа.
"""
import argparse
import paramiko
import sys

HOST = "178.105.1.60"
USER = "root"
KEY_FILE = "/home/julija/.ssh/vps_jade_developer"

def main():
    parser = argparse.ArgumentParser(description="Безопасное чтение логов с VPS через SSH-ключ.")
    parser.add_argument("-u", "--unit", default="vibe-bot", help="Имя systemd-юнита (по умолчанию: vibe-bot)")
    parser.add_argument("-s", "--since", default="20 minutes ago", help="Временной диапазон для journalctl (по умолчанию: 20 minutes ago)")
    parser.add_argument("-n", "--lines", type=int, help="Количество строк с конца (переопределяет --since, если задано)")
    parser.add_argument("-e", "--exclude", default="getUpdates", help="Паттерн для исключения строк (по умолчанию: getUpdates)")
    
    args = parser.parse_args()
    
    # Формируем команду для journalctl
    journal_cmd = f"journalctl -u {args.unit}"
    if args.lines:
        journal_cmd += f" -n {args.lines}"
    else:
        journal_cmd += f" --since \"{args.since}\""
    journal_cmd += " --no-pager"
    
    # Если есть паттерн исключения, добавляем grep -v
    if args.exclude:
        # Экранируем спецсимволы в паттерне
        exclude_escaped = args.exclude.replace('"', '\\"')
        cmd = f"{journal_cmd} | grep -v \"{exclude_escaped}\""
    else:
        cmd = journal_cmd

    print(f"🔌 Подключение к {HOST} по ключу...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(HOST, username=USER, key_filename=KEY_FILE, timeout=15)
        print(f"✅ Подключено. Выполнение команды: {cmd}")
        
        stdin, stdout, stderr = client.exec_command(cmd)
        
        # Чтение вывода
        out_content = stdout.read().decode("utf-8", errors="replace")
        err_content = stderr.read().decode("utf-8", errors="replace")
        
        if out_content.strip():
            print("\n--- ВЫВОД ЛОГОВ ---")
            print(out_content)
            print("-------------------")
        else:
            print("\nЛоги за указанный период отсутствуют или отфильтрованы.")
            
        if err_content.strip():
            print("\n⚠️  [STDERR]:")
            print(err_content, file=sys.stderr)
            
    except Exception as e:
        print(f"❌ Ошибка подключения или выполнения команды: {e}", file=sys.stderr)
    finally:
        client.close()
        print("🔌 Соединение закрыто.")

if __name__ == "__main__":
    main()
