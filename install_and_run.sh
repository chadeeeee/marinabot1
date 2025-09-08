#!/bin/bash
set -e

# Зупинка та видалення старого Docker
sudo systemctl stop docker docker.socket 2>/dev/null || true
sudo dnf remove -y docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine || true
sudo rm -rf /var/lib/docker /var/lib/containerd

# Встановлення нового Docker
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker

# Оновлення коду
git pull

# Запуск ботів
cd my_bot1
docker build -t bot1 . && docker run -d --name bot1 -p 9541:80 bot1 || true
cd ..

cd my_bot3
docker build -t bot3 . && docker run -d --name bot3 -p 7423:80 bot3 || true
cd ..

cd my_bot8
docker build -t bot8 . && docker run -d --name bot8 -p 2345:80 bot8 || true
cd ..
