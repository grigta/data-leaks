# Cloudflare CDN Integration

Руководство по настройке nginx для работы за Cloudflare CDN с получением реального IP клиента и security headers.

## Обзор

При работе за Cloudflare CDN все запросы приходят с IP-адресов Cloudflare, а не реальных клиентов. Это создает проблемы:

1. **Rate limiting** блокирует по IP Cloudflare, а не по IP клиента
2. **Логи** показывают IP Cloudflare вместо реального клиента
3. **Geo-blocking** и **IP-based access control** работают некорректно

Данная конфигурация решает эти проблемы через:
- Использование `ngx_http_realip_module` для извлечения реального IP
- Доверие к заголовку `CF-Connecting-IP` от Cloudflare
- Добавление строгих security headers

## Структура файлов

```
/root/soft/
├── nginx.conf                      # Основная конфигурация nginx
├── cloudflare-ips.conf             # IP ranges Cloudflare (генерируется автоматически)
├── scripts/
│   └── update-cloudflare-ips.sh    # Скрипт обновления IP ranges
└── docs/
    └── CLOUDFLARE_SETUP.md         # Эта документация
```

## Настройка Cloudflare Dashboard

### 1. SSL/TLS настройки

1. Перейдите в **SSL/TLS** > **Overview**
2. Выберите режим **Full (strict)** для полного шифрования
3. В **Edge Certificates** включите:
   - **Always Use HTTPS** - принудительный HTTPS
   - **Automatic HTTPS Rewrites** - автоматическая перезапись HTTP ссылок
   - **Minimum TLS Version** - установите TLS 1.2 или выше

### 2. Firewall настройки

1. Перейдите в **Security** > **WAF**
2. Рассмотрите включение **Managed Rules** для защиты от распространенных атак
3. В **Security** > **Bots** настройте защиту от ботов

### 3. Page Rules (опционально)

Создайте правила для кэширования статики:
```
URL: *example.com/static/*
Setting: Cache Level = Cache Everything
Edge Cache TTL: 1 month
```

## Настройка на сервере

### Первичная настройка

1. **Проверьте наличие файлов:**

```bash
ls -la /root/soft/nginx.conf
ls -la /root/soft/cloudflare-ips.conf
ls -la /root/soft/scripts/update-cloudflare-ips.sh
```

2. **Обновите IP ranges Cloudflare:**

```bash
/root/soft/scripts/update-cloudflare-ips.sh
```

3. **Перезапустите nginx:**

```bash
docker-compose exec nginx nginx -t
docker-compose exec nginx nginx -s reload
```

### Как это работает

**nginx.conf** содержит:

```nginx
# Подключение файла с IP ranges Cloudflare
include /etc/nginx/cloudflare-ips.conf;

# Использование заголовка CF-Connecting-IP для получения реального IP
real_ip_header CF-Connecting-IP;

# Рекурсивная обработка для правильного извлечения IP
real_ip_recursive on;
```

**cloudflare-ips.conf** содержит директивы `set_real_ip_from` для каждого IP range Cloudflare:

```nginx
set_real_ip_from 173.245.48.0/20;
set_real_ip_from 103.21.244.0/22;
# ... и другие ranges
```

После обработки этих директив:
- `$remote_addr` содержит реальный IP клиента
- Rate limiting работает по реальному IP
- Логи показывают реальный IP

## Автоматическое обновление IP ranges

Cloudflare периодически обновляет свои IP ranges. Скрипт `update-cloudflare-ips.sh` автоматически скачивает актуальные ranges.

### Ручной запуск

```bash
/root/soft/scripts/update-cloudflare-ips.sh
```

### Настройка cron

Для автоматического обновления добавьте в crontab:

```bash
crontab -e
```

Добавьте строку (ежедневно в 3:00):

```cron
0 3 * * * /root/soft/scripts/update-cloudflare-ips.sh >> /var/log/cloudflare-ips-update.log 2>&1
```

Или еженедельно (по воскресеньям в 3:00):

```cron
0 3 * * 0 /root/soft/scripts/update-cloudflare-ips.sh >> /var/log/cloudflare-ips-update.log 2>&1
```

### Что делает скрипт

