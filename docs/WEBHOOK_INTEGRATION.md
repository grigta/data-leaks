# Webhook Integration Guide

## Overview

Enrichment API предоставляет webhook endpoint для интеграции с внешними сервисами, позволяя им отправлять обновления данных SSN в реальном времени.

## Аутентификация

Webhook endpoint поддерживает два уровня безопасности:

1. **API Key** (обязательно): Передается в заголовке `X-API-Key`
2. **Signature** (рекомендуется): HMAC-SHA256 подпись в заголовке `X-Webhook-Signature`

## Endpoint

**URL:** `POST /enrichment/webhook`
**Content-Type:** `application/json`

## Верификация подписи

### Зачем использовать подписи?

- Предотвращает неавторизованные webhook запросы
- Обеспечивает целостность данных
- Защищает от replay атак

### Как генерировать подпись

1. Получите webhook secret от администратора API
2. Вычислите HMAC-SHA256 от сырого тела запроса
3. Конвертируйте в hexadecimal строку
4. Добавьте в заголовок `X-Webhook-Signature`

### Примеры реализации

#### Python

```python
import hmac
import hashlib
import json
import requests

webhook_secret = "your_webhook_secret"
api_key = "your_api_key"
url = "http://localhost:8001/enrichment/webhook"

payload = {
    "operation": "add",
    "table_name": "ssn_1",
    "data": {
        "ssn": "123-45-6789",
        "firstname": "John",
        "lastname": "Doe",
        "email": "john@example.com"
    }
}

# Сериализуем payload
body = json.dumps(payload)

# Вычисляем подпись
signature = hmac.new(
    webhook_secret.encode(),
    body.encode(),
    hashlib.sha256
).hexdigest()

# Отправляем запрос
response = requests.post(
    url,
    headers={
        "X-API-Key": api_key,
        "X-Webhook-Signature": signature,
        "Content-Type": "application/json"
    },
    data=body
)

print(response.json())
```

#### Node.js

```javascript
const crypto = require('crypto');
const axios = require('axios');

const webhookSecret = 'your_webhook_secret';
const apiKey = 'your_api_key';
const url = 'http://localhost:8001/enrichment/webhook';

const payload = {
  operation: 'add',
  table_name: 'ssn_1',
  data: {
    ssn: '123-45-6789',
    firstname: 'John',
    lastname: 'Doe',
    email: 'john@example.com'
  }
};

// Сериализуем payload
const body = JSON.stringify(payload);

// Вычисляем подпись
const signature = crypto
  .createHmac('sha256', webhookSecret)
  .update(body)
  .digest('hex');

// Отправляем запрос
axios.post(url, payload, {
  headers: {
    'X-API-Key': apiKey,
    'X-Webhook-Signature': signature,
    'Content-Type': 'application/json'
  }
})
.then(response => console.log(response.data))
.catch(error => console.error(error));
```

#### PHP

```php
<?php
$webhookSecret = 'your_webhook_secret';
$apiKey = 'your_api_key';
$url = 'http://localhost:8001/enrichment/webhook';

$payload = [
    'operation' => 'add',
    'table_name' => 'ssn_1',
    'data' => [
        'ssn' => '123-45-6789',
        'firstname' => 'John',
        'lastname' => 'Doe',
        'email' => 'john@example.com'
    ]
];

// Сериализуем payload
$body = json_encode($payload);

// Вычисляем подпись
$signature = hash_hmac('sha256', $body, $webhookSecret);

// Отправляем запрос
$ch = curl_init($url);
curl_setopt($ch, CURLOPT_POST, 1);
curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    'X-API-Key: ' . $apiKey,
    'X-Webhook-Signature: ' . $signature,
    'Content-Type: application/json'
]);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);

$response = curl_exec($ch);
curl_close($ch);

print_r(json_decode($response, true));
?>
```

#### cURL (Bash)

