import json
import subprocess
from datetime import datetime
import os

# завантажуємо групи
with open("groups.json", "r") as f:
    groups = json.load(f)
    


# сьогоднішній день  
day = datetime.now().timetuple().tm_yday
group_num = ((day - 1) % 4) + 1

print(f"Сьогодні працює група {group_num} + постійні боти")

# функція для створення контейнера, якщо його ще немає
def ensure_container(bot_name):
    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True, text=True
    )
    existing = result.stdout.splitlines()
    
    if bot_name not in existing:
        path = os.path.join(os.getcwd(), bot_name)
        print(f"Створюю контейнер {bot_name}...")
        subprocess.run(["docker", "build", "-t", bot_name, path])
        # створюємо і запускаємо контейнер відразу
        subprocess.run(["docker", "run", "-d", "--name", bot_name, bot_name])
    else:
        # перевіримо, чи контейнер запущений
        running = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True
        ).stdout.splitlines()
        if bot_name not in running:
            print(f"Запускаю контейнер {bot_name}...")
            subprocess.run(["docker", "start", bot_name])
        else:
            print(f"Контейнер {bot_name} вже працює.")


# запускаємо постійні
for bot in groups["always"]:
    ensure_container(bot)
    subprocess.run(["docker", "start", bot])

# запускаємо потрібну групу та зупиняємо інші
for num, bots in groups.items():
    if num == "always":
        continue
    if int(num) == group_num:
        for bot in bots:
            ensure_container(bot)
            subprocess.run(["docker", "start", bot])
    else:
        for bot in bots:
            subprocess.run(["docker", "stop", bot])
