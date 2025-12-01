#!/bin/bash

#############################################
# Скрипт деплоя на production сервер
# Использование: bash scripts/deploy-production.sh
#############################################

set -e  # Прерывать выполнение при ошибках

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Переменные
SERVER_IP="192.3.154.51"
DEPLOY_USER="root"  # Измените на вашего пользователя
DEPLOY_PATH="/opt/data-leaks"
BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo -e "${GREEN}===== Деплой на Production Сервер =====${NC}"
echo "Сервер: $SERVER_IP"
echo "Путь: $DEPLOY_PATH"
echo ""

# Функция для вывода сообщений
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Проверка наличия .env.production
if [ ! -f ".env.production" ]; then
    error ".env.production файл не найден! Создайте его на основе .env.production.example"
fi

# Создание директории для бэкапов
mkdir -p "$BACKUP_DIR"

log "Создание архива проекта..."
tar -czf "$BACKUP_DIR/deploy_${TIMESTAMP}.tar.gz" \
    --exclude='node_modules' \
    --exclude='frontend/node_modules' \
    --exclude='admin-frontend/node_modules' \
    --exclude='.svelte-kit' \
    --exclude='frontend/.svelte-kit' \
    --exclude='admin-frontend/.svelte-kit' \
    --exclude='data/*.db' \
    --exclude='backups' \
    --exclude='.git' \
    --exclude='__pycache__' \
    .

log "Архив создан: $BACKUP_DIR/deploy_${TIMESTAMP}.tar.gz"

# Проверка доступности сервера
log "Проверка подключения к серверу..."
if ! ssh -o ConnectTimeout=5 "${DEPLOY_USER}@${SERVER_IP}" "echo 'OK'" &> /dev/null; then
    error "Не удается подключиться к серверу $SERVER_IP"
fi

log "Подключение успешно!"

# Создание директорий на сервере
log "Создание директорий на сервере..."
ssh "${DEPLOY_USER}@${SERVER_IP}" "mkdir -p $DEPLOY_PATH/{data,backups,logs/nginx,certbot/{conf,www}}"

# Копирование архива на сервер
log "Копирование файлов на сервер..."
scp "$BACKUP_DIR/deploy_${TIMESTAMP}.tar.gz" "${DEPLOY_USER}@${SERVER_IP}:$DEPLOY_PATH/"

# Распаковка и установка на сервере
log "Распаковка и настройка на сервере..."
ssh "${DEPLOY_USER}@${SERVER_IP}" "bash -s" << EOF
set -e
cd $DEPLOY_PATH

# Бэкап текущей версии если существует
if [ -d "api" ]; then
    echo "Создание бэкапа текущей версии..."
    tar -czf backups/backup_before_deploy_${TIMESTAMP}.tar.gz \
        api frontend admin-frontend docker-compose.yml nginx.conf || true
fi

# Распаковка нового кода
echo "Распаковка нового кода..."
tar -xzf deploy_${TIMESTAMP}.tar.gz

# Копирование production файлов
echo "Настройка production конфигурации..."
cp .env.production .env
cp docker-compose.production.yml docker-compose.yml
cp nginx.production.conf nginx.conf

# Очистка
rm deploy_${TIMESTAMP}.tar.gz

echo "Файлы успешно развернуты!"
EOF

log "Файлы развернуты на сервере!"

# Получение SSL сертификатов
log "Проверка SSL сертификатов..."
warning "ВАЖНО: Убедитесь, что DNS записи для data-leaks.cc и ois8u912jknasjb.top указывают на $SERVER_IP"
read -p "DNS записи настроены? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    warning "Пропуск получения SSL сертификатов. Запустите позже: bash scripts/setup-ssl.sh"
else
    log "Получение SSL сертификатов..."
    ssh "${DEPLOY_USER}@${SERVER_IP}" "bash -s" << 'EOF'
cd /opt/data-leaks

# Временный nginx конфиг для получения сертификатов
cat > nginx.temp.conf << 'NGINX'
events {
    worker_connections 1024;
}
http {
    server {
        listen 80;
        server_name data-leaks.cc www.data-leaks.cc ois8u912jknasjb.top www.ois8u912jknasjb.top;

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            return 200 "OK";
        }
    }
}
NGINX

# Запуск nginx с временным конфигом
docker run -d --name nginx-temp \
    -p 80:80 \
    -v $(pwd)/nginx.temp.conf:/etc/nginx/nginx.conf:ro \
    -v $(pwd)/certbot/www:/var/www/certbot \
    nginx:alpine

sleep 5

# Получение сертификатов
docker run --rm \
    -v $(pwd)/certbot/conf:/etc/letsencrypt \
    -v $(pwd)/certbot/www:/var/www/certbot \
    certbot/certbot certonly --webroot \
    --webroot-path=/var/www/certbot \
    --email admin@data-leaks.cc \
    --agree-tos \
    --no-eff-email \
    -d data-leaks.cc \
    -d www.data-leaks.cc

docker run --rm \
    -v $(pwd)/certbot/conf:/etc/letsencrypt \
    -v $(pwd)/certbot/www:/var/www/certbot \
    certbot/certbot certonly --webroot \
    --webroot-path=/var/www/certbot \
    --email admin@ois8u912jknasjb.top \
    --agree-tos \
    --no-eff-email \
    -d ois8u912jknasjb.top \
    -d www.ois8u912jknasjb.top

# Остановка временного nginx
docker stop nginx-temp
docker rm nginx-temp
rm nginx.temp.conf
EOF
fi

# Запуск сервисов
log "Запуск Docker контейнеров..."
ssh "${DEPLOY_USER}@${SERVER_IP}" "bash -s" << 'EOF'
cd /opt/data-leaks

# Остановка старых контейнеров
docker-compose down || true

# Сборка и запуск
docker-compose up -d --build

# Ожидание запуска
echo "Ожидание запуска сервисов..."
sleep 10

# Проверка статуса
docker-compose ps

# Применение миграций БД
echo "Применение миграций базы данных..."
docker-compose exec -T public_api alembic upgrade head || true

echo "Сервисы запущены!"
EOF

log "Деплой завершен успешно!"
echo ""
echo -e "${GREEN}✓${NC} Основной сайт: https://data-leaks.cc"
echo -e "${GREEN}✓${NC} Админка: https://ois8u912jknasjb.top"
echo ""
log "Проверка состояния сервисов..."

# Проверка доступности
sleep 5
if curl -f -k https://data-leaks.cc/health &> /dev/null; then
    echo -e "${GREEN}✓${NC} Основной сайт доступен"
else
    warning "Основной сайт недоступен. Проверьте логи: ssh $DEPLOY_USER@$SERVER_IP 'cd $DEPLOY_PATH && docker-compose logs'"
fi

if curl -f -k https://ois8u912jknasjb.top/health &> /dev/null; then
    echo -e "${GREEN}✓${NC} Админка доступна"
else
    warning "Админка недоступна. Проверьте логи: ssh $DEPLOY_USER@$SERVER_IP 'cd $DEPLOY_PATH && docker-compose logs'"
fi

echo ""
log "Полезные команды:"
echo "  Просмотр логов: ssh $DEPLOY_USER@$SERVER_IP 'cd $DEPLOY_PATH && docker-compose logs -f'"
echo "  Перезапуск: ssh $DEPLOY_USER@$SERVER_IP 'cd $DEPLOY_PATH && docker-compose restart'"
echo "  Остановка: ssh $DEPLOY_USER@$SERVER_IP 'cd $DEPLOY_PATH && docker-compose down'"
echo ""
log "Готово!"
