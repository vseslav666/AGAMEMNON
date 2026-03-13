#!/bin/zsh
set -euo pipefail

# Папка проекта (где docker-compose.yml). Если скрипт лежит рядом — это удобно:
cd "$(dirname "$0")"

export DOCKER_DEFAULT_PLATFORM=linux/amd64

docker compose pull
docker compose build
docker compose config --images > images.txt

docker save --platform=linux/amd64 -o images_amd64.tar $(cat images.txt)

echo "Готово: $(pwd)/images_amd64.tar"

echo
echo "Нажми Enter, чтобы закрыть окно..."
read -r