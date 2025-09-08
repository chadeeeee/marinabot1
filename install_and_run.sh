#!/bin/bash
set -e

# Зупиняємо Docker і видаляємо старі пакети
sudo systemctl stop docker docker.socket 2>/dev/null || true
sudo dnf remove -y docker docker-client docker-client-latest docker-common \
  docker-latest docker-latest-logrotate docker-logrotate docker-engine

# Чистимо каталоги Docker
sudo rm -rf /var/lib/docker /var/lib/containerd

# Додаємо офіційний репозиторій Docker
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# Встановлюємо Docker CE
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Запускаємо і вмикаємо Docker
sudo systemctl enable --now docker

# Оновлюємо репозиторій
git pull

# Збірка та запуск контейнерів
cd my_bot1
docker build -t bot1 .
docker run -d --name bot1 -p 9541:80 bot1
cd ..

cd my_bot3
docker build -t bot3 .
docker run -d --name bot3 -p 7423:80 bot3
cd ..

cd my_bot8
docker build -t bot8 .
docker run -d --name bot8 -p 2345:80 bot8
cd ..

cd crypto_always
docker build -t bot15 .
docker run -d --name bot15 -p 3248:80 bot15
cd ..
