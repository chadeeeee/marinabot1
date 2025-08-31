import subprocess
import os

BASE = os.path.dirname(os.path.abspath(__file__))
# ENTRY = "python3 main.py"
ENTRY = 'bash -c "echo HELLO from $(pwd); sleep 9999"'

BOTS = ["bot"] + [f"bot{i}" for i in range(1, 12)]

def tmux_has(session):
    return subprocess.run(
        ["tmux", "has-session", "-t", session],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    ).returncode == 0

def tmux_start(session, cmd, cwd):
    if not tmux_has(session):
        print(f"[INFO] Створюю сесію: {session}")
        subprocess.run([
            "tmux", "new-session", "-d", "-s", session,
            f"cd {cwd} && {cmd}"
        ])
    else:
        print(f"[INFO] Сесія {session} вже існує")

def main():
    for bot in BOTS:
        path = os.path.join(BASE, bot)
        tmux_start(bot, ENTRY, path)

if __name__ == "__main__":
    main()
