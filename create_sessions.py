import subprocess
import os

BASE = os.path.dirname(os.path.abspath(__file__))
ENTRY = "python3 main.py"

# всі боти
BOTS = ["bot"] + [f"bot{i}" for i in range(1, 12)]

def tmux_has(session):
    """Перевіряє чи існує сесія"""
    return subprocess.run(
        ["tmux", "has-session", "-t", session],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    ).returncode == 0

def tmux_kill(session):
    """Вбиває сесію tmux"""
    if tmux_has(session):
        print(f"[INFO] Зупиняю сесію: {session}")
        subprocess.run(["tmux", "kill-session", "-t", session])

def tmux_start(session, cmd, cwd):
    """Створює нову сесію і запускає бота"""
    print(f"[INFO] Створюю сесію: {session}")
    subprocess.run([
        "tmux", "new-session", "-d", "-s", session,
        f"cd {cwd} && {cmd} || exec bash"
    ])

def main():
    # видаляємо всі старі сесії
    for bot in BOTS:
        tmux_kill(bot)

    # створюємо нові сесії
    for bot in BOTS:
        path = os.path.join(BASE, bot)
        tmux_start(bot, ENTRY, path)

if __name__ == "__main__":
    main()
