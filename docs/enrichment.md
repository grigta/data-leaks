# Документация по обогащению данных (Enrichment)

## Оглавление
- [Общая информация](#общая-информация)
- [Архитектура обогащения](#архитектура-обогащения)
- [Поля базы данных](#поля-базы-данных)
- [Обогащаемые поля](#обогащаемые-поля)
- [Интеграция с Whitepages API](#интеграция-с-whitepages-api)
- [Алгоритм обогащения](#алгоритм-обогащения)
- [API endpoints](#api-endpoints)
- [Безопасность и ограничения](#безопасность-и-ограничения)
- [Примеры использования](#примеры-использования)

---

## Общая информация

Система обогащения данных предоставляет возможность автоматически дополнять записи SSN актуальной информацией из внешних источников (Whitepages API). Обогащение является платной услугой и требует достаточного баланса пользователя.

**Стоимость обогащения**: $1.00 за запрос

**Основные возможности**:
- Поиск и обогащение данных о человеке через Whitepages API
- Использование первого кандидата из результатов (упорядочены по релевантности)
- Атомарная транзакционная система с компенсацией при ошибках
- Безопасное обновление только разрешенных полей
- Базовая проверка совпадения имени для безопасности

---

## Архитектура обогащения

### Двухэтапный процесс обогащения

#### Этап 1: Последовательный таргетированный поиск и выбор кандидата
1. **Последовательный поиск** с использованием только поддерживаемых WhitePages комбинаций параметров
   - **Попытка 1**: Имя + Адрес (если адрес доступен)
     - Whitepages API: `GET /v1/person/?name={firstname lastname}&street={street}&city={city}&state_code={state}&zipcode={zip}`
     - Проверка совпадения имени (firstname и lastname) в результатах
   - **Попытка 2**: Имя + Телефон (если телефон доступен и первая попытка не удалась)
     - Whitepages API: `GET /v1/person/?phone={phone}`
     - Проверка совпадения имени в результатах
   - **Важно**: Email НЕ используется как параметр поиска, так как не поддерживается WhitePages API
   - Возвращает список кандидатов, упорядоченных по релевантности
   - Используется первый кандидат, прошедший проверку имени
   - Выполняется базовая проверка совпадения имени (firstname и lastname, case-insensitive)

#### Этап 2: Получение полных данных
- Если выбран кандидат с `person_id`, запрашиваются полные данные
- Whitepages API: `GET /v1/person/{person_id}`
- Возвращается детальная информация о человеке

#### Этап 3: Извлечение и маппинг данных
- Данные из Whitepages API преобразуются в формат нашей БД
- Применяются правила безопасности (разрешенные поля)
- Обновление записи в SQLite

### Атомарная транзакционная модель

```
1. VALIDATION: Проверка существования записи + достаточности баланса
2. API CALL: Запрос к Whitepages API (поиск + обогащение)
3. PHASE 1 (Postgres): Атомарное списание средств с баланса
   - UPDATE User SET balance = balance - 1.00 WHERE id = X AND balance >= 1.00
   - COMMIT
4. PHASE 2 (SQLite): Обновление записи
   - Если успех: возврат результата
   - Если ошибка: COMPENSATION - возврат средств (refund)
```

**Преимущества модели**:
- Платеж всегда происходит до обновления данных
- При ошибке обновления средства автоматически возвращаются
- Защита от race conditions через атомарный WHERE condition
- Логирование всех критических операций

---

## Поля базы данных

### Схема таблицы SSN (ssn_1, ssn_2)

```sql
CREATE TABLE IF NOT EXISTS ssn_1 (
    id INTEGER PRIMARY KEY,
    firstname TEXT,
    lastname TEXT,
    middlename TEXT,
    address TEXT,           -- Улица/дом (маппится в street для Whitepages)
    city TEXT,
    state TEXT,
    zip TEXT,               -- Почтовый индекс (маппится в zipcode для Whitepages)
    phone TEXT,
    ssn TEXT UNIQUE NOT NULL,  -- 🔒 НИКОГДА не отправляется в Whitepages
    dob TEXT,
    email TEXT
)
```

### Маппинг полей (наша БД ↔ Whitepages API)

| Поле нашей БД | Поле Whitepages API | Направление | Описание |
|---------------|---------------------|-------------|----------|
| `firstname` | `name` (first part) | Отправка ✓ | Имя (только для поиска) |
| `lastname` | `name` (last part) | Отправка ✓ | Фамилия (только для поиска) |
| `middlename` | `name` (middle part) | Получение ✓ | Отчество (может быть обогащено) |
| `address` | `street` | Двусторонняя ⇄ | Улица/дом |
| `city` | `city` | Двусторонняя ⇄ | Город |
| `state` | `state_code` | Двусторонняя ⇄ | Штат (2 буквы) |
| `zip` | `zipcode` | Двусторонняя ⇄ | Почтовый индекс |
| `phone` | `phones[].number` | Двусторонняя ⇄ | Телефон (используется для поиска) |
| `email` | `emails[]` | Получение ✓ | Email (НЕ используется для поиска - не поддерживается API) |
| `dob` | `date_of_birth` | Двусторонняя ⇄ | Дата рождения (ISO формат) |
| `ssn` | ❌ НИКОГДА | - | SSN НЕ отправляется в API |

---

## Обогащаемые поля

### Безопасные поля (SAFE_UPDATE_FIELDS)

Только эти поля могут быть обновлены через обогащение:

```python
SAFE_UPDATE_FIELDS = {'dob', 'address', 'city', 'state', 'zip', 'phone', 'email', 'middlename'}
```

### ❌ Запрещенные для обновления поля

- `firstname` - никогда не обновляется (используется только для валидации)
- `lastname` - никогда не обновляется (используется только для валидации)
- `ssn` - никогда не отправляется и не обновляется
- `id` - системное поле

### Логика обновления полей

1. **Firstname & Lastname**: Используются только для верификации личности
   - Отправляются в Whitepages для поиска
   - Результаты проверяются на совпадение имени
   - **Никогда не обновляются** в БД (защита от подмены личности)

2. **Middlename**: Может быть обогащено из Whitepages
   - Извлекается из поля `name` API ответа (средняя часть имени)
   - Разрешено для обновления через `SAFE_UPDATE_FIELDS`

3. **Address, City, State, Zip**: Обновляются при наличии новых данных
   - Парсятся из `current_addresses[0].address`
   - Формат Whitepages: `"123 Main St, New York, NY 10001"`
   - Обновляются только если значение изменилось

4. **Phone**: Обновляется из массива `phones[]`
   - Выбирается телефон с наибольшим `score`
   - Форматируется в `(XXX) XXX-XXXX`

5. **Email**: Обновляется из массива `emails[]`
   - Берется первый email (строка, не объект)

6. **DOB**: Обновляется из `date_of_birth`
   - ISO формат: `YYYY-MM-DD`

### Структура данных Whitepages API

#### Ответ поиска (Person Search Response)
```json
{
  "id": "P1234567890",  // Whitepages person ID (P + 10 alphanumeric)
  "name": "John Michael Doe",
  "date_of_birth": "1985-03-15",
  "is_dead": false,
  "current_addresses": [
    {
      "address": "123 Main St, New York, NY 10001"
    }
  ],
  "phones": [
    {
      "number": "2125551234",
      "score": 95
    }
  ],
  "emails": [
    "john.doe@example.com"
  ]
}
```

---

## Интеграция с Whitepages API

### Конфигурация клиента

```python
class WhitepagesClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.whitepages.com",
        timeout: int = 30,
        max_retries: int = 3
    )
```

### Переменные окружения

```bash
# .env
WHITEPAGES_API_KEY=your_api_key_here
WHITEPAGES_API_URL=https://api.whitepages.com  # optional, default
```

### API Methods

#### 1. Поиск по телефону
```python
async def search_person_by_phone(
    phone: str,
    return_all: bool = False
) -> Optional[list[Dict] | Dict]
```

**Параметры**:
- `phone`: Номер телефона (нормализуется автоматически)
- `return_all`: Если True, возвращает всех кандидатов; иначе первого

**Нормализация телефона**:
- Удаляются все нецифровые символы
- Убирается ведущая "1" для US номеров
- Результат: 10-digit формат (только цифры)

#### 2. Поиск по имени и адресу
```python
async def search_person_by_name_address(
    firstname: str,
    lastname: str,
    street: Optional[str] = None,
    city: Optional[str] = None,
    state_code: Optional[str] = None,
    zipcode: Optional[str] = None,
    return_all: bool = False
) -> Optional[list[Dict] | Dict]
```

**Параметры**:
- `firstname`, `lastname`: Обязательные
- `street`, `city`, `state_code`, `zipcode`: Опциональные (улучшают точность)
- `return_all`: Если True, возвращает всех кандидатов

**Формирование запроса**:
- `firstname` и `lastname` объединяются в `name` параметр
- `state_code` нормализуется к uppercase (2 буквы)

#### 3. Получение данных по ID
```python
async def get_person_by_id(person_id: str) -> Optional[Dict]
```

**Параметры**:
- `person_id`: Whitepages person ID (формат: P + 10 alphanumeric, case-insensitive)

**Валидация**:
- ID нормализуется к uppercase
- Проверяется regex: `^P[A-Z0-9]{10}$`
- Raises `ValueError` при невалидном формате

#### 4. Последовательный таргетированный поиск (внутренний метод)
```python
async def _search_with_targeted_criteria(
    phone: Optional[str] = None,
    firstname: Optional[str] = None,
    lastname: Optional[str] = None,
    street: Optional[str] = None,
    city: Optional[str] = None,
    state_code: Optional[str] = None,
    zipcode: Optional[str] = None,
    return_all: bool = False
) -> Optional[list[Dict] | Dict]
```

**Назначение**: Выполняет последовательный поиск с использованием только поддерживаемых WhitePages комбинаций параметров

**Последовательность попыток**:
1. **Name + Address**: Если адрес и имя доступны
2. **Name + Phone**: Если первая попытка не удалась и телефон доступен

**Важно**: Email НЕ используется как параметр поиска

#### 5. Обогащение данных (основной метод)
```python
async def enrich_person_data(current_record: Dict[str, Any]) -> Dict[str, Any]
```

**Входные данные** (`current_record`):
```python
{
    'ssn': '123-45-6789',          # НЕ отправляется в API
    'firstname': 'John',
    'lastname': 'Doe',
    'middlename': 'M',
    'phone': '(212) 555-1234',
    'email': 'john@example.com',
    'street': '123 Main St',       # Наше поле 'address' маппится в 'street'
    'city': 'New York',
    'state': 'NY',
    'zipcode': '10001'             # Наше поле 'zip' маппится в 'zipcode'
}
```

**Возвращает**: Словарь с обогащенными полями (только измененные значения)

### Обработка ошибок

```python
# Базовая ошибка API
class WhitepagesAPIError(Exception):
    def __init__(self, message: str, status_code: int = None, trace_id: str = None)

# Rate limiting (429)
class WhitepagesRateLimitError(WhitepagesAPIError):
    pass

# Not found (404)
class WhitepagesNotFoundError(WhitepagesAPIError):
    pass
```

**Retry логика**:
- **429 (Rate Limit)**: Повтор с задержкой из `Retry-After` header (до 3 попыток)
- **5xx (Server Error)**: Экспоненциальная задержка: 1s, 2s, 4s
- **Network Error**: Экспоненциальная задержка
- **Timeout**: Немедленная ошибка (timeout = 30s)

---

## Алгоритм обогащения

### Трехфазный подход

#### PHASE 1: Последовательный таргетированный поиск и выбор кандидата

**Последовательный поиск с использованием только поддерживаемых WhitePages комбинаций параметров**
```python
# Используем последовательную стратегию поиска:
# 1. Сначала пробуем Имя + Адрес
# 2. Если не удалось, пробуем Имя + Телефон
# Email НЕ используется, так как не поддерживается WhitePages API

candidates = await _search_with_targeted_criteria(
    phone=phone,
    firstname=firstname,
    lastname=lastname,
    street=street,
    city=city,
    state_code=state,
    zipcode=zipcode,
    return_all=True
)

# Проверяем всех кандидатов на соответствие имени
if candidates:
    for candidate in candidates:
        # Базовая проверка совпадения имени
        if _verify_basic_name_match(candidate, current_record):
            best_candidate = candidate
            break
```

**Стратегия последовательного поиска**:
1. **Попытка 1** (если доступны адресные компоненты): Поиск по имени и адресу
2. **Попытка 2** (если попытка 1 не удалась или адрес недоступен): Поиск по телефону с проверкой имени
3. **Email не используется**: WhitePages API не поддерживает email как параметр поиска

**Примечание**: Whitepages API возвращает результаты упорядоченными по релевантности, поэтому первый кандидат, прошедший проверку имени, обычно является наиболее подходящим.

#### PHASE 2: Получение полных данных

```python
if best_candidate and best_candidate.get("id"):
    person_id = best_candidate["id"]
    try:
        whitepages_result = await get_person_by_id(person_id)
    except WhitepagesNotFoundError:
        whitepages_result = best_candidate  # Fallback к данным кандидата
else:
    whitepages_result = best_candidate
```

#### PHASE 3: Извлечение и маппинг

```python
# Адрес из current_addresses[0].address
addresses = whitepages_result.get("current_addresses", [])
if addresses:
    address_str = addresses[0].get("address", "")
    parsed_address = _parse_address(address_str)  # "123 Main St, City, ST 12345"
    # enriched_data["street"], ["city"], ["state"], ["zipcode"]

# Телефон с наибольшим score
phones = whitepages_result.get("phones", [])
sorted_phones = sorted(phones, key=lambda p: p.get("score", 0), reverse=True)
if sorted_phones:
    enriched_data["phone"] = _format_phone(sorted_phones[0]["number"])

# Email (первый из массива строк)
emails = whitepages_result.get("emails", [])
if emails:
    enriched_data["email"] = emails[0]

# Дата рождения
dob = whitepages_result.get("date_of_birth")
if dob:
    enriched_data["dob"] = dob

# Отчество (парсится из name и обновляется в БД)
name_str = whitepages_result.get("name", "")
if name_str:
    _, _, middle_name = _parse_name(name_str)
    if middle_name:
        enriched_data["middlename"] = middle_name  # Разрешено в SAFE_UPDATE_FIELDS
```

### Маппинг Whitepages → наша БД

```python
# Обратное маппинг (street → address, zipcode → zip)
update_data = {}
if 'street' in enriched_data:
    update_data['address'] = enriched_data['street']
if 'zipcode' in enriched_data:
    update_data['zip'] = enriched_data['zipcode']

# Прямое копирование других полей
for field in ['city', 'state', 'phone', 'dob', 'email']:
    if field in enriched_data:
        update_data[field] = enriched_data[field]

# Фильтрация по SAFE_UPDATE_FIELDS
update_data = {k: v for k, v in update_data.items() if k in SAFE_UPDATE_FIELDS}
```

---

## API Endpoints

### 1. Public API: Обогащение записи

**Endpoint**: `POST /api/public/enrichment/enrich-record`

**Аутентификация**: JWT Bearer token

**Request Body**:
```json
{
  "ssn": "123-45-6789",
  "table_name": "ssn_1"
}
```

**Response** (200 OK):
```json
{
  "record": {
    "id": 1,
    "firstname": "John",
    "lastname": "Doe",
    "middlename": "Michael",
    "address": "123 Main St",
    "city": "New York",
    "state": "NY",
    "zip": "10001",
    "phone": "(212) 555-1234",
    "ssn": "123-45-6789",
    "dob": "1985-03-15",
    "email": "john.doe@example.com",
    "source_table": "ssn_1",
    "email_count": 1,
    "phone_count": 1
  },
  "updated_fields": ["phone", "email", "dob"],
  "enrichment_cost": 1.0,
  "changes": {
    "phone": "(212) 555-1234",
    "email": "john.doe@example.com",
    "dob": "1985-03-15"
  }
}
```

**Error Responses**:
- `400 Bad Request`: Insufficient balance
- `404 Not Found`: SSN not found или no matching data in Whitepages
- `429 Too Many Requests`: Whitepages rate limit exceeded
- `500 Internal Server Error`: Payment processing error
- `502 Bad Gateway`: Whitepages API error

**Rate Limiting**: 10 requests/hour (можно настроить, сейчас закомментировано для тестирования)

### 2. Enrichment API: Обогащение из противоположной таблицы

**Endpoint**: `POST /api/enrichment/enrich-record`

**Аутентификация**: API Key (Header: `X-API-Key`)

**Request Body**:
```json
{
  "ssn": "123-45-6789",
  "table_name": "ssn_1"
}
```

**Логика**:
- Ищет запись в `opposite_table` (если table_name=ssn_1, то opposite=ssn_2)
- Обогащает текущую запись данными из opposite table
- **Стоимость**: $2.00 (внутренняя цена, без Whitepages)

**Response**:
```json
{
  "record": { ... },
  "updated_fields": ["phone", "email"],
  "enrichment_cost": 2.0,
  "changes": {
    "phone": "(212) 555-1234",
    "email": "john@example.com"
  }
}
```

---

## Безопасность и ограничения

### 🔒 Безопасность данных

#### 1. SSN никогда не передается
```python
# SSN ИСКЛЮЧАЕТСЯ из payload для Whitepages
whitepages_record = {
    'firstname': current_record.get('firstname'),
    'lastname': current_record.get('lastname'),
    # ... other fields
    # SSN: NOT INCLUDED
}
```

#### 2. Валидация идентичности личности
```python
def verify_person_match(current_record: dict, enriched_data: dict) -> bool:
    """
    Проверяет, что обогащенные данные относятся к тому же человеку.
    Сравнивает firstname и lastname (case-insensitive).
    """
    current_firstname = (current_record.get('firstname') or '').strip().lower()
    current_lastname = (current_record.get('lastname') or '').strip().lower()

    enriched_firstname = (enriched_data.get('firstname') or '').strip().lower()
    enriched_lastname = (enriched_data.get('lastname') or '').strip().lower()

    return (current_firstname == enriched_firstname and
            current_lastname == enriched_lastname)
```

**Примечание**: В текущей реализации `enrich_person_data()` Whitepages клиента **НЕ возвращает** firstname/lastname в enriched_data (они фильтруются), поэтому проверка `verify_person_match()` в `api/public/routers/enrichment.py` фактически **всегда ложна**. Валидация происходит внутри `_select_best_candidate()` через `_check_name_match()`.

#### 3. Фильтрация обновляемых полей
```python
# Только безопасные поля могут быть обновлены
SAFE_UPDATE_FIELDS = {'dob', 'address', 'city', 'state', 'zip', 'phone', 'email'}

update_data = {k: v for k, v in update_data.items() if k in SAFE_UPDATE_FIELDS}
```

#### 4. Маскирование SSN в логах
```python
masked_ssn = f"***-**-{ssn[-4:]}" if len(ssn) >= 4 else "***"
logger.info(f"Enrichment request for SSN {masked_ssn}")
```

### ⚡ Rate Limiting

#### Whitepages API
- **Max Retries**: 3 попытки
- **Retry Strategy**: Exponential backoff для 5xx, `Retry-After` header для 429
- **Timeout**: 30 секунд

#### Public API Endpoint
```python
@limiter.limit("10/hour")  # 10 обогащений в час на пользователя
async def enrich_record(...)
```

### 💰 Транзакционная безопасность

#### Атомарное списание баланса
```python
stmt = (
    update(User)
    .where(User.id == current_user.id, User.balance >= ENRICHMENT_COST)
    .values(balance=User.balance - ENRICHMENT_COST)
    .returning(User.balance)
)
result = await db.execute(stmt)
new_balance_row = result.fetchone()

if new_balance_row is None:
    # Race condition caught: insufficient balance at transaction time
    raise HTTPException(status_code=400, detail="Insufficient balance")

await db.commit()  # Charge finalized
```

#### Компенсация при ошибке
```python
try:
    # Update SQLite record
    update_result = data_manager.update_record(table_name, ssn, update_data)
    if not update_result['success']:
        raise Exception("SQLite update failed")
except Exception as e:
    # COMPENSATION: Refund the charge
    refund_stmt = (
        update(User)
        .where(User.id == current_user.id)
        .values(balance=User.balance + ENRICHMENT_COST)
    )
    await db.execute(refund_stmt)
    await db.commit()
    logger.info(f"Refunded ${ENRICHMENT_COST} to user {current_user.id}")
    raise HTTPException(status_code=500, detail="Failed to update record")
```

### 📊 Оптимизация: Пропуск обогащения без изменений

```python
# Сравнение текущих и новых значений
has_changes = False
for key, new_value in update_data.items():
    current_value = current_record.get(key)
    normalized_current = str(current_value).strip() if current_value else ""
    normalized_new = str(new_value).strip() if new_value else ""
    if normalized_current != normalized_new:
        has_changes = True
        break

if not has_changes:
    logger.info("No actual changes detected, skipping charge")
    return EnrichRecordResponse(
        record=SSNRecord(**current_record),
        updated_fields=[],
        enrichment_cost=0.0,
        changes={}
    )
```

**Преимущество**: Пользователь не платит, если данные уже актуальны.

---

## Примеры использования

### Пример 1: Успешное обогащение через Public API

**Request**:
```bash
curl -X POST http://localhost/api/public/enrichment/enrich-record \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{
    "ssn": "123-45-6789",
    "table_name": "ssn_1"
  }'
```

**Процесс**:
1. Проверка баланса пользователя (≥ $1.00)
2. Получение текущей записи из SQLite (ssn_1)
3. Последовательный поиск в Whitepages:
   - Попытка 1: Поиск по Имени + Адресу (123 Main St, New York, NY 10001)
   - Результат: 3 кандидата найдено
   - Проверка имени: Первый кандидат прошел проверку
4. Получение полных данных по `person_id`
5. Списание $1.00 с баланса (атомарная операция)
6. Обновление записи в SQLite (phone, email, dob)
7. Возврат результата

**Response**:
```json
{
  "record": {
    "id": 1,
    "firstname": "John",
    "lastname": "Doe",
    "address": "123 Main St",
    "city": "New York",
    "state": "NY",
    "zip": "10001",
    "phone": "(212) 555-9999",  // ← обновлено
    "ssn": "123-45-6789",
    "dob": "1985-03-15",        // ← обновлено
    "email": "john.doe@example.com",  // ← обновлено
    "source_table": "ssn_1",
    "email_count": 1,
    "phone_count": 1
  },
  "updated_fields": ["phone", "email", "dob"],
  "enrichment_cost": 1.0,
  "changes": {
    "phone": "(212) 555-9999",
    "email": "john.doe@example.com",
    "dob": "1985-03-15"
  }
}
```

### Пример 2: Недостаточно средств

**Request**:
```bash
curl -X POST http://localhost/api/public/enrichment/enrich-record \
  -H "Authorization: Bearer ..." \
  -d '{"ssn": "123-45-6789", "table_name": "ssn_1"}'
```

**Response** (400 Bad Request):
```json
{
  "detail": "Insufficient balance. Required: $1.0, Available: $0.50"
}
```

**Процесс**:
- Fast-fail проверка баланса до вызова API
- Запрос к Whitepages НЕ выполняется
- Баланс НЕ списывается

### Пример 3: Данные не найдены в Whitepages

**Request**:
```bash
curl -X POST http://localhost/api/public/enrichment/enrich-record \
  -H "Authorization: Bearer ..." \
  -d '{"ssn": "999-99-9999", "table_name": "ssn_1"}'
```

**Процесс**:
1. Запись найдена в SQLite
2. Баланс достаточен ($10.00 ≥ $1.00)
3. Последовательный поиск в Whitepages:
   - Попытка 1: Поиск по Имени + Адресу - 0 результатов
   - Попытка 2: Поиск по Имени + Телефону - 0 результатов
4. Списание **НЕ происходит** (нет данных для обогащения)

**Response** (404 Not Found):
```json
{
  "detail": "No matching data found in Whitepages"
}
```

### Пример 4: Нет изменений (оптимизация)

**Request**:
```bash
curl -X POST http://localhost/api/public/enrichment/enrich-record \
  -H "Authorization: Bearer ..." \
  -d '{"ssn": "123-45-6789", "table_name": "ssn_1"}'
```

**Процесс**:
1. Запись найдена в SQLite: `phone="(212) 555-1234"`
2. Whitepages вернул: `phone="(212) 555-1234"` (без изменений)
3. Сравнение: `current_phone == new_phone` → true
4. Списание **НЕ происходит** (нет изменений)

**Response** (200 OK):
```json
{
  "record": { ... },
  "updated_fields": [],
  "enrichment_cost": 0.0,  // ← Бесплатно!
  "changes": {}
}
```

### Пример 5: Ошибка SQLite с компенсацией

**Процесс**:
1. Баланс списан успешно ($1.00)
2. Whitepages API вернул данные
3. **Ошибка при обновлении SQLite** (например, constraint violation)
4. **COMPENSATION**: Возврат $1.00 на баланс пользователя
5. HTTP 500 возвращается клиенту

**Response** (500 Internal Server Error):
```json
{
  "detail": "Failed to update record"
}
```

**Баланс пользователя**: Восстановлен до исходного значения

### Пример 6: Rate limit Whitepages API

**Request**:
```bash
curl -X POST http://localhost/api/public/enrichment/enrich-record \
  -H "Authorization: Bearer ..." \
  -d '{"ssn": "123-45-6789", "table_name": "ssn_1"}'
```

**Процесс**:
1. Whitepages API: 429 Too Many Requests
2. Retry #1: Ожидание 5 секунд
3. Retry #2: 429 снова, ожидание 5 секунд
4. Retry #3: 429 снова
5. Максимум попыток исчерпан
6. Баланс **НЕ списывается** (ошибка API до фазы payment)

**Response** (429 Too Many Requests):
```json
{
  "detail": "Whitepages API rate limit exceeded. Please try again later."
}
```

### Пример 7: Использование через Python SDK

```python
import httpx
import asyncio

async def enrich_ssn_record(token: str, ssn: str, table_name: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost/api/public/enrichment/enrich-record",
            headers={"Authorization": f"Bearer {token}"},
            json={"ssn": ssn, "table_name": table_name},
            timeout=60.0  # Whitepages может быть медленным
        )

        if response.status_code == 200:
            data = response.json()
            print(f"✅ Enrichment successful!")
            print(f"Updated fields: {data['updated_fields']}")
            print(f"Cost: ${data['enrichment_cost']}")
            return data
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.json())
            return None

# Использование
token = "your_jwt_token_here"
result = asyncio.run(enrich_ssn_record(token, "123-45-6789", "ssn_1"))
```

---

## Логирование и мониторинг

### Ключевые логи

```python
# Начало обогащения
logger.info(f"Enrichment request for SSN {masked_ssn} in {table_name} by user {user_id}")

# Вызов Whitepages API
logger.info(f"Calling Whitepages API for SSN {masked_ssn}")
logger.info(f"Whitepages API returned data for SSN {masked_ssn}: {len(enriched_data)} fields")

# Выбор кандидата
logger.info(f"Found {len(candidates)} candidates for phone {normalized_phone}")
logger.info(f"Selected best candidate with score {score}/100: reasons={reasons}, person_id={person_id}")

# Списание баланса
logger.info(f"Atomically deducted ${ENRICHMENT_COST} from user {user_id}. New balance: ${new_balance}")
logger.info(f"Postgres charge committed for user {user_id}")

# Обновление SQLite
logger.info(f"Enrichment changes for SSN {masked_ssn}: fields={updated_fields}, old={old_values}, new={new_values}")
logger.info(f"Successfully updated {len(updated_fields)} fields for SSN {masked_ssn}")

# Компенсация
logger.info(f"Refunded ${ENRICHMENT_COST} to user {user_id} after SQLite failure")
logger.critical(f"CRITICAL: Failed to refund ${ENRICHMENT_COST} to user {user_id}")

# Завершение
logger.info(f"Enrichment completed successfully for SSN {masked_ssn}")
```

### Метрики для мониторинга

- **Успешность обогащения**: `updated_fields` count
- **Стоимость**: `enrichment_cost` (0.0 если без изменений)
- **Whitepages API latency**: время между "Calling" и "returned" логами
- **Компенсации**: количество `Refunded` логов (должно быть минимум)
- **Критические ошибки**: количество `CRITICAL: Failed to refund` (должно быть 0)

---

## Конфигурация и настройка

### Переменные окружения (.env)

```bash
# Whitepages API
WHITEPAGES_API_KEY=your_whitepages_api_key_here
WHITEPAGES_API_URL=https://api.whitepages.com  # optional

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dbname
SQLITE_PATH=/app/data/ssn_database.db

# JWT
JWT_SECRET=your_jwt_secret_min_32_chars
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
```

### Rate Limiting настройка

```python
# В api/public/routers/enrichment.py
@router.post("/enrich-record", response_model=EnrichRecordResponse)
@limiter.limit("10/hour")  # Изменить лимит здесь
async def enrich_record(...):
```

**Варианты**:
- `"5/hour"` - строгий лимит для дорогих операций
- `"20/hour"` - мягкий лимит для premium пользователей
- `"100/day"` - дневной лимит
- Закомментировать для отключения (только для тестирования!)

---

## Troubleshooting

### Проблема: "No matching data found in Whitepages"

**Причины**:
1. Недостаточно данных для поиска (нет телефона, имени, адреса)
2. Имя/телефон не найдены в Whitepages API
3. Все кандидаты не прошли проверку имени
4. API не вернул ни одного кандидата

**Решение**:
- Проверить наличие `firstname`, `lastname`, адреса или `phone` в текущей записи
- Проверить логи: какие кандидаты были найдены и какой метод поиска использовался
- Убедиться, что имена в базе корректны (firstname и lastname)
- **Важно**: Email НЕ используется для поиска, так как не поддерживается WhitePages API. Для успешного поиска необходим адрес или телефон.

### Проблема: "Whitepages API rate limit exceeded"

**Причины**:
- Превышен лимит запросов к Whitepages API
- Все 3 retry попытки вернули 429

**Решение**:
- Подождать время, указанное в `Retry-After` header (обычно 5-60 секунд)
- Проверить квоту API ключа Whitepages
- Обновить API план Whitepages для большей квоты

### Проблема: Баланс списан, но запись не обновлена

**Ожидаемое поведение**: Автоматическая компенсация (refund)

**Проверка**:
1. Поиск в логах: `"Refunded $1.00 to user {user_id}"`
2. Если логов нет, проверить баланс пользователя в PostgreSQL
3. Если `CRITICAL: Failed to refund` - **ручное вмешательство** требуется

**Ручное восстановление**:
```sql
-- Вернуть $1.00 пользователю
UPDATE users SET balance = balance + 1.00 WHERE id = '{user_id}';
```

### Проблема: Name verification failed

**Симптомы**:
- 404 Not Found с "No matching data found"
- Логи: `"First candidate failed basic name verification"`

**Причины**:
- Имя из Whitepages API не совпадает с именем в текущей записи
- Базовая проверка имени выполняется в `WhitepagesClient.enrich_person_data()`

**Решение**:
- Проверить корректность имени в текущей записи
- Убедиться, что firstname и lastname соответствуют данным в Whitepages
- Проверить логи для деталей о несовпадении

### Проблема: Неверный формат телефона

**Симптомы**:
- Телефон не обновляется
- Логи показывают parsing ошибки

**Причины**:
- Whitepages вернул невалидный формат
- Телефон не соответствует US формату (10 цифр)

**Решение**:
- Проверить метод `_format_phone()` и `_normalize_phone()`
- Добавить поддержку международных форматов при необходимости

---

## Будущие улучшения

### Потенциальные фичи

1. **Batch Enrichment**
   - Обогащение нескольких записей одним запросом
   - Скидка на bulk операции

2. **Partial Enrichment**
   - Обогащение только выбранных полей
   - Пользователь платит пропорционально (например, $0.50 за только телефон)

3. **Auto-Enrichment**
   - Автоматическое обогащение при добавлении новой записи
   - Scheduled enrichment (например, раз в месяц для старых записей)

4. **Enrichment History**
   - Логирование всех обогащений для аудита
   - Возможность rollback к предыдущей версии

5. **Multiple Providers**
   - Интеграция с альтернативными API (кроме Whitepages)
   - Fallback стратегия при недоступности primary provider

6. **Enhanced Matching**
   - Добавление нечеткого поиска (fuzzy matching) для имен
   - Поддержка вариаций имен (nicknames)

7. **Smart Caching**
   - Кэширование результатов Whitepages на определенный срок
   - Экономия на повторных запросах для той же записи

---

## Лицензии и compliance

### Data Privacy

- **SSN Protection**: SSN никогда не покидает систему
- **PII Handling**: Минимальная информация отправляется в Whitepages
- **Data Retention**: Обогащенные данные хранятся локально в SQLite

### Whitepages Terms of Service

Использование Whitepages API подчиняется их Terms of Service:
- https://www.whitepages.com/terms-of-service

**Ключевые ограничения**:
- Использовать данные только для законных целей
- Не хранить копии данных Whitepages длительное время без лицензии
- Соблюдать rate limits и квоты API

### FCRA Compliance

Fair Credit Reporting Act (FCRA) может применяться к использованию данных:
- Не использовать для кредитных решений без FCRA-compliant процедур
- Обеспечить точность и актуальность данных
- Позволить пользователям оспаривать неточности

---

## Контакты и поддержка

**Документация**:
- Whitepages API: https://developer.whitepages.com/api-reference
- FastAPI: https://fastapi.tiangolo.com/

**Логи**:
- Public API: `docker-compose logs -f public_api | grep enrichment`
- Enrichment API: `docker-compose logs -f enrichment_api | grep enrich`

**Тестирование**:
```bash
# Health check
curl http://localhost/api/public/health

# Проверка баланса пользователя
curl http://localhost/api/public/auth/me \
  -H "Authorization: Bearer {token}"
```

---

**Версия документа**: 1.0
**Последнее обновление**: 2025-10-31
**Автор**: Claude Code (Anthropic)
