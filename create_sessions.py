import subprocess
import os

BASE = os.path.dirname(os.path.abspath(__file__))

# Всі боти
BOTS = ["bot"] + [f"bot{i}" for i in range(1, 12)]

def tmux_has(session):
    """Перевіряє чи існує сесія"""
    return subprocess.run(
        ["tmux", "has-session", "-t", session],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    ).returncode == 0

def tmux_kill(session):
    """Зупиняє сесію"""
    if tmux_has(session):
        print(f"[INFO] Зупиняю сесію: {session}")
        subprocess.run(["tmux", "kill-session", "-t", session])

def tmux_start(session, cwd):
    """Створює сесію і запускає бота разом з установкою зависимостей"""
    print(f"[INFO] Створюю сесію: {session}")
    # команда bash: встановити залежності, запустити бот, залишити сесію відкритою
    cmd = (
        "bash -c '"
        "if [ -f requirements.txt ]; then pip install -r requirements.txt; fi && "
        "python3 main.py || exec bash'"
    )
    subprocess.run([
        "tmux", "new-session", "-d", "-s", session,
        f"cd {cwd} && {cmd}"
    ])

def main():
    # видаляємо старі сесії
    for bot in BOTS:
        tmux_kill(bot)

    # створюємо нові сесії
    for bot in BOTS:
        path = os.path.join(BASE, bot)
        tmux_start(bot, path)

if __name__ == "__main__":
    main()
