#!/bin/bash

#############################################
# Простой скрипт переноса проекта на сервер
# Использование: bash scripts/transfer-to-server.sh
#############################################

set -e

SERVER_IP="192.3.154.51"
SERVER_USER="root"
DEPLOY_PATH="/opt/data-leaks"

echo "===== Перенос проекта на сервер ====="
echo "Сервер: $SERVER_USER@$SERVER_IP"
echo "Путь: $DEPLOY_PATH"
echo ""

# Создание архива
echo "Создание архива..."
tar -czf deploy.tar.gz \
    --exclude='node_modules' \
    --exclude='frontend/node_modules' \
    --exclude='admin-frontend/node_modules' \
    --exclude='.svelte-kit' \
    --exclude='data/*.db' \
    --exclude='backups' \
    --exclude='.git' \
    .

echo "✓ Архив создан"

# Копирование на сервер
echo "Копирование на сервер..."
ssh $SERVER_USER@$SERVER_IP "mkdir -p $DEPLOY_PATH"
scp deploy.tar.gz $SERVER_USER@$SERVER_IP:$DEPLOY_PATH/

echo "✓ Файлы скопированы"

# Распаковка
echo "Распаковка на сервере..."
ssh $SERVER_USER@$SERVER_IP << EOF
cd $DEPLOY_PATH
tar -xzf deploy.tar.gz
rm deploy.tar.gz
cp .env.production .env
cp docker-compose.production.yml docker-compose.yml
cp nginx.production.conf nginx.conf
echo "✓ Распаковка завершена"
EOF

# Очистка локального архива
rm deploy.tar.gz

echo ""
echo "✓ Перенос завершен!"
echo ""
echo "Следующие шаги на сервере ($SERVER_USER@$SERVER_IP):"
echo "  1. cd $DEPLOY_PATH"
echo "  2. Отредактируйте .env (пароли, API ключи)"
echo "  3. bash scripts/setup-ssl.sh"
echo "  4. docker-compose up -d --build"
echo "  5. docker-compose exec public_api alembic upgrade head"
