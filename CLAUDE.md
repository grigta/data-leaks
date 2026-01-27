# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Язык общения

- Всегда отвечать на русском языке
- Не делать того, о чем не просят

## Домены и структура папок

```
/opt/soft/
├── huntrssn.cc/              # Основной сайт
│   ├── frontend/             # SvelteKit frontend
│   ├── api/
│   │   ├── common -> shared  # Симлинк на общие модули
│   │   └── public/           # Public API
│   ├── database -> shared    # Симлинк
│   ├── alembic -> shared     # Симлинк
│   └── Dockerfile
├── infinitymoneyyy.xyz/      # Админка
│   ├── admin-frontend/       # SvelteKit admin frontend
│   ├── api/
│   │   ├── common -> shared  # Симлинк на общие модули
│   │   └── admin/            # Admin API
│   └── Dockerfile
├── shared/                   # Общие компоненты
│   ├── api/common/           # Общие модули Python
│   ├── database/             # SQLite модули
│   ├── alembic/              # Миграции PostgreSQL
│   └── requirements.txt
├── bot/                      # Telegram бот
├── data/                     # SQLite база данных
├── docker-compose.yml
├── docker-compose.prod.yml
└── nginx.conf
```

## Архитектура проекта

Это full-stack приложение для управления SSN данными с поиском, e-commerce и SMS функциями.

### Основные компоненты

**huntrssn.cc (основной сайт):**
- `huntrssn.cc/frontend/` - SvelteKit frontend
- `huntrssn.cc/api/public/` - Public API (порт 8000)

**infinitymoneyyy.xyz (админка):**
- `infinitymoneyyy.xyz/admin-frontend/` - SvelteKit admin frontend
- `infinitymoneyyy.xyz/api/admin/` - Admin API (порт 8002)

**Общие компоненты (shared/):**
- `shared/api/common/` - Общие модули (database.py, auth.py, models)
- `shared/database/` - SQLite search engine
- `shared/alembic/` - PostgreSQL миграции

**Базы данных:**
- PostgreSQL - пользователи, сессии, заказы (shared/api/common/models_postgres.py)
- SQLite - SSN записи (shared/api/common/models_sqlite.py)

**Nginx:**
- huntrssn.cc: `/api/public` → public_api:8000, `/` → frontend:3000
- infinitymoneyyy.xyz: `/api/admin` → admin_api:8002, `/` → admin_frontend:3000

## Команды для разработки

### Запуск всех сервисов

```bash
# Запустить все сервисы
docker-compose up -d

# Проверить статус
docker-compose ps

# Просмотр логов
docker-compose logs -f [service_name]
```

### Работа с базой данных

```bash
# Применить миграции Alembic
docker-compose exec public_api alembic upgrade head

# Создать новую миграцию
docker-compose exec public_api alembic revision --autogenerate -m "Description"

# Подключиться к PostgreSQL
docker-compose exec postgres psql -U ssn_user -d ssn_users
```

### Frontend разработка

```bash
# huntrssn.cc frontend
cd huntrssn.cc/frontend
pnpm install
pnpm dev  # Порт 5173

# infinitymoneyyy.xyz admin frontend
cd infinitymoneyyy.xyz/admin-frontend
pnpm install
pnpm dev  # Порт 5174
```

### Backend разработка

```bash
# CLI команды (main.py)
python main.py search ssn 123-45-6789
python main.py search email test@example.com
```

### Перезапуск и пересборка

```bash
# Backend API изменения
docker-compose up -d --build public_api admin_api

# Frontend изменения
docker-compose up -d --build frontend admin_frontend

# Nginx конфигурация
docker-compose restart nginx
```

## Структура кода

### Backend модули (shared/api/common/)

- `database.py` - подключение к PostgreSQL и SQLite
- `auth.py` - JWT токены, хеширование паролей
- `models_postgres.py` - SQLAlchemy модели (User, Order, SMSRental)
- `models_sqlite.py` - Pydantic модели для SSN данных
- `searchbug_client.py` - интеграция с SearchBug API
- `daisysms_client.py` - интеграция с DaisySMS API

### Public API (huntrssn.cc/api/public/)

- `routers/auth.py` - аутентификация
- `routers/search.py` - поиск SSN
- `routers/ecommerce.py` - заказы, покупки
- `routers/sms.py` - SMS сервис

### Admin API (infinitymoneyyy.xyz/api/admin/)

- `routers/users.py` - управление пользователями
- `routers/tickets.py` - обработка тикетов
- `routers/analytics.py` - статистика

## Переменные окружения

```bash
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://ssn_user:password@postgres:5432/ssn_users

# JWT
JWT_SECRET=change_me_long_random_string_min_32_chars

# CORS
ALLOWED_ORIGINS=https://huntrssn.cc,https://www.huntrssn.cc
ALLOWED_ORIGINS_ADMIN=https://infinitymoneyyy.xyz,https://www.infinitymoneyyy.xyz

# SQLite
SQLITE_PATH=/app/data/ssn_database.db
```

## Debugging

```bash
# Логи
docker-compose logs public_api | grep ERROR

# Войти в контейнер
docker-compose exec public_api bash
docker-compose exec frontend sh
```

## Документация API

- Public API Swagger: http://huntrssn.cc/api/public/docs
- Admin API Swagger: http://infinitymoneyyy.xyz/api/admin/docs
