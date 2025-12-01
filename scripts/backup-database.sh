#!/bin/bash

#############################################
# Скрипт резервного копирования баз данных
# Использование: bash scripts/backup-database.sh
#############################################

set -e

# Цвета
GREEN='\033[0;32m'
NC='\033[0m'

BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
POSTGRES_BACKUP="$BACKUP_DIR/postgres_${TIMESTAMP}.sql"
SQLITE_BACKUP="$BACKUP_DIR/sqlite_${TIMESTAMP}.db"

echo -e "${GREEN}===== Создание резервной копии баз данных =====${NC}"

# Создание директории
mkdir -p "$BACKUP_DIR"

# Бэкап PostgreSQL
echo "Создание бэкапа PostgreSQL..."
docker-compose exec -T postgres pg_dump -U ssn_user ssn_users > "$POSTGRES_BACKUP"
gzip "$POSTGRES_BACKUP"
echo "✓ PostgreSQL: ${POSTGRES_BACKUP}.gz"

# Бэкап SQLite
echo "Создание бэкапа SQLite..."
if [ -f "data/ssn_database.db" ]; then
    cp data/ssn_database.db "$SQLITE_BACKUP"
    gzip "$SQLITE_BACKUP"
    echo "✓ SQLite: ${SQLITE_BACKUP}.gz"
else
    echo "⚠ SQLite база не найдена"
fi

# Удаление старых бэкапов (старше 30 дней)
echo "Очистка старых бэкапов (старше 30 дней)..."
find "$BACKUP_DIR" -name "*.gz" -mtime +30 -delete
echo "✓ Старые бэкапы удалены"

echo ""
echo -e "${GREEN}✓ Резервное копирование завершено!${NC}"
echo "Бэкапы сохранены в: $BACKUP_DIR"
echo ""
echo "Восстановление из бэкапа:"
echo "  PostgreSQL: gunzip -c $POSTGRES_BACKUP.gz | docker-compose exec -T postgres psql -U ssn_user ssn_users"
echo "  SQLite: gunzip -c $SQLITE_BACKUP.gz > data/ssn_database.db"
