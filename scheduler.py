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
    # перевірка, чи існує контейнер
    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True, text=True
    )
    existing = result.stdout.splitlines()
    if bot_name not in existing:
        # створюємо контейнер із Dockerfile у відповідній папці
        path = os.path.join(os.getcwd(), bot_name)
        print(f"Створюю контейнер {bot_name}...")
        subprocess.run(["docker", "build", "-t", bot_name, path])
    else:
        print(f"Контейнер {bot_name} вже існує.")

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