```bash
# Подготовка payload
PAYLOAD='{"operation":"add","table_name":"ssn_1","data":{"ssn":"123-45-6789","firstname":"John","lastname":"Doe"}}'

# Вычисление подписи
SECRET="your_webhook_secret"
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)

# Отправка запроса
curl -X POST http://localhost:8001/enrichment/webhook \
  -H "X-API-Key: your_api_key" \
  -H "X-Webhook-Signature: $SIGNATURE" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD"
```

## Форматы payload

### Generic формат (рекомендуется)

Соответствует внутренней структуре данных, не требует трансформации:

```json
{
  "operation": "add",
  "table_name": "ssn_1",
  "data": {
    "ssn": "123-45-6789",
    "firstname": "John",
    "lastname": "Doe",
    "middlename": "M",
    "address": "123 Main St",
    "city": "Springfield",
    "state": "IL",
    "zip": "62701",
    "phone": "555-1234",
    "dob": "1990-01-15",
    "email": "john@example.com"
  }
}
```

### Custom формат

Установите заголовок `X-Webhook-Source` с идентификатором вашего сервиса. Свяжитесь с администратором API для настройки маппинга полей.

**Пример для source="service_a":**

```json
{
  "operation": "add",
  "table_name": "ssn_1",
  "data": {
    "social_security_number": "123456789",
    "first_name": "John",
    "last_name": "Doe",
    "email_address": "john@example.com",
    "phone_number": "555-1234"
  }
}
```

Поля автоматически трансформируются:
- `social_security_number` → `ssn`
- `first_name` → `firstname`
- `last_name` → `lastname`
- `email_address` → `email`
- `phone_number` → `phone`

## Операции

### Добавление/обновление записи (UPSERT)

```json
{
  "operation": "add",
  "table_name": "ssn_1",
  "data": {
    "ssn": "123-45-6789",
    "firstname": "John",
    "lastname": "Doe",
    "email": "john@example.com"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Operation 'add' completed successfully",
  "details": {
    "success": true,
    "ssn": "123-45-6789",
    "message": "Record inserted successfully"
  }
}
```

### Обновление существующей записи

```json
{
  "operation": "update",
  "table_name": "ssn_1",
  "data": {
    "ssn": "123-45-6789",
    "email": "newemail@example.com",
    "phone": "555-9999"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Operation 'update' completed successfully",
  "details": {
    "success": true,
    "updated": true,
    "ssn": "123-45-6789"
  }
}
```

### Удаление записи

```json
{
  "operation": "delete",
  "table_name": "ssn_1",
  "data": {
    "ssn": "123-45-6789"
  }
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Operation 'delete' completed successfully",
  "details": {
    "success": true,
    "deleted": true,
    "ssn": "123-45-6789"
  }
}
```

### Массовое добавление

```json
{
  "operation": "bulk_add",
  "table_name": "ssn_1",
  "data": [
    {
      "ssn": "123-45-6789",
      "firstname": "John",
      "lastname": "Doe",
      "email": "john@example.com"
    },
    {
      "ssn": "987-65-4321",
      "firstname": "Jane",
      "lastname": "Smith",
      "email": "jane@example.com"
    }
  ]
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Operation 'bulk_add' completed successfully",
  "details": {
    "total": 2,
    "successful": 2,
    "failed": 0,
    "failed_records": []
  }
}
```

## Формат ответа

### Успешный ответ

```json
{
  "status": "success",
  "message": "Operation 'add' completed successfully",
  "details": {
    "success": true,
    "ssn": "123-45-6789",
    "message": "Record inserted successfully"
  }
}
```

### Ответ с ошибкой

```json
{
  "status": "error",
  "message": "Validation error: Invalid SSN format",
  "details": {
    "error": "SSN must be 9 digits"
  }
}
```

**Важно:** Webhook endpoint всегда возвращает 200 OK, даже при ошибках. Проверяйте поле `status` в ответе.

## Обработка ошибок

### Best practices на стороне клиента

1. **Всегда проверяйте поле `status` в ответе**
2. **Логируйте все webhook вызовы и ответы**
3. **Реализуйте retry логику с exponential backoff для сетевых ошибок**
4. **НЕ повторяйте запросы при ошибках валидации (status: "error")**
5. **Мониторьте success rate webhook запросов**

