import subprocess

print("-> Створюю сесію...")
res = subprocess.run([
    "tmux", "new-session", "-d", "-s", "demo",
    "echo 'Hello from tmux' && sleep 1000"
], capture_output=True, text=True)

print("STDOUT:", res.stdout)
print("STDERR:", res.stderr)
print("Return code:", res.returncode)
