# Database Migration Guide

This guide covers working with Alembic migrations for the PostgreSQL database schema.

## 1. Откат миграции (Rollback)

Если что-то пошло не так после применения миграции:

```bash
# Откатить последнюю миграцию
alembic downgrade -1

# Откатить до конкретной версии
alembic downgrade abc123

# Откатить все миграции
alembic downgrade base
```

## 2. Создание новых миграций

Когда вы изменяете модели в `api/common/models_postgres.py`:

```bash
# Автогенерация миграции
alembic revision --autogenerate -m "Add new column to users"

# Ручное создание миграции (без autogenerate)
alembic revision -m "Custom migration"
```

## 3. Работа с несколькими окружениями

**Development:**
```bash
export DATABASE_URL="postgresql+asyncpg://ssn_user:dev_password@localhost:5432/ssn_users_dev"
alembic upgrade head
```

**Staging:**
```bash
export DATABASE_URL="postgresql+asyncpg://ssn_user:staging_password@staging-db:5432/ssn_users_staging"
alembic upgrade head
```

**Production:**
```bash
export DATABASE_URL="postgresql+asyncpg://ssn_user:prod_password@prod-db:5432/ssn_users"
alembic upgrade head
```

## 4. Работа в Docker

```bash
# Применить миграции в Docker контейнере
docker-compose exec public_api alembic upgrade head

# Создать миграцию в Docker
docker-compose exec public_api alembic revision --autogenerate -m "Migration name"

# Откатить миграцию в Docker
docker-compose exec public_api alembic downgrade -1
```

## 5. Best Practices

✅ **DO:**
- Всегда проверяйте сгенерированные миграции перед применением
- Тестируйте миграции на development окружении перед production
- Делайте backup БД перед применением миграций в production
- Используйте осмысленные имена для миграций
- Коммитьте файлы миграций в git

❌ **DON'T:**
- Не редактируйте уже примененные миграции
- Не удаляйте файлы миграций из `alembic/versions/`
- Не применяйте миграции напрямую в production без тестирования
- Не используйте `--sql` флаг в production (только для проверки)

## 6. Troubleshooting

**Проблема: "Can't locate revision"**
```bash
# Проверить текущую версию
alembic current

# Проверить историю
alembic history

# Пометить БД как находящуюся на конкретной версии
alembic stamp head
```

**Проблема: "Multiple heads detected"**
```bash
# Объединить ветки миграций
alembic merge -m "Merge branches" head1 head2
```

**Проблема: Миграция зависла**
```bash
# Проверить locks в PostgreSQL
SELECT * FROM pg_locks WHERE NOT granted;

# Убить зависший процесс
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle in transaction';
```

## 7. Backup и Restore

**Backup перед миграцией:**
```bash
# Backup всей БД
pg_dump -U ssn_user -d ssn_users > backup_before_migration.sql

# Backup только схемы
pg_dump -U ssn_user -d ssn_users --schema-only > schema_backup.sql

# Backup только данных
pg_dump -U ssn_user -d ssn_users --data-only > data_backup.sql
```

**Restore после неудачной миграции:**
```bash
# Откатить миграцию
alembic downgrade -1

# Или восстановить из backup
psql -U ssn_user -d ssn_users < backup_before_migration.sql
```

## 8. CI/CD Integration

Пример для GitHub Actions:

```yaml
- name: Run migrations
  run: |
    export DATABASE_URL=${{ secrets.DATABASE_URL }}
    alembic upgrade head
```

Пример для GitLab CI:

```yaml
migrate:
  script:
    - export DATABASE_URL=$DATABASE_URL
    - alembic upgrade head
```

## 9. Мониторинг миграций

Создайте скрипт для проверки состояния миграций:

```python
import asyncio
from sqlalchemy import text
from api.common.database import async_engine

async def check_migration_status():
    async with async_engine.connect() as conn:
        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        version = result.scalar()
        print(f"Current migration version: {version}")

asyncio.run(check_migration_status())
```

## 10. Полезные команды

```bash
# Показать текущую версию
alembic current -v

# Показать SQL для миграции без выполнения
alembic upgrade head --sql

# Показать разницу между моделями и БД
alembic check

# Показать историю миграций
alembic history --verbose

# Показать информацию о конкретной миграции
alembic show abc123
```
