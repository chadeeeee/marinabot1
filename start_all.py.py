import subprocess

bots = [
    # "mybot_1/main.py",
    # "mybot_3/main.py",
    "mybot_8/main.py",
    "crypto_always/main.py"
]

processes = []
for bot in bots:
    print(f"Запускаю {bot} ...")
    processes.append(subprocess.Popen(["python", bot]))

for p in processes:
    p.wait()
