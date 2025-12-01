# Whitepages API Documentation

## Обзор

Whitepages API предоставляет доступ к базе данных людей и бизнесов для поиска контактной информации, верификации идентификационных данных и обогащения данных.

**Основные возможности:**
- Поиск людей по имени и адресу
- Обратный поиск по телефону (Reverse Phone Lookup)
- Обратный поиск по адресу (Reverse Address Lookup)
- Проверка идентификационных данных (Identity Check)
- Обогащение данных о людях и бизнесах

**Официальная документация:** [https://api.whitepages.com/docs](https://api.whitepages.com/docs)

## Аутентификация

Whitepages API использует API ключи для аутентификации запросов.

### Получение API ключа

1. Зарегистрируйтесь на [Whitepages Pro](https://www.whitepages.com/pro-api)
2. Создайте новый API ключ в панели управления
3. Используйте ключ в параметре `api_key` для всех запросов

### Пример аутентификации

```bash
curl "https://proapi.whitepages.com/3.0/person?name=John+Doe&api_key=YOUR_API_KEY"
```

## Base URL

```
https://proapi.whitepages.com/3.0/
```

## Основные Endpoints

### 1. Person Lookup (Поиск людей)

**Endpoint:** `GET /person`

Поиск людей по имени, адресу, телефону или другим параметрам.

**Параметры запроса:**

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `api_key` | string | Да | Ваш API ключ |
| `name` | string | Нет* | Имя и фамилия для поиска |
| `address.street_line_1` | string | Нет* | Адрес (улица и дом) |
| `address.city` | string | Нет* | Город |
| `address.state_code` | string | Нет* | Код штата (2 буквы) |
| `address.postal_code` | string | Нет* | Почтовый индекс |
| `phone` | string | Нет* | Номер телефона |

*Требуется хотя бы один параметр для поиска

**Важное примечание о параметрах поиска:**
- **Email НЕ поддерживается** как параметр поиска в Person Lookup endpoint
- Допустимые комбинации для поиска:
  - **Имя + Телефон**: Поиск по имени и номеру телефона
  - **Имя + Адрес**: Поиск по имени и компонентам адреса (street, city, state, postal_code)
  - **Только телефон**: Обратный поиск по телефону (используйте endpoint `/phone` для лучших результатов)
- Для верификации email адреса используйте endpoint **Identity Check** вместо Person Lookup

**Пример запроса:**

```bash
curl "https://proapi.whitepages.com/3.0/person?name=John+Doe&address.city=Seattle&address.state_code=WA&api_key=YOUR_API_KEY"
```

**Пример ответа:**

```json
{
  "results": [
    {
      "id": "Person.12345678-abcd-1234-efgh-123456789012.Durable",
      "name": "John Doe",
      "age_range": "50-54",
      "gender": "Male",
      "locations": [
        {
          "id": "Location.12345678-abcd-1234-efgh-123456789012.Durable",
          "type": "Address",
          "standard_address_line1": "123 Main St",
          "standard_address_line2": "Seattle, WA 98101",
          "city": "Seattle",
          "state_code": "WA",
          "postal_code": "98101",
          "zip4": "1234",
          "country_code": "US",
          "is_commercial": false,
          "is_active": true
        }
      ],
      "phones": [
        {
          "id": "Phone.12345678-abcd-1234-efgh-123456789012.Durable",
          "phone_number": "+12065551234",
          "line_type": "Mobile",
          "carrier": "T-Mobile USA, Inc.",
          "is_prepaid": false,
          "is_active": true
        }
      ],
      "associated_people": [
        {
          "id": "Person.87654321-dcba-4321-hgfe-210987654321.Durable",
          "name": "Jane Doe",
          "relation": "Spouse"
        }
      ]
    }
  ],
  "messages": []
}
```

### 2. Reverse Phone Lookup (Обратный поиск по телефону)

**Endpoint:** `GET /phone`

Получение информации о владельце номера телефона.

**Параметры запроса:**

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `api_key` | string | Да | Ваш API ключ |
| `phone` | string | Да | Номер телефона (10 цифр или E.164 формат) |

**Пример запроса:**

```bash
curl "https://proapi.whitepages.com/3.0/phone?phone=2065551234&api_key=YOUR_API_KEY"
```

**Пример ответа:**

```json
{
  "results": [
    {
      "id": "Phone.12345678-abcd-1234-efgh-123456789012.Durable",
      "phone_number": "+12065551234",
      "line_type": "Mobile",
      "carrier": "T-Mobile USA, Inc.",
      "is_prepaid": false,
      "is_active": true,
      "country_calling_code": "1",
      "belongs_to": [
        {
          "id": "Person.12345678-abcd-1234-efgh-123456789012.Durable",
          "name": "John Doe",
          "age_range": "50-54",
          "gender": "Male",
          "type": "Person"
        }
      ],
      "associated_locations": [
        {
          "id": "Location.12345678-abcd-1234-efgh-123456789012.Durable",
          "city": "Seattle",
          "state_code": "WA",
          "postal_code": "98101"
        }
      ],
      "is_valid": true,
      "is_connected": true,
      "reputation": {
        "spam_score": 1,
        "level": "low"
      }
    }
  ],
  "messages": []
}
```

### 3. Reverse Address Lookup (Обратный поиск по адресу)

**Endpoint:** `GET /location`

Получение информации о жильцах и собственности по адресу.

**Параметры запроса:**

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `api_key` | string | Да | Ваш API ключ |
| `street_line_1` | string | Да | Адрес (улица и дом) |
| `city` | string | Нет* | Город |
| `state_code` | string | Нет* | Код штата |
| `postal_code` | string | Нет* | Почтовый индекс |

*Рекомендуется указать хотя бы один дополнительный параметр

**Пример запроса:**

```bash
curl "https://proapi.whitepages.com/3.0/location?street_line_1=123+Main+St&city=Seattle&state_code=WA&api_key=YOUR_API_KEY"
```

**Пример ответа:**

```json
{
  "results": [
    {
      "id": "Location.12345678-abcd-1234-efgh-123456789012.Durable",
      "type": "Address",
      "standard_address_line1": "123 Main St",
      "standard_address_line2": "Seattle, WA 98101",
      "city": "Seattle",
      "state_code": "WA",
      "postal_code": "98101",
      "zip4": "1234",
      "country_code": "US",
      "lat_long": {
        "latitude": 47.6062,
        "longitude": -122.3321,
        "accuracy": "RoofTop"
      },
      "is_commercial": false,
      "is_active": true,
      "current_residents": [
        {
          "id": "Person.12345678-abcd-1234-efgh-123456789012.Durable",
          "name": "John Doe",
          "age_range": "50-54"
        }
      ],
      "historical_residents": [
        {
          "id": "Person.87654321-dcba-4321-hgfe-210987654321.Durable",
          "name": "Previous Resident",
          "age_range": "40-44"
        }
      ]
    }
  ],
  "messages": []
}
```

### 4. Get Person by ID (Получение данных о человеке по ID)

**Endpoint:** `GET /person/{person_id}`

Получение полной информации о человеке по его Whitepages ID.

**Path параметры:**

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `person_id` | string | Да | Whitepages Person ID |

**Query параметры:**

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `api_key` | string | Да | Ваш API ключ |

**Пример запроса:**

```bash
curl "https://proapi.whitepages.com/3.0/person/Person.12345678-abcd-1234-efgh-123456789012.Durable?api_key=YOUR_API_KEY"
```

### 5. Identity Check (Проверка идентификации)

**Endpoint:** `POST /identity_check`

Верификация комбинации идентификационных данных (имя, адрес, телефон, email, IP).

**Параметры запроса (JSON body):**

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `api_key` | string | Да | Ваш API ключ |
| `name` | object | Нет | Объект с `first_name` и `last_name` |
| `phone` | string | Нет | Номер телефона |
| `email_address` | string | Нет | Email адрес |
| `address` | object | Нет | Объект адреса |
| `ip_address` | string | Нет | IP адрес |

**Пример запроса:**

```bash
curl -X POST "https://proapi.whitepages.com/3.0/identity_check?api_key=YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": {
      "first_name": "John",
      "last_name": "Doe"
    },
    "phone": "2065551234",
    "email_address": "john.doe@example.com",
    "address": {
      "street_line_1": "123 Main St",
      "city": "Seattle",
      "state_code": "WA",
      "postal_code": "98101"
    },
    "ip_address": "8.8.8.8"
  }'
```

**Пример ответа:**

```json
{
  "results": {
    "name_to_phone": "Match",
    "name_to_address": "Match",
    "phone_to_address": "Match",
    "email_to_name": "No Match",
    "ip_to_address": "City Match",
    "identity_score": 85,
    "warnings": []
  }
}
```

## Типы данных

### Line Types (Типы телефонных линий)

- `Mobile` - Мобильный телефон
- `Landline` - Стационарный телефон
- `FixedVOIP` - Фиксированный VoIP
- `NonFixedVOIP` - Нефиксированный VoIP
- `Premium` - Премиум номер
- `TollFree` - Бесплатный номер
- `Other` - Другое

### Location Types (Типы локаций)

- `Address` - Физический адрес
- `Neighborhood` - Район
- `City` - Город
- `PostalCode` - Почтовый индекс
- `StateOrProvince` - Штат или провинция
- `Country` - Страна

## Обработка ошибок

### HTTP коды ответов

| Код | Описание |
|-----|----------|
| 200 | Успешный запрос |
| 400 | Неверные параметры запроса |
| 401 | Ошибка аутентификации (неверный API ключ) |
| 403 | Доступ запрещен |
| 404 | Данные не найдены |
| 429 | Превышен лимит запросов |
| 500 | Внутренняя ошибка сервера |

### Пример ответа с ошибкой

```json
{
  "error": {
    "code": "INVALID_API_KEY",
    "message": "The API key provided is invalid"
  }
}
```

## Rate Limiting (Ограничения)

- Лимиты зависят от вашего плана подписки
- Заголовки ответа содержат информацию о лимитах:
  - `X-RateLimit-Limit` - Общий лимит запросов
  - `X-RateLimit-Remaining` - Оставшиеся запросы
  - `X-RateLimit-Reset` - Время сброса лимита (Unix timestamp)

## Примеры использования

### Python

```python
import requests

API_KEY = "your_api_key_here"
BASE_URL = "https://proapi.whitepages.com/3.0"

def reverse_phone_lookup(phone_number):
    """Обратный поиск по телефону"""
    url = f"{BASE_URL}/phone"
    params = {
        "api_key": API_KEY,
        "phone": phone_number
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}")
        return None

def person_lookup(name, city=None, state=None):
    """Поиск людей по имени и локации"""
    url = f"{BASE_URL}/person"
    params = {
        "api_key": API_KEY,
        "name": name
    }

    if city:
        params["address.city"] = city
    if state:
        params["address.state_code"] = state

    response = requests.get(url, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}")
        return None

# Примеры использования
if __name__ == "__main__":
    # Обратный поиск по телефону
    phone_data = reverse_phone_lookup("2065551234")
    if phone_data:
        print("Phone lookup result:", phone_data)

    # Поиск людей
    person_data = person_lookup("John Doe", city="Seattle", state="WA")
    if person_data:
        print("Person lookup result:", person_data)
```

### JavaScript/Node.js

```javascript
const axios = require('axios');

const API_KEY = 'your_api_key_here';
const BASE_URL = 'https://proapi.whitepages.com/3.0';

async function reversePhoneLookup(phoneNumber) {
  try {
    const response = await axios.get(`${BASE_URL}/phone`, {
      params: {
        api_key: API_KEY,
        phone: phoneNumber
      }
    });

    return response.data;
  } catch (error) {
    console.error('Error:', error.response?.status, error.response?.data);
    return null;
  }
}

async function personLookup(name, city = null, state = null) {
  try {
    const params = {
      api_key: API_KEY,
      name: name
    };

    if (city) params['address.city'] = city;
    if (state) params['address.state_code'] = state;

    const response = await axios.get(`${BASE_URL}/person`, { params });

    return response.data;
  } catch (error) {
    console.error('Error:', error.response?.status, error.response?.data);
    return null;
  }
}

// Примеры использования
(async () => {
  // Обратный поиск по телефону
  const phoneData = await reversePhoneLookup('2065551234');
  console.log('Phone lookup result:', phoneData);

  // Поиск людей
  const personData = await personLookup('John Doe', 'Seattle', 'WA');
  console.log('Person lookup result:', personData);
})();
```

## Полезные ссылки

- [Официальная документация API](https://api.whitepages.com/docs)
- [Whitepages Pro API](https://www.whitepages.com/pro-api)
- [Цены и тарифные планы](https://www.whitepages.com/pro-api#pricing)
- [GitHub - C# Client Library](http://whitepages.github.io/proapi-client-csharp/)
- [Поддержка](https://www.whitepages.com/contact)

## Примечания

1. **Стоимость запросов**: Каждый API вызов тарифицируется согласно вашему плану подписки
2. **Конфиденциальность**: Используйте API только для законных целей и соблюдайте законы о конфиденциальности
3. **Точность данных**: Данные в базе Whitepages обновляются регулярно, но могут содержать устаревшую информацию
4. **Кеширование**: Рекомендуется кешировать результаты на стороне клиента для снижения количества запросов

## Changelog

- **v3.0** - Текущая версия API
- Поддержка JSON формата
- Расширенные данные о репутации телефонов
- Улучшенная точность геолокации

---

*Документация основана на публично доступной информации о Whitepages API. Для получения актуальной и полной информации обращайтесь к официальной документации.*