1. Скачивает актуальные IPv4 ranges с `https://www.cloudflare.com/ips-v4`
2. Скачивает актуальные IPv6 ranges с `https://www.cloudflare.com/ips-v6`
3. Генерирует новый `cloudflare-ips.conf`
4. Создает backup старого файла
5. Тестирует конфигурацию nginx (`nginx -t`)
6. Если тест успешен - перезагружает nginx
7. При ошибке - откатывается к backup

## Проверка работоспособности

### 1. Проверка реального IP в логах

```bash
# Просмотр логов nginx
docker-compose logs nginx | tail -20

# Или напрямую
docker-compose exec nginx tail -f /var/log/nginx/access.log
```

Вы должны видеть реальные IP клиентов, а не IP Cloudflare.

### 2. Проверка security headers

```bash
curl -I https://your-domain.com
```

Ожидаемые заголовки:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'; ...
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

### 3. Проверка конфигурации nginx

```bash
docker-compose exec nginx nginx -t
```

Ожидаемый вывод:
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### 4. Проверка загрузки cloudflare-ips.conf

```bash
docker-compose exec nginx cat /etc/nginx/cloudflare-ips.conf | head -20
```

## Troubleshooting

### Ошибка "include directive failed"

**Проблема:** nginx не может найти `cloudflare-ips.conf`

**Решение:**
1. Проверьте наличие файла: `ls -la /root/soft/cloudflare-ips.conf`
2. Проверьте монтирование в docker-compose.yml:
   ```yaml
   volumes:
     - ./cloudflare-ips.conf:/etc/nginx/cloudflare-ips.conf:ro
   ```
3. Перезапустите nginx: `docker-compose restart nginx`

### Rate limiting блокирует всех

**Проблема:** Все клиенты блокируются rate limiting

**Решение:**
1. Проверьте, что `cloudflare-ips.conf` содержит актуальные IP
2. Проверьте, что `real_ip_header CF-Connecting-IP;` установлен
3. Обновите IP ranges: `/root/soft/scripts/update-cloudflare-ips.sh`

### Security headers не применяются

**Проблема:** curl не показывает security headers

**Решение:**
1. Убедитесь, что запрос идет через Cloudflare, а не напрямую
2. Проверьте, что нет конфликтующих `add_header` в location блоках
3. Используйте `always` флаг: `add_header X-Header value always;`

### Скрипт обновления не работает

**Проблема:** `update-cloudflare-ips.sh` завершается с ошибкой

**Решение:**
1. Проверьте права: `chmod +x /root/soft/scripts/update-cloudflare-ips.sh`
2. Проверьте доступ к Cloudflare API:
   ```bash
   curl -sf https://www.cloudflare.com/ips-v4
   ```
3. Проверьте логи: `cat /var/log/cloudflare-ips-update.log`

### Откат к предыдущей конфигурации

Если что-то пошло не так:

```bash
# Восстановить backup
cp /root/soft/cloudflare-ips.conf.backup /root/soft/cloudflare-ips.conf

# Проверить конфигурацию
docker-compose exec nginx nginx -t

# Перезагрузить nginx
docker-compose exec nginx nginx -s reload
```

## Security Best Practices

### 1. Content Security Policy (CSP)

Текущая CSP настроена с `unsafe-inline` и `unsafe-eval` для совместимости с Vite/SvelteKit.

Для production рекомендуется ужесточить:

```nginx
# Строгий CSP (требует тестирования)
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https:; font-src 'self'; connect-src 'self'; frame-ancestors 'none';" always;
```

### 2. HSTS Preload

Для регистрации домена в HSTS preload list:

1. Убедитесь, что заголовок содержит `preload`:
   ```
   Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
   ```

2. Подайте заявку на https://hstspreload.org

### 3. Мониторинг

Настройте мониторинг security headers через:
- https://securityheaders.com
- https://observatory.mozilla.org

## Дополнительные ресурсы

- [Cloudflare IP Ranges](https://www.cloudflare.com/ips/)
- [nginx real_ip module](https://nginx.org/en/docs/http/ngx_http_realip_module.html)
- [Cloudflare SSL/TLS docs](https://developers.cloudflare.com/ssl/)
- [Mozilla Security Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers)
