import json
import subprocess
from datetime import datetime

# завантажуємо групи
with open("groups.json", "r") as f:
    groups = json.load(f)

# сьогоднішній день
day = datetime.now().timetuple().tm_yday  # номер дня у році
group_num = ((day - 1) % 4) + 1           # визначаємо групу (1-4)

print(f"Сьогодні працює група {group_num} + постійні боти")

# запускаємо постійні
for bot in groups["always"]:
    subprocess.run(["docker", "start", bot])

# запускаємо потрібну групу
for num, bots in groups.items():
    if num == "always":
        continue
    if int(num) == group_num:
        for bot in bots:
            subprocess.run(["docker", "start", bot])
    else:
        for bot in bots:
            subprocess.run(["docker", "stop", bot])
