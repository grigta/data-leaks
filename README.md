# SSN Data Management System

Full-stack приложение для управления SSN данными с функциями поиска, e-commerce и обогащения данных.

## Архитектура

Проект построен на микросервисной архитектуре с использованием Docker Compose:

- **Public API** (порт 8000) - Публичное API для пользователей
- **Admin API** (порт 8002) - Административное API
- **Enrichment API** (порт 8001) - API обогащения данных
- **Lookup API** (порт 8003) - API поиска данных
- **Telegram Bot** - Бот для создания Manual SSN тикетов
- **Frontend** (порт 5173) - Веб-интерфейс для пользователей
- **Admin Frontend** (порт 3001) - Административная панель
- **Lookup Frontend** (порт 3002) - Интерфейс поиска
- **PostgreSQL** - База данных для пользователей, заказов, корзины
- **Redis** - Distributed rate limiting
- **Nginx** - Reverse proxy (порт 80/443)

## Быстрый старт

### Предварительные требования

- Docker и Docker Compose
- Git
- Минимум 2GB RAM

### Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd soft
```

2. Создайте файл `.env`:
```bash
cp .env.example .env
```

3. Отредактируйте `.env` и установите необходимые значения:
   - `POSTGRES_PASSWORD` - пароль PostgreSQL
   - `JWT_SECRET` - секретный ключ для JWT (минимум 32 символа)
   - `TELEGRAM_BOT_TOKEN` - токен от @BotFather (для Telegram бота)
   - `BOT_API_KEY` - API ключ для WebSocket аутентификации бота
   - Другие конфигурационные параметры

4. Запустите все сервисы:
```bash
docker-compose up -d
```

5. Проверьте статус сервисов:
```bash
docker-compose ps
```

6. Примените миграции базы данных:
```bash
docker-compose exec public_api alembic upgrade head
```

## Документация API

После запуска доступна интерактивная документация:

- Public API: http://localhost/api/public/docs
- Admin API: http://localhost:8002/docs
- Enrichment API: http://localhost:8001/docs
- Lookup API: http://localhost:8003/docs

## Telegram Bot

Telegram бот для создания Manual SSN тикетов через групповые чаты.

### Функциональность

- Активация бота в групповом чате через команду `/login ACCESS_CODE`
- Создание тикетов через упоминание бота с данными пользователя
- Получение уведомлений о статусе тикетов через WebSocket
- Автоматическое переподключение при потере соединения

### Настройка

1. Создайте бота через @BotFather в Telegram:
   - Отправьте `/newbot` в чат с @BotFather
   - Следуйте инструкциям для создания бота
   - Получите токен бота

2. Сгенерируйте API ключ для бота:
```bash
python -c 'import secrets; print(secrets.token_hex(32))'
```

3. Добавьте переменные в `.env`:
```bash
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
BOT_API_KEY=your_secure_random_key_min_32_chars
```

4. Запустите сервис:
```bash
docker-compose up -d telegram_bot
```

### Использование

1. Добавьте бота в групповой чат Telegram
2. Сделайте бота администратором чата (требуется для чтения сообщений)
3. Активируйте бот в чате: `/login XXX-XXX-XXX-XXX`
4. Создайте тикет, упомянув бота:
```
@bot_name Firstname Lastname
Address Line 1
Phone Number
Date of Birth
```

5. Бот создаст тикет и отправит уведомление в чат

### Логи бота

Просмотр логов:
```bash
docker-compose logs -f telegram_bot
```

### Переменные окружения

Основные переменные для Telegram бота:

- `TELEGRAM_BOT_TOKEN` - токен бота (обязательно)
- `BOT_API_KEY` - ключ для WebSocket аутентификации (обязательно)
- `DATABASE_URL` - подключение к PostgreSQL (наследуется)
- `PUBLIC_API_URL` - URL Public API для WebSocket (по умолчанию: http://public_api:8000)
- `LOG_LEVEL` - уровень логирования (INFO, DEBUG, WARNING, ERROR)
- `WS_RECONNECT_DELAY` - начальная задержка переподключения WebSocket (по умолчанию: 5 секунд)
- `WS_MAX_RECONNECT_DELAY` - максимальная задержка переподключения (по умолчанию: 300 секунд)
- `WS_HEARTBEAT_INTERVAL` - интервал heartbeat для WebSocket (по умолчанию: 30 секунд)

## Разработка

### Frontend разработка

```bash
# Установка зависимостей
cd frontend
pnpm install

# Запуск dev сервера с hot-reload
pnpm dev

# Проверка типов
pnpm run check

# Сборка production
pnpm run build
```

### Backend разработка

```bash
# Запуск тестов
docker-compose exec public_api python -m pytest tests/

# Создание новой миграции
docker-compose exec public_api alembic revision --autogenerate -m "Description"

# Применение миграций
docker-compose exec public_api alembic upgrade head

# Откат миграции
docker-compose exec public_api alembic downgrade -1
```

### Работа с базой данных

```bash
# Подключение к PostgreSQL
docker-compose exec postgres psql -U ssn_user -d ssn_users

# Проверка статуса PostgreSQL
docker-compose exec postgres pg_isready -U ssn_user

# Просмотр текущей версии миграции
docker-compose exec public_api alembic current
```

### Перезапуск сервисов

```bash
# Перезапуск конкретного сервиса
docker-compose restart [service_name]

# Пересборка и перезапуск (после изменений в коде)
docker-compose up -d --build [service_name]

# Полная остановка и перезапуск
docker-compose down
docker-compose up -d

# Остановка с удалением данных (осторожно!)
docker-compose down -v
```

## Мониторинг

### Логи

```bash
# Все сервисы
docker-compose logs -f

# Конкретный сервис
docker-compose logs -f [service_name]

# С фильтром
docker-compose logs public_api | grep ERROR
```

### Healthcheck

```bash
# Проверка здоровья сервисов
curl http://localhost/api/public/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

### Статус контейнеров

```bash
# Статус всех сервисов
docker-compose ps

# Использование ресурсов
docker stats
```

## Структура проекта

```
.
├── api/
│   ├── common/          # Общие модули (database, auth, models)
│   ├── public/          # Public API
│   ├── admin/           # Admin API
│   ├── enrichment/      # Enrichment API
│   └── lookup/          # Lookup API
├── bot/                 # Telegram Bot
├── frontend/            # Public Frontend (SvelteKit)
├── admin-frontend/      # Admin Frontend (SvelteKit)
├── lookup-frontend/     # Lookup Frontend
├── database/            # Database utilities
├── alembic/             # Database migrations
├── data/                # SQLite database files
├── docker-compose.yml   # Docker services configuration
├── Dockerfile.*         # Docker images for each service
├── nginx.conf           # Nginx configuration
└── .env                 # Environment variables (not in git)
```

## Безопасность

- Всегда используйте сильные пароли в production
- Сгенерируйте уникальные значения для `JWT_SECRET`, `BOT_API_KEY`, `WEBHOOK_SECRET`
- Ограничьте `ALLOWED_ORIGINS` только доверенными доменами
- Никогда не коммитьте `.env` файл в git
- Используйте HTTPS в production через Nginx
- Регулярно обновляйте зависимости

## Лицензия

[Укажите лицензию проекта]

## Контакты

[Укажите контактную информацию]
