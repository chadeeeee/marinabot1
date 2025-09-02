import subprocess

def stop_and_remove_all_containers():
    # Отримати список усіх контейнерів (запущених і зупинених)
    result = subprocess.run(
        ["docker", "ps", "-aq"],
        capture_output=True, text=True
    )
    container_ids = result.stdout.splitlines()

    if not container_ids:
        print("Немає контейнерів для зупинки/видалення.")
        return

    # Зупинити всі
    subprocess.run(["docker", "stop"] + container_ids, check=False)
    print("Зупинено всі контейнери.")

    # Видалити всі
    subprocess.run(["docker", "rm"] + container_ids, check=False)
    print("Видалено всі контейнери.")

if __name__ == "__main__":
    stop_and_remove_all_containers()