### Распространенные ошибки

| Ошибка | Причина | Решение |
|--------|---------|---------|
| 403 Forbidden | Неверный API key | Проверьте `X-API-Key` header |
| 401 Unauthorized | Неверная подпись | Проверьте вычисление HMAC-SHA256 |
| 200 OK + status: "error" | Неверный table_name | Используйте 'ssn_1' или 'ssn_2' |
| 200 OK + status: "error" | Неверный формат SSN | SSN должен быть 9 цифр |
| 200 OK + status: "error" | Отсутствуют обязательные поля | Проверьте наличие SSN |
| Network timeout | Сервер недоступен | Реализуйте retry с backoff |

### Пример retry логики (Python)

```python
import time
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

def send_webhook_with_retry(url, headers, payload, max_retries=3):
    """Отправка webhook с автоматическим retry."""

    session = requests.Session()

    # Настройка retry стратегии
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=2,  # 2, 4, 8 секунд
        status_forcelist=[500, 502, 503, 504],  # Retry только на server errors
        method_whitelist=["POST"]
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    try:
        response = session.post(url, headers=headers, json=payload, timeout=10)
        result = response.json()

        # Проверяем статус в ответе
        if result.get('status') == 'success':
            return True, result
        else:
            # Не повторяем при ошибках валидации
            return False, result

    except requests.exceptions.RequestException as e:
        return False, {"error": str(e)}
    finally:
        session.close()
```

## Тестирование

### Тест без верификации подписи

```bash
curl -X POST http://localhost:8001/enrichment/webhook \
  -H "X-API-Key: test_key" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "add",
    "table_name": "ssn_1",
    "data": {
      "ssn": "123-45-6789",
      "firstname": "Test",
      "lastname": "User"
    }
  }'
```

### Тест с верификацией подписи

```bash
# Генерируем подпись
SECRET="your_webhook_secret"
PAYLOAD='{"operation":"add","table_name":"ssn_1","data":{"ssn":"123-45-6789","firstname":"Test","lastname":"User"}}'
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)

# Отправляем запрос
curl -X POST http://localhost:8001/enrichment/webhook \
  -H "X-API-Key: test_key" \
  -H "X-Webhook-Signature: $SIGNATURE" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD"
```

### Тест с custom source

```bash
curl -X POST http://localhost:8001/enrichment/webhook \
  -H "X-API-Key: test_key" \
  -H "X-Webhook-Source: service_a" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "add",
    "table_name": "ssn_1",
    "data": {
      "social_security_number": "123456789",
      "first_name": "John",
      "last_name": "Doe"
    }
  }'
```

## Безопасность

### Рекомендации для production

1. ✅ **Всегда используйте HTTPS**
2. ✅ **Включите верификацию подписи** (установите `WEBHOOK_SECRET`)
3. ✅ **Регулярно ротируйте API keys и webhook secrets**
4. ✅ **Мониторьте подозрительную активность** (необычные паттерны операций, высокий error rate)
5. ✅ **Используйте rate limiting** (при необходимости, свяжитесь с администратором API)
6. ✅ **Валидируйте данные на своей стороне** перед отправкой в webhook
7. ✅ **Используйте отдельные API keys** для webhook интеграции (отличные от других API доступов)

### Генерация безопасных secrets

```bash
# Генерация webhook secret (64 символа)
python -c 'import secrets; print(secrets.token_hex(32))'

# Или используя openssl
openssl rand -hex 32
```

## Мониторинг и отладка

### Логирование

Все webhook запросы логируются на стороне сервера с следующей информацией:
- Timestamp
- Source (из заголовка `X-Webhook-Source`)
- Operation type
- Table name
- Signature verification status
- Operation result
- Замаскированные SSN и email (первые 3 символа + **)

### Отладка проблем

**Проблема: 403 Forbidden**
- Проверьте, что API key корректный
- Убедитесь, что API key находится в `ENRICHMENT_API_KEYS` в .env файле

