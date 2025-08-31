#!/usr/bin/env python3
import os
import subprocess
import time
from datetime import datetime
import pytz

# Шлях до проекту
BASE = os.path.abspath("proj")
ENTRY = "python3 main.py"

MAIN_BOT = os.path.join(BASE, "bot")

OTHER_BOTS = [os.path.join(BASE, f"bot{i}") for i in range(1, 12)]

TZ = pytz.timezone("Europe/Kyiv")

def tmux_has(session):
    return subprocess.run(["tmux", "has-session", "-t", session],
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0

def tmux_start(session, cmd, cwd):
    if not tmux_has(session):
        subprocess.run(["tmux", "new-session", "-d", "-s", session,
                        f"cd {cwd} && {cmd}"])

def tmux_kill(session):
    if tmux_has(session):
        subprocess.run(["tmux", "kill-session", "-t", session])

def sanitize(path):
    return os.path.basename(path)

def manage_bots():
    now = datetime.now(TZ)
    hour = now.hour

    tmux_start(sanitize(MAIN_BOT), ENTRY, MAIN_BOT)

    if 9 <= hour < 19:
        for path in OTHER_BOTS:
            tmux_start(sanitize(path), ENTRY, path)
    else:
        for path in OTHER_BOTS:
            tmux_kill(sanitize(path))

def main():
    while True:
        manage_bots()
        time.sleep(60)

if __name__ == "__main__":
    main()
