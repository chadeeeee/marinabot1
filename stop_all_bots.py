import json
import subprocess
import os

with open("/root/mail_bot/marinabot1/groups.json", "r") as f:
    groups = json.load(f)

def stop_container(bot_name):
    running = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True
    ).stdout.splitlines()
    if bot_name in running:
        subprocess.run(["docker", "stop", bot_name], check=True)
        print(f"Зупинено контейнер {bot_name}")

# зупиняємо всі контейнери
for bots in groups.values():
    for bot in bots:
        stop_container(bot)
