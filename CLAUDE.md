# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Язык общения

- Всегда отвечать на русском языке
- Не делать того, о чем не просят

## Архитектура проекта

Это full-stack приложение для управления SSN данными с поиском, e-commerce и enrichment функциями.

### Основные компоненты

**Backend (Python FastAPI):**
- `api/public/` - Публичное API (порт 8000) - аутентификация JWT, поиск SSN, корзина, заказы
- `api/enrichment/` - API обогащения данных (порт 8001) - управление записями, webhook
- `api/common/` - Общие модули (database.py, auth.py, security.py, models)

**Frontend (SvelteKit):**
- Расположен в `frontend/`
- TypeScript + Svelte 5 + TailwindCSS
- Порт 3000 (внутри контейнера), доступ через nginx

**Базы данных:**
- PostgreSQL - пользователи, сессии, корзина, заказы (api/common/models_postgres.py)
- SQLite - SSN записи (api/common/models_sqlite.py)

**Nginx:**
- Порт 80 - reverse proxy для всех сервисов
- `/api/public` → public_api:8000
- `/api/enrichment` → enrichment_api:8001
- `/` → frontend:3000

### Важные особенности архитектуры

1. **Двойной доступ к API**: через nginx (http://localhost/api/public) и напрямую (http://localhost:8000)
2. **JWT аутентификация** для Public API, **API key** для Enrichment API
3. **Общие модули** в api/common/ используются обоими API
4. **Alembic миграции** для PostgreSQL в директории alembic/
5. **CLI утилита** main.py работает напрямую с SQLite базой

## Команды для разработки

### Запуск всех сервисов

```bash
# Запустить все сервисы (postgres, public_api, enrichment_api, frontend, nginx)
docker-compose up -d

# Проверить статус
docker-compose ps

# Просмотр логов
docker-compose logs -f [service_name]
```

### Работа с базой данных

```bash
# Инициализация баз данных
bash scripts/init_db.sh

# Применить миграции Alembic
docker-compose exec public_api alembic upgrade head

# Создать новую миграцию
docker-compose exec public_api alembic revision --autogenerate -m "Description"

# Проверить текущую версию миграции
docker-compose exec public_api alembic current

# Откатить миграцию
docker-compose exec public_api alembic downgrade -1

# Подключиться к PostgreSQL
docker-compose exec postgres psql -U ssn_user -d ssn_users
```

### Frontend разработка

```bash
# Разработка с hot-reload (локально)
cd frontend
pnpm install
pnpm dev  # Запустится на порте 5173

# Проверка типов
pnpm run check

# Форматирование
pnpm run format

# Сборка production
pnpm run build

# Установка shadcn-svelte компонентов
npx shadcn-svelte@0.14 add [component-name]
```

### Backend разработка

```bash
# Запустить Public API с hot-reload
# (Изменить docker-compose.yml: добавить volumes: .:/app и command с --reload)

# Запустить тесты
docker-compose exec public_api python -m pytest tests/

# CLI команды (main.py)
python main.py search ssn 123-45-6789
python main.py search email test@example.com
python main.py add ssn_1 --ssn 123-45-6789 --firstname John --lastname Doe
```

### Тестирование API

```bash
# Public API здоровье
curl http://localhost/api/public/health

# Enrichment API здоровье
curl http://localhost/api/enrichment/health

# Регистрация пользователя
curl -X POST http://localhost/api/public/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "test", "email": "test@example.com", "password": "password123"}'

# Вход
curl -X POST http://localhost/api/public/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test&password=password123"
```

### Перезапуск и пересборка

**ВАЖНО: Когда пересобирать контейнеры**

После изменений в коде необходимо пересобрать и перезапустить соответствующие контейнеры:

- **Backend API изменения** (`api/public/`, `api/enrichment/`, `api/common/`):
  ```bash
  docker-compose down
  docker-compose up -d --build public_api enrichment_api
  ```

- **Frontend изменения** (`frontend/`):
  ```bash
  docker-compose down
  docker-compose up -d --build frontend
  ```

- **Nginx конфигурация** (`nginx/nginx.conf`):
  ```bash
  docker-compose restart nginx
  # Или для полной пересборки:
  docker-compose up -d --build nginx
  ```

- **Изменения в зависимостях**:
  - Backend: после изменения `requirements.txt` пересобрать API контейнеры
  - Frontend: после изменения `package.json` или `pnpm-lock.yaml` пересобрать frontend

**Общие команды:**

```bash
# Перезапустить сервис (без пересборки)
docker-compose restart [service_name]

# Пересобрать и перезапустить конкретный сервис
docker-compose up -d --build [service_name]

# Остановить все и запустить заново (рекомендуется при проблемах)
docker-compose down
docker-compose up -d

# Остановить и удалить volumes (осторожно - удаляет данные БД!)
docker-compose down -v
```

## Структура кода

### Backend модули

- `api/common/database.py` - подключение к PostgreSQL и SQLite
- `api/common/auth.py` - JWT токены, хеширование паролей
- `api/common/security.py` - проверка API ключей
- `api/common/models_postgres.py` - SQLAlchemy модели (User, Order, CartItem, Session)
- `api/common/models_sqlite.py` - Pydantic модели для SSN данных
- `api/common/whitepages_client.py` - интеграция с Whitepages API
- `api/public/routers/` - роуты для auth, search, ecommerce, enrichment, stats
- `api/enrichment/routers/records.py` - CRUD операции для SSN записей

### Frontend структура

- `frontend/src/routes/` - страницы SvelteKit (файловый роутинг)
- `frontend/src/lib/` - компоненты и утилиты
- API запросы через axios к `/api/public`

### Database модули

- `database/search_engine.py` - поисковый движок для SSN
- `database/data_manager.py` - управление данными
- `database/db_schema.py` - схема SQLite базы

## Переменные окружения

Ключевые переменные в `.env`:

```bash
# PostgreSQL
POSTGRES_USER=ssn_user
POSTGRES_PASSWORD=change_me_strong_password
POSTGRES_DB=ssn_users
DATABASE_URL=postgresql+asyncpg://ssn_user:password@postgres:5432/ssn_users

# JWT
JWT_SECRET=change_me_long_random_string_min_32_chars
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# API Keys
ENRICHMENT_API_KEYS=key1_change_me,key2_change_me
WHITEPAGES_API_KEY=your_whitepages_api_key_here
WEBHOOK_SECRET=change_me_webhook_secret_min_32_chars

# CORS
ALLOWED_ORIGINS=*

# Paths
SQLITE_PATH=/app/data/ssn_database.db
```

## Важные детали для разработки

1. **Миграции Alembic**: всегда выполнять из корня проекта `/root/soft/`, не из поддиректорий
2. **Порты**: сервис работает на порте 5173 в dev режиме, 80 в production через nginx
3. **CORS**: настроен через ALLOWED_ORIGINS в .env
4. **Enrichment стоимость**: $1.00 за запрос, требуется баланс пользователя
5. **Rate limiting**: настроен для всех API endpoints через slowapi
6. **Whitepages API**: требуется валидный API ключ для функции обогащения данных

## Debugging

```bash
# Проверить переменные окружения в контейнере
docker-compose exec public_api env | grep DATABASE

# Проверить подключение к PostgreSQL
docker-compose exec postgres pg_isready -U ssn_user

# Логи с фильтром
docker-compose logs public_api | grep ERROR

# Войти в контейнер
docker-compose exec public_api bash
docker-compose exec frontend sh

# Проверить сеть
docker-compose exec nginx ping public_api
```

## Документация API

- Public API Swagger: http://localhost/api/public/docs
- Enrichment API Swagger: http://localhost/api/enrichment/docs
- Полная документация: README_API.md
- Deployment: DEPLOYMENT.md
