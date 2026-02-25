# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow Orchestration

### 1. Plan Node Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately – don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One tack per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes – don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests – then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management
1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimat Impact**: Changes should only touch what's necessary. Avoid introducing bugs.


## Язык общения

- Всегда отвечать на русском языке
- Не делать того, о чем не просят

## Архитектура проекта

Монорепозиторий с тремя доменами, общими модулями и Docker-оркестрацией.

### Домены

| Домен | Назначение | Frontend | API | Порт API |
|-------|-----------|----------|-----|----------|
| huntrssn.cc | Основной сайт | `huntrssn.cc/frontend/` | `huntrssn.cc/api/public/` | 8000 |
| infinitymoneyyy.xyz | Админка | `infinitymoneyyy.xyz/admin-frontend/` | `infinitymoneyyy.xyz/api/admin/` | 8002 |
| qwertyworkforever.top | Портал воркеров | `qwertyworkforever.top/worker-frontend/` | `qwertyworkforever.top/api/` | 8003 |

### Общий код (shared/)

Каждый домен имеет симлинки `api/common -> shared/api/common`, `database -> shared/database`, `alembic -> shared/alembic`.

- `shared/api/common/` — Python модули: auth (JWT), models (PostgreSQL/SQLite), database connections, pricing, external API clients (SearchBug, Whitepages, DaisySMS)
- `shared/database/` — поисковые движки (SQLite, ClickHouse), bloom/search key генераторы
- `shared/alembic/` — PostgreSQL миграции (Alembic)

### Базы данных

- **PostgreSQL** — пользователи, заказы, сессии, тикеты, подписки (`shared/api/common/models_postgres.py`, SQLAlchemy 2.0 async)
- **ClickHouse** — SSN записи ~135M строк (`shared/database/clickhouse_*.py`), MergeTree с bloom-индексами
- **SQLite** — SSN записи legacy (`shared/api/common/models_sqlite.py`)
- **Redis** — distributed rate limiting, WebSocket pub/sub

### Двухуровневый поиск SSN (ClickHouse)

1. **Level 1 — Bloom keys** (`bloom_key_generator.py`): фильтрация по `bloom_key_address` формата `{fn_letter}:{ln_letter}:{addr_number}:{street_word}:{state}`. Lookup-таблицы `ssn_bloom_address_lookup` / `ssn_bloom_phone_lookup` для быстрого доступа.
2. **Level 2 — Search keys** (`search_key_generator.py`): 16 методов matching (8 с полным именем FN + 8 с первой буквой FN1). Дедупликация по SSN происходит **после** Level 2.

### Nginx routing

- `huntrssn.cc`: `/api/public/` → public_api:8000, `/` → frontend:3000
- `infinitymoneyyy.xyz`: `/api/admin/` → admin_api:8002, `/` → admin_frontend:3000
- `qwertyworkforever.top`: `/api/worker/` → worker_api:8003, `/` → worker_frontend:3000
- Cloudflare real IP через `CF-Connecting-IP`. Rate limit: 10r/s.

## Стек технологий

**Backend:** FastAPI (async) + Uvicorn, SQLAlchemy 2.0 (async), JWT auth (python-jose), Python 3.11

**Frontend:** Svelte 5 (Runes API: `$state`, `$derived`, `$effect`, `$props`), SvelteKit 2, TypeScript, Tailwind CSS 3.4, Vite. UI: bits-ui, flowbite-svelte, @lucide/svelte, svelte-sonner, mode-watcher (dark/light), sveltekit-i18n (en/ru).

**Telegram бот:** aiogram 3.x (`bot/`)

## Команды для разработки

**ВАЖНО:** Использовать `docker compose` (без дефиса), не `docker-compose`.

### Docker

```bash
docker compose up -d                              # Запустить все сервисы
docker compose ps                                 # Статус
docker compose logs -f public_api                  # Логи конкретного сервиса
docker compose up -d --build public_api admin_api  # Пересобрать backend
docker compose up -d --build frontend              # Пересобрать frontend
docker compose restart nginx                       # Перезапуск nginx
docker compose exec public_api bash                # Войти в контейнер
```

### База данных

```bash
docker compose exec public_api alembic upgrade head                            # Применить миграции
docker compose exec public_api alembic revision --autogenerate -m "Description" # Новая миграция
docker compose exec public_api alembic downgrade -1                             # Откат
docker compose exec postgres psql -U ssn_user -d ssn_users                     # PostgreSQL shell
docker compose exec clickhouse clickhouse-client                               # ClickHouse shell
```

### Frontend

```bash
cd huntrssn.cc/frontend && pnpm install && pnpm dev           # Порт 5173
cd infinitymoneyyy.xyz/admin-frontend && pnpm install && pnpm dev  # Порт 5174
pnpm run check   # Проверка типов (svelte-check)
pnpm run build    # Production сборка
```

### Тестирование

```bash
# Python тесты (unittest, из корня проекта)
python3 -m unittest tests.test_search_engine -v                    # Все тесты поиска (47 тестов)
python3 -m unittest tests.test_bloom_key_generator -v              # Bloom key тесты
python3 -m unittest tests.test_search_key_generator -v             # Search key тесты
python3 -m unittest tests.test_search_engine.TestSearchBySSN -v    # Конкретный класс
python3 -m unittest discover -s tests -p "test_*.py" -v            # Все тесты

# Frontend тесты
cd huntrssn.cc/frontend && pnpm test    # Vitest

# Безопасность
docker compose exec public_api python -m pytest tests/test_sql_injection.py -v
```

### Линтинг

```bash
ruff check .                    # Python linting (ruff.toml: line-length=120, py311)
cd huntrssn.cc/frontend && pnpm lint   # Frontend (prettier + eslint)
```

## Переменные окружения

Копировать `.env.example` → `.env`. Ключевые переменные:

```bash
DATABASE_URL=postgresql+asyncpg://ssn_user:password@postgres:5432/ssn_users
JWT_SECRET=...
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PORT=9000
SEARCH_ENGINE_TYPE=sqlite          # sqlite/clickhouse/hybrid
ENABLE_CLICKHOUSE_WRITES=false
ALLOWED_ORIGINS=https://huntrssn.cc,https://www.huntrssn.cc
ALLOWED_ORIGINS_ADMIN=https://infinitymoneyyy.xyz,https://www.infinitymoneyyy.xyz
```

## Документация API

- Public API: http://huntrssn.cc/api/public/docs
- Admin API: http://infinitymoneyyy.xyz/api/admin/docs
