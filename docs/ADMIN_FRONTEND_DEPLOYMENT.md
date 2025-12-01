# Admin Frontend Deployment Guide

## Пошаговая инструкция по развертыванию и тестированию

### Шаг 1: Подготовка окружения

Убедитесь, что все необходимые переменные окружения настроены в `.env`:

\`\`\`bash
# Скопируйте пример, если еще не сделали
cp .env.example .env

# Проверьте следующие переменные:
# - JWT_SECRET (минимум 32 символа)
# - DATABASE_URL
# - PUBLIC_ADMIN_API_URL=/api/admin
# - ADMIN_FRONTEND_PORT=3001
\`\`\`

### Шаг 2: Сборка и запуск всех сервисов

\`\`\`bash
# Остановить существующие контейнеры (если есть)
docker-compose down

# Пересобрать образы
docker-compose build

# Запустить все сервисы
docker-compose up -d

# Проверить статус
docker-compose ps
\`\`\`

Ожидаемый результат:
\`\`\`
NAME                           STATUS    PORTS
soft-admin_api-1               Up        0.0.0.0:8002->8002/tcp
soft-admin_frontend-1          Up        (healthy)
soft-enrichment_api-1          Up        0.0.0.0:8001->8001/tcp
soft-frontend-1                Up        (healthy)
soft-nginx-1                   Up        0.0.0.0:80->80/tcp
soft-postgres-1                Up        5432/tcp
soft-public_api-1              Up        0.0.0.0:8000->8000/tcp
\`\`\`

### Шаг 3: Инициализация базы данных

\`\`\`bash
# Дождитесь готовности PostgreSQL
docker-compose exec postgres pg_isready -U ssn_user

# Применить миграции (если еще не применены)
docker-compose exec public_api alembic upgrade head
\`\`\`

### Шаг 4: Создание admin пользователя

\`\`\`bash
# Запустить интерактивный скрипт создания admin пользователя
docker-compose exec public_api python scripts/create_admin.py
\`\`\`

Пример взаимодействия:
\`\`\`
=== Create Admin User ===

Enter admin username: admin
Enter admin email: admin@example.com
Enter admin password: ********
Confirm admin password: ********
Enter initial balance (default: 1000.00): 1000

==================================================
✓ Admin user created successfully!
==================================================
User ID:  abc123...
Username: admin
Email:    admin@example.com
Admin:    True
Balance:  $1000.00
Created:  2025-11-01...
==================================================

IMPORTANT: Please set up 2FA on first login to access admin features.
==================================================
\`\`\`

### Шаг 5: Первый вход в admin panel

1. **Откройте браузер** и перейдите на http://localhost/admin

2. **Введите credentials**:
   - Username: admin
   - Password: (пароль, который вы указали при создании)

3. **Настройка 2FA** (только при первом входе):
   - Откроется QR код
   - Откройте Google Authenticator или Authy на телефоне
   - Отсканируйте QR код
   - Сохраните backup codes в безопасном месте!
   - Введите 6-значный код из приложения для подтверждения

4. **Subsequent logins**:
   - Username + Password
   - TOTP код из Google Authenticator
   - Автоматический redirect на dashboard

### Шаг 6: Тестирование функций

#### Dashboard
1. Перейдите на `/admin/dashboard`
2. Проверьте:
   - ✅ User statistics карточки
   - ✅ Financial statistics
   - ✅ Transaction statistics
   - ✅ Product breakdown
   - ✅ User growth chart (line chart)
   - ✅ Transaction status chart (doughnut chart)
   - ✅ Refresh button обновляет данные

#### Coupons
1. Перейдите на `/admin/coupons`
2. **Создание купона**:
   - Click "Create Coupon"
   - Заполните форму (code optional, bonus_percent, max_uses)
   - Submit
   - ✅ Купон появился в таблице
3. **Редактирование**:
   - Click Edit icon
   - Измените bonus_percent или max_uses
   - Save
   - ✅ Изменения сохранены
4. **Toggle active/inactive**:
   - Click Toggle icon
   - ✅ Статус изменился
5. **Copy code**:
   - Click Copy icon
   - ✅ Code скопирован в clipboard
6. **Delete**:
   - Click Delete icon
   - Confirm
   - ✅ Купон удален

#### Users
1. Перейдите на `/admin/users`
2. **Просмотр таблицы**:
   - ✅ Видны все пользователи
   - ✅ Показаны username, email, balance, deposits, spending
   - ✅ Applied coupons в виде badges
3. **Поиск**:
   - Введите username или email в search bar
   - ✅ Таблица фильтруется
4. **Сортировка**:
   - Click на column header
   - ✅ Таблица сортируется
   - ✅ Индикатор направления сортировки
5. **Pagination**:
   - Если пользователей >50, появятся страницы
   - ✅ Навигация работает

#### Theme Toggle
1. Click на Moon/Sun icon в sidebar
2. ✅ Переключение между light и dark mode
3. ✅ Настройка сохраняется в localStorage

#### Logout
1. Click на user dropdown в sidebar
2. Select "Logout"
3. ✅ Redirect на login page
4. ✅ Token очищен из localStorage

### Шаг 7: Проверка логов

\`\`\`bash
# Admin frontend logs
docker-compose logs admin_frontend

# Admin API logs
docker-compose logs admin_api

# Nginx logs
docker-compose logs nginx

# Все логи в реальном времени
docker-compose logs -f admin_frontend admin_api nginx
\`\`\`

## Troubleshooting

### Проблема: Admin frontend не загружается

**Симптомы**: http://localhost/admin возвращает 502 Bad Gateway

**Решение**:
\`\`\`bash
# Проверить статус контейнера
docker-compose ps admin_frontend

# Если нездоров, посмотреть логи
docker-compose logs admin_frontend

# Пересобрать и перезапустить
docker-compose up -d --build admin_frontend
\`\`\`

### Проблема: UI компоненты не отображаются

**Симптомы**: Белый экран или ошибки компонентов в консоли браузера

**Решение**:
\`\`\`bash
# Проверить, что symlink создан
ls -la /root/soft/admin-frontend/src/lib/components/ui

# Пересобрать с копированием компонентов
docker-compose build admin_frontend
docker-compose up -d admin_frontend
\`\`\`

### Проблема: 2FA не настраивается

**Симптомы**: QR код не появляется или ошибка при верификации

**Решение**:
\`\`\`bash
# Проверить, что admin API работает
curl http://localhost:8002/health

# Проверить JWT_SECRET
docker-compose exec admin_api env | grep JWT_SECRET

# Проверить логи admin API
docker-compose logs admin_api | grep ERROR
\`\`\`

### Проблема: Charts не отображаются

**Симптомы**: Dashboard показывает карточки, но графики не рендерятся

**Решение**:
1. Открыть Browser DevTools (F12)
2. Проверить Console на ошибки
3. Проверить Network tab - загружается ли Chart.js
4. Если SSR ошибки, проверить svelte.config.js:
   \`\`\`javascript
   vite: {
     ssr: {
       noExternal: ['chart.js', 'chartjs-adapter-date-fns']
     }
   }
   \`\`\`

### Проблема: API requests failing (401/403)

**Симптомы**: После логина все API requests возвращают 401

**Решение**:
1. Проверить localStorage в Browser DevTools:
   - Application → Local Storage → http://localhost
   - Должен быть `admin_access_token`
2. Проверить CORS настройки в admin API
3. Проверить JWT_SECRET соответствие между public_api и admin_api

### Проблема: Nginx routing не работает

**Симптомы**: http://localhost/admin возвращает 404

**Решение**:
\`\`\`bash
# Проверить nginx конфигурацию
docker-compose exec nginx cat /etc/nginx/nginx.conf | grep -A 20 "location /admin"

# Reload nginx
docker-compose restart nginx

# Проверить upstream
docker-compose exec nginx ping admin_frontend
\`\`\`

## Production Deployment

### Security Checklist

1. ✅ **IP Whitelist**: Раскомментировать в nginx.conf
   \`\`\`nginx
   location /admin {
       allow 10.0.0.0/8;
       allow 172.16.0.0/12;
       allow 192.168.0.0/16;
       deny all;
       # ...
   }
   \`\`\`

2. ✅ **HTTPS**: Настроить SSL сертификаты
3. ✅ **Strong JWT_SECRET**: Минимум 64 символа, случайная строка
4. ✅ **Strong Admin Password**: Минимум 16 символов
5. ✅ **2FA Mandatory**: Убедиться, что все admin users настроили 2FA
6. ✅ **Rate Limiting**: Проверить настройки в nginx.conf
7. ✅ **Firewall**: Закрыть прямой доступ к портам 8000, 8001, 8002

### Environment Variables для Production

\`\`\`bash
# .env for production
NODE_ENV=production
JWT_SECRET=<strong-random-64-char-string>
DATABASE_URL=postgresql+asyncpg://user:strong_password@db_host:5432/db_name
ALLOWED_ORIGINS=https://yourdomain.com
\`\`\`

### Мониторинг

\`\`\`bash
# Health checks
curl http://localhost/health

# Metrics
docker stats admin_frontend admin_api

# Logs
docker-compose logs -f --tail=100 admin_frontend
\`\`\`

## Development Mode

Для локальной разработки без Docker:

\`\`\`bash
cd admin-frontend
pnpm install
pnpm dev  # http://localhost:5174
\`\`\`

Настройте vite.config.ts proxy для API:
\`\`\`typescript
server: {
  proxy: {
    '/api/admin': {
      target: 'http://localhost:8002',
      changeOrigin: true
    }
  }
}
\`\`\`

## Backup и Recovery

### Backup Admin Users

\`\`\`bash
# Экспорт admin пользователей
docker-compose exec postgres pg_dump -U ssn_user -d ssn_users -t users --data-only > admin_users_backup.sql
\`\`\`

### Restore

\`\`\`bash
# Импорт admin пользователей
docker-compose exec -T postgres psql -U ssn_user -d ssn_users < admin_users_backup.sql
\`\`\`

## Поддержка

При возникновении проблем:
1. Проверить логи: `docker-compose logs admin_frontend admin_api`
2. Проверить health checks: `docker-compose ps`
3. Проверить network connectivity: `docker-compose exec admin_frontend ping admin_api`
4. Обратиться к README.md для деталей