**Проблема: 401 Unauthorized**
- Проверьте корректность вычисления подписи
- Убедитесь, что webhook secret совпадает с конфигурацией сервера
- Проверьте, что используется raw request body для подписи (не сериализованный дважды)

**Проблема: 200 OK но status: "error"**
- Проверьте response message для деталей
- Убедитесь, что формат payload соответствует ожидаемому
- Валидируйте SSN формат (9 цифр, опционально с дефисами)
- Проверьте, что table_name либо 'ssn_1', либо 'ssn_2'

**Проблема: Network timeout**
- Проверьте, что сервер запущен и доступен
- Проверьте firewall правила
- Реализуйте retry логику с exponential backoff

## Поддержка

Для получения поддержки по webhook интеграции:

1. Проверьте эту документацию
2. Просмотрите логи API для деталей ошибок
3. Свяжитесь с администратором API со следующей информацией:
   - Timestamp webhook вызова
   - Request payload (с замаскированными чувствительными данными)
   - Полученный response
   - Сообщение об ошибке

## Примеры интеграций

### Интеграция с внешним CRM

```python
import hmac
import hashlib
import json
import requests
from datetime import datetime

class WebhookClient:
    """Клиент для отправки данных в Enrichment API webhook."""

    def __init__(self, api_url, api_key, webhook_secret):
        self.api_url = api_url
        self.api_key = api_key
        self.webhook_secret = webhook_secret

    def _compute_signature(self, payload):
        """Вычисление HMAC-SHA256 подписи."""
        body = json.dumps(payload)
        return hmac.new(
            self.webhook_secret.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()

    def send_webhook(self, operation, table_name, data):
        """Отправка webhook запроса."""
        payload = {
            "operation": operation,
            "table_name": table_name,
            "data": data
        }

        signature = self._compute_signature(payload)

        headers = {
            "X-API-Key": self.api_key,
            "X-Webhook-Signature": signature,
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                f"{self.api_url}/enrichment/webhook",
                headers=headers,
                json=payload,
                timeout=10
            )

            result = response.json()

            if result.get('status') == 'success':
                print(f"✓ Webhook успешно отправлен: {operation}")
                return True, result
            else:
                print(f"✗ Webhook ошибка: {result.get('message')}")
                return False, result

        except Exception as e:
            print(f"✗ Ошибка сети: {str(e)}")
            return False, {"error": str(e)}

    def sync_customer(self, customer_data):
        """Синхронизация данных клиента."""
        # Трансформация данных из CRM формата в SSN формат
        ssn_data = {
            "ssn": customer_data["social_security"],
            "firstname": customer_data["first_name"],
            "lastname": customer_data["last_name"],
            "email": customer_data["email"],
            "phone": customer_data["phone"],
            "address": customer_data["street"],
            "city": customer_data["city"],
            "state": customer_data["state"],
            "zip": customer_data["postal_code"],
            "dob": customer_data["date_of_birth"]
        }

        return self.send_webhook("add", "ssn_1", ssn_data)

# Использование
client = WebhookClient(
    api_url="http://localhost:8001",
    api_key="your_api_key",
    webhook_secret="your_webhook_secret"
)

# Синхронизация клиента из CRM
customer = {
    "social_security": "123-45-6789",
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone": "555-1234",
    "street": "123 Main St",
    "city": "Springfield",
    "state": "IL",
    "postal_code": "62701",
    "date_of_birth": "1990-01-15"
}

success, result = client.sync_customer(customer)
```

## Лимиты и производительность

- **Rate limit:** Не установлен по умолчанию (свяжитесь с администратором для настройки)
- **Максимальный размер payload:** 10 MB
- **Timeout:** 30 секунд
- **Максимальное количество записей в bulk_add:** 1000

## Changelog

### v1.0.0 (2025-10-27)
- Начальный релиз webhook endpoint
- Поддержка операций: add, update, delete, bulk_add
- HMAC-SHA256 signature verification
- Гибкая трансформация payload
- Comprehensive logging с маскированием чувствительных данных
