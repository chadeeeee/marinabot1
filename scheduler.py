import json
import subprocess
from datetime import datetime
import os

# --- Конфігурація ---
BASE_IMAGE = "bot_base_image"
DOCKERFILE_PATH = os.path.join(os.getcwd(), "crypto_always")  # папка з Dockerfile

# завантажуємо групи
with open("groups.json", "r") as f:
    groups = json.load(f)

# сьогоднішній день
day = datetime.now().timetuple().tm_yday
group_num = ((day - 1) % 4) + 1
print(f"Сьогодні працює група {group_num} + постійні боти")

# --- Функції ---
def build_base_image():
    """Будує базовий образ один раз"""
    existing = subprocess.run(
        ["docker", "images", "-q", BASE_IMAGE],
        capture_output=True, text=True
    ).stdout.strip()
    if not existing:
        print("Будуємо базовий образ...")
        subprocess.run(["docker", "build", "-t", BASE_IMAGE, DOCKERFILE_PATH], check=True)
    else:
        print("Базовий образ вже існує.")

def ensure_container(bot_name):
    """Створює або запускає контейнер"""
    existing = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True, text=True
    ).stdout.splitlines()

    if bot_name not in existing:
        print(f"Створюю контейнер {bot_name}...")
        subprocess.run(["docker", "run", "-d", "--name", bot_name, BASE_IMAGE], check=True)
    else:
        running = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True
        ).stdout.splitlines()
        if bot_name not in running:
            print(f"Запускаю контейнер {bot_name}...")
            subprocess.run(["docker", "start", bot_name], check=True)
        else:
            print(f"Контейнер {bot_name} вже працює.")

def stop_container(bot_name):
    """Зупиняє контейнер, якщо він запущений"""
    running = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True
    ).stdout.splitlines()
    if bot_name in running:
        subprocess.run(["docker", "stop", bot_name], check=True)
        print(f"Зупинено контейнер {bot_name}")

# --- Основний процес ---
build_base_image()

# запускаємо постійні боти
for bot in groups.get("always", []):
    ensure_container(bot)

# запускаємо потрібну групу та зупиняємо інші
for num, bots in groups.items():
    if num == "always":
        continue
    if int(num) == group_num:
        for bot in bots:
            ensure_container(bot)
    else:
        for bot in bots:
            stop_container(bot)
