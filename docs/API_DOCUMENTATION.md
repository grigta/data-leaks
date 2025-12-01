# 📖 API Documentation - SSN Database Management System

## 1. Введение и быстрый старт

### Описание системы
Система управления базой данных SSN (Social Security Number) предоставляет мощный инструмент для хранения, поиска и управления персональными данными. Система построена на SQLite и включает три основных компонента:

- **SearchEngine** (`search_engine.py`) - Поисковый движок с 4 типами поиска
- **DataManager** (`data_manager.py`) - Менеджер данных для CRUD операций
- **CLI** (`main.py`) - Интерфейс командной строки

### 🚀 Быстрый старт

```bash
# 1. Инициализация базы данных
python db_schema.py

# 2. Добавление записи
python main.py add --table ssn_1 --ssn 123-45-6789 --firstname John --lastname Doe --email john.doe@example.com

# 3. Поиск записи по SSN
python main.py search --ssn 123-45-6789

# 4. Обновление записи
python main.py update --table ssn_1 --ssn 123-45-6789 --email newemail@example.com

# 5. Поиск по email
python main.py search --email newemail@example.com
```

---

## 2. 🔍 Поиск людей (SearchEngine)

Класс `SearchEngine` из `search_engine.py` предоставляет мощные методы поиска по различным критериям.

### 2.1 Поиск по SSN

**Метод:** `search_by_ssn(ssn, limit=None)`

Поиск записей по номеру социального страхования. SSN автоматически нормализуется и валидируется.

**Python API:**

```python
from search_engine import SearchEngine

engine = SearchEngine()

# Поиск с дефисами
result = engine.search_by_ssn("123-45-6789")

# Поиск без дефисов
result = engine.search_by_ssn("123456789")

# Поиск с пробелами (автоматически нормализуется)
result = engine.search_by_ssn("123 45 6789")

# Поиск с ограничением результатов
result = engine.search_by_ssn("123-45-6789", limit=5)

print(result)
```

**CLI команда:**

```bash
# Базовый поиск
python main.py search --ssn 123-45-6789

# С ограничением результатов
python main.py search --ssn 123-45-6789 --limit 5
```

**Формат JSON ответа:**

```json
{
  "status": "success",
  "count": 1,
  "results": [
    {
      "id": 42,
      "firstname": "John",
      "lastname": "Doe",
      "middlename": "Michael",
      "address": "123 Main St",
      "city": "Springfield",
      "state": "IL",
      "zip": "62701",
      "phone": "555-1234",
      "ssn": "123-45-6789",
      "dob": "1980-01-15",
      "email": "john.doe@example.com",
      "source_table": "ssn_1"
    }
  ]
}
```

**Особенности:**
- ✅ Нормализация SSN (удаление дефисов, пробелов, других символов)
- ✅ Валидация 9 цифр
- ✅ Форматирование результата как XXX-XX-XXXX
- ✅ Автоматический поиск в обеих таблицах (`ssn_1` и `ssn_2`)

---

### 2.2 Поиск по Email

**Метод:** `search_by_email(email, limit=None)`

Регистронезависимый поиск по email адресу.

**Python API:**

```python
from search_engine import SearchEngine

engine = SearchEngine()

# Базовый поиск
result = engine.search_by_email("john.doe@example.com")

# Поиск регистронезависимый
result = engine.search_by_email("JOHN.DOE@EXAMPLE.COM")

# С ограничением результатов
result = engine.search_by_email("john.doe@example.com", limit=10)

print(result)
```

**CLI команда:**

```bash
# Базовый поиск
python main.py search --email john.doe@example.com

# С ограничением результатов
python main.py search --email john.doe@example.com --limit 10
```

**Особенности:**
- ✅ Регистронезависимый поиск (COLLATE NOCASE)
- ✅ Нормализация (trim + lowercase)
- ✅ Базовая валидация формата email
- ✅ Использует оптимизированный индекс `idx_{table}_email`

---

### 2.3 Поиск по имени + ZIP код

**Метод:** `search_by_name_zip(firstname, lastname, zip_code, limit=None)`

Точный поиск по комбинации имени, фамилии и почтового индекса.

**Python API:**

```python
from search_engine import SearchEngine

engine = SearchEngine()

# Базовый поиск
result = engine.search_by_name_zip(
    firstname="John",
    lastname="Doe",
    zip_code="62701"
)

# С ограничением результатов
result = engine.search_by_name_zip(
    firstname="John",
    lastname="Doe",
    zip_code="62701",
    limit=5
)

print(result)
```

**CLI команда:**

```bash
# Базовый поиск
python main.py search --firstname John --lastname Doe --zip 62701

# С ограничением результатов
python main.py search --firstname John --lastname Doe --zip 62701 --limit 5
```

**Требования:**
- ⚠️ Все три параметра обязательны (firstname, lastname, zip_code)
- ⚠️ Точное совпадение по всем параметрам
- ✅ Использует композитный индекс `idx_{table}_name_zip` для оптимизации

---

### 2.4 Поиск по имени + штат

**Метод:** `search_by_name_state(firstname, lastname, state, limit=None)`

Точный поиск по комбинации имени, фамилии и штата.

**Python API:**

```python
from search_engine import SearchEngine

engine = SearchEngine()

# Базовый поиск
result = engine.search_by_name_state(
    firstname="John",
    lastname="Doe",
    state="IL"
)

# State автоматически приводится к верхнему регистру
result = engine.search_by_name_state(
    firstname="John",
    lastname="Doe",
    state="il"  # Автоматически станет "IL"
)

# С ограничением результатов
result = engine.search_by_name_state(
    firstname="John",
    lastname="Doe",
    state="IL",
    limit=5
)

print(result)
```

**CLI команда:**

```bash
# Базовый поиск
python main.py search --firstname John --lastname Doe --state IL

# С ограничением результатов
python main.py search --firstname John --lastname Doe --state IL --limit 5
```

**Требования:**
- ⚠️ State должен быть 2-символьным кодом
- ✅ Автоматическое приведение к верхнему регистру
- ✅ Использует композитный индекс `idx_{table}_name_state` для оптимизации

---

### 2.5 Универсальный поиск

**Метод:** `search_all(ssn=None, firstname=None, lastname=None, zip_code=None, state=None, email=None, limit=None)`

Автоматически определяет тип поиска по предоставленным параметрам и вызывает соответствующий метод.

**Python API:**

```python
from search_engine import SearchEngine

engine = SearchEngine()

# Поиск по SSN
result = engine.search_all(ssn="123-45-6789")

# Поиск по email
result = engine.search_all(email="john.doe@example.com")

# Поиск по имени + ZIP
result = engine.search_all(
    firstname="John",
    lastname="Doe",
    zip_code="62701"
)

# Поиск по имени + штат
result = engine.search_all(
    firstname="John",
    lastname="Doe",
    state="IL"
)

# С ограничением результатов
result = engine.search_all(
    email="john.doe@example.com",
    limit=10
)

print(result)
```

**Логика определения типа поиска:**
1. Если указан `ssn` → `search_by_ssn()`
2. Иначе если указан `email` → `search_by_email()`
3. Иначе если указаны `firstname`, `lastname`, `zip_code` → `search_by_name_zip()`
4. Иначе если указаны `firstname`, `lastname`, `state` → `search_by_name_state()`
5. Иначе → ошибка валидации

---

### 2.6 Обработка результатов и ошибок

**Формат успешного ответа:**

```json
{
  "status": "success",
  "count": 2,
  "results": [
    {
      "id": 1,
      "firstname": "John",
      "lastname": "Doe",
      "ssn": "123-45-6789",
      "email": "john@example.com",
      "source_table": "ssn_1"
    },
    {
      "id": 2,
      "firstname": "Jane",
      "lastname": "Doe",
      "ssn": "987-65-4321",
      "email": "jane@example.com",
      "source_table": "ssn_2"
    }
  ]
}
```

**Пустой результат:**

```json
{
  "status": "success",
  "count": 0,
  "results": []
}
```

**Формат ошибки:**

```json
{
  "status": "error",
  "error": "Invalid SSN format. Must be 9 digits."
}
```

**Типы ошибок:**
- ❌ Ошибки валидации (некорректный формат SSN, email, state)
- ❌ База данных не найдена
- ❌ Некорректные параметры (отсутствуют обязательные поля)
- ❌ Некорректное имя таблицы

---

## 3. ➕ Создание записей (DataManager)

Класс `DataManager` из `data_manager.py` предоставляет методы для создания и управления записями.

### 3.1 Добавление одной записи (UPSERT)

**Метод:** `upsert_record(table_name, record_data)`

UPSERT операция: создает новую запись или обновляет существующую, если SSN уже есть в таблице.

**Python API:**

```python
from data_manager import DataManager

manager = DataManager()

# Полная запись со всеми полями
record_data = {
    "ssn": "123-45-6789",
    "firstname": "John",
    "lastname": "Doe",
    "middlename": "Michael",
    "address": "123 Main St",
    "city": "Springfield",
    "state": "IL",
    "zip": "62701",
    "phone": "555-1234",
    "dob": "1980-01-15",
    "email": "john.doe@example.com"
}

result = manager.upsert_record("ssn_1", record_data)
print(result)

# Минимальная запись (только обязательные поля)
minimal_record = {
    "ssn": "987-65-4321",
    "firstname": "Jane",
    "lastname": "Smith"
}

result = manager.upsert_record("ssn_2", minimal_record)
print(result)
```

**CLI команда:**

```bash
# Полная запись
python main.py add --table ssn_1 \
  --ssn 123-45-6789 \
  --firstname John \
  --lastname Doe \
  --middlename Michael \
  --address "123 Main St" \
  --city Springfield \
  --state IL \
  --zip 62701 \
  --phone 555-1234 \
  --dob 1980-01-15 \
  --email john.doe@example.com

# Минимальная запись
python main.py add --table ssn_1 \
  --ssn 987-65-4321 \
  --firstname Jane \
  --lastname Smith
```

**Формат успешного ответа:**

```json
{
  "success": true,
  "record_id": 42,
  "ssn": "123-45-6789",
  "message": "Record upserted successfully in ssn_1"
}
```

**Поведение UPSERT:**
- ✅ Если SSN существует → обновление всех полей
- ✅ Если SSN новый → создание новой записи
- ✅ Использует SQL: `INSERT OR REPLACE INTO {table_name} (...) VALUES (...)`

---

### 3.2 Массовое добавление записей

**Метод:** `bulk_upsert(table_name, records)`

Добавление множества записей за одну операцию с обработкой ошибок и транзакциями.

**Python API:**

```python
from data_manager import DataManager

manager = DataManager()

# Список записей
records = [
    {
        "ssn": "111-11-1111",
        "firstname": "Alice",
        "lastname": "Johnson",
        "email": "alice@example.com"
    },
    {
        "ssn": "222-22-2222",
        "firstname": "Bob",
        "lastname": "Williams",
        "email": "bob@example.com"
    },
    {
        "ssn": "333-33-3333",
        "firstname": "Charlie",
        "lastname": "Brown",
        "email": "charlie@example.com"
    }
]

result = manager.bulk_upsert("ssn_1", records)
print(result)

# Вывод статистики
print(f"Всего: {result['total']}")
print(f"Успешно: {result['successful']}")
print(f"Ошибок: {result['failed']}")

# Обработка ошибок
if result['failed'] > 0:
    for failed in result['failed_records']:
        print(f"Ошибка в записи {failed['index']}: {failed['error']}")
```

**Формат ответа:**

```json
{
  "total": 3,
  "successful": 2,
  "failed": 1,
  "failed_records": [
    {
      "index": 1,
      "record": {
        "ssn": "invalid",
        "firstname": "Bob"
      },
      "error": "Invalid SSN format"
    }
  ]
}
```

**Особенности:**
- ✅ Продолжает обработку при ошибках (не останавливается на первой ошибке)
- ✅ Использует транзакции для атомарности
- ✅ Возвращает детальную статистику с индексами проблемных записей
- ✅ Использует `cursor.executemany()` для оптимизации производительности

---

### 3.3 Валидация данных при создании

Все данные проходят валидацию через `DataValidator` из `csv_importer.py` перед добавлением в базу.

| Поле | Обязательность | Правила валидации | Метод валидации |
|------|----------------|-------------------|-----------------|
| **ssn** | ✅ Обязательно | 9 цифр, форматируется как XXX-XX-XXXX | `DataValidator.validate_ssn()` |
| **email** | ⚪ Опционально | Должен содержать @ и домен | `DataValidator.validate_email()` |
| **phone** | ⚪ Опционально | Нормализуется (удаляются нечисловые символы) | `DataValidator.validate_phone()` |
| **dob** | ⚪ Опционально | Формат YYYY-MM-DD | `DataValidator.validate_date()` |
| **zip** | ⚪ Опционально | 5 цифр | `DataValidator.validate_zip()` |
| **state** | ⚪ Опционально | 2 символа, верхний регистр | `DataValidator.validate_state()` |
| **firstname** | ⚪ Опционально | Trim whitespace | - |
| **lastname** | ⚪ Опционально | Trim whitespace | - |
| **middlename** | ⚪ Опционально | Trim whitespace | - |
| **address** | ⚪ Опционально | Trim whitespace | - |
| **city** | ⚪ Опционально | Trim whitespace | - |

**Примеры валидации:**

```python
from csv_importer import DataValidator

validator = DataValidator()

# SSN валидация
print(validator.validate_ssn("123-45-6789"))  # "123456789"
print(validator.validate_ssn("123456789"))     # "123456789"
print(validator.validate_ssn("invalid"))       # None (невалидный)

# Email валидация
print(validator.validate_email("test@example.com"))  # "test@example.com"
print(validator.validate_email("invalid"))           # None

# State валидация
print(validator.validate_state("il"))   # "IL"
print(validator.validate_state("IL"))   # "IL"
print(validator.validate_state("abc"))  # None (не 2 символа)
```

---

## 4. 🔄 Обновление записей (DataManager)

### 4.1 Полное обновление (UPSERT)

Для полного обновления записи используйте тот же метод `upsert_record()`, что и для создания.

**Python API:**

```python
from data_manager import DataManager

manager = DataManager()

# Если SSN существует, все поля будут перезаписаны
full_update = {
    "ssn": "123-45-6789",  # Существующий SSN
    "firstname": "John",
    "lastname": "Updated",
    "email": "new.email@example.com",
    "phone": "555-9999"
}

result = manager.upsert_record("ssn_1", full_update)
print(result)
```

**Поведение:**
- ✅ Полная замена всех полей существующей записи
- ⚠️ Поля, не указанные в record_data, будут установлены в NULL

---

### 4.2 Частичное обновление (UPDATE)

**Метод:** `update_record(table_name, ssn, update_data)`

Обновление только указанных полей существующей записи без затрагивания остальных данных.

**Python API:**

```python
from data_manager import DataManager

manager = DataManager()

# Обновление только email
result = manager.update_record(
    table_name="ssn_1",
    ssn="123-45-6789",
    update_data={"email": "updated@example.com"}
)
print(result)

# Обновление нескольких полей
result = manager.update_record(
    table_name="ssn_1",
    ssn="123-45-6789",
    update_data={
        "email": "new@example.com",
        "phone": "555-7777",
        "address": "456 Oak Ave"
    }
)
print(result)
```

**CLI команда:**

```bash
# Обновление одного поля
python main.py update --table ssn_1 --ssn 123-45-6789 --email updated@example.com

# Обновление нескольких полей
python main.py update --table ssn_1 --ssn 123-45-6789 \
  --email new@example.com \
  --phone 555-7777 \
  --address "456 Oak Ave"
```

**Формат успешного ответа:**

```json
{
  "success": true,
  "record_id": 42,
  "ssn": "123-45-6789",
  "message": "Record updated successfully in ssn_1",
  "updated_fields": ["email", "phone", "address"]
}
```

**Ошибка если запись не найдена:**

```json
{
  "success": false,
  "error": "Record with SSN 123-45-6789 not found in ssn_1"
}
```

**Логика работы:**
1. Получает текущую запись через `get_record(table_name, ssn)`
2. Объединяет текущие данные с `update_data`
3. Валидирует объединенные данные
4. Выполняет UPDATE с динамическим SQL: `UPDATE {table_name} SET field1 = ?, field2 = ? WHERE ssn = ?`

---

### 4.3 Разница между UPSERT и UPDATE

| Метод | Описание | Использование | Поведение с несуществующим SSN |
|-------|----------|---------------|--------------------------------|
| **upsert_record()** | Полная замена всех полей | Когда есть полный набор данных | ✅ Создает новую запись |
| **update_record()** | Обновление только указанных полей | Для изменения отдельных полей | ❌ Возвращает ошибку |

**Пример сравнения:**

```python
from data_manager import DataManager

manager = DataManager()

# Исходная запись
original = {
    "ssn": "123-45-6789",
    "firstname": "John",
    "lastname": "Doe",
    "email": "john@example.com",
    "phone": "555-1234"
}
manager.upsert_record("ssn_1", original)

# UPSERT - полная замена
manager.upsert_record("ssn_1", {
    "ssn": "123-45-6789",
    "firstname": "Jane",
    "email": "jane@example.com"
})
# Результат: firstname="Jane", lastname=NULL, email="jane@example.com", phone=NULL

# UPDATE - частичное обновление
manager.update_record("ssn_1", "123-45-6789", {
    "email": "updated@example.com"
})
# Результат: firstname="John", lastname="Doe", email="updated@example.com", phone="555-1234"
```

---

## 5. 🗑️ Дополнительные операции

### 5.1 Удаление записей

**Метод:** `delete_record(table_name, ssn)`

Удаляет запись из указанной таблицы по SSN.

**Python API:**

```python
from data_manager import DataManager

manager = DataManager()

# Удаление записи
result = manager.delete_record("ssn_1", "123-45-6789")
print(result)
```

**Формат ответа (успех):**

```json
{
  "success": true,
  "deleted": true,
  "ssn": "123-45-6789",
  "message": "Record deleted successfully from ssn_1"
}
```

**Формат ответа (не найдена):**

```json
{
  "success": true,
  "deleted": false,
  "ssn": "123-45-6789",
  "message": "Record not found"
}
```

**SQL запрос:**

```sql
DELETE FROM {table_name} WHERE ssn = ?
```

---

### 5.2 Получение записи

**Метод:** `get_record(table_name, ssn)`

Получает полную запись из указанной таблицы по SSN.

**Python API:**

```python
from data_manager import DataManager

manager = DataManager()

# Получение записи
record = manager.get_record("ssn_1", "123-45-6789")

if record:
    print(f"Найдена запись: {record['firstname']} {record['lastname']}")
    print(f"Email: {record['email']}")
else:
    print("Запись не найдена")
```

**Возвращаемое значение:**
- Словарь с данными записи (если найдена)
- `None` (если не найдена)

**SQL запрос:**

```sql
SELECT * FROM {table_name} WHERE ssn = ?
```

---

### 5.3 Проверка существования

**Метод:** `record_exists(table_name, ssn)`

Проверяет, существует ли запись с указанным SSN в таблице.

**Python API:**

```python
from data_manager import DataManager

manager = DataManager()

# Проверка существования
if manager.record_exists("ssn_1", "123-45-6789"):
    print("Запись существует")
else:
    print("Запись не найдена")

# Использование в условиях
ssn = "123-45-6789"
table = "ssn_1"

if not manager.record_exists(table, ssn):
    # Создать новую запись
    manager.upsert_record(table, {"ssn": ssn, "firstname": "New"})
else:
    # Обновить существующую
    manager.update_record(table, ssn, {"email": "updated@example.com"})
```

**Возвращаемое значение:**
- `True` - запись существует
- `False` - запись не найдена

**Внутренняя реализация:**
Использует `get_record()` и проверяет, является ли результат не `None`.

---

## 6. 🔧 Конфигурация

### 6.1 Настройка пути к базе данных

**По умолчанию:** `/root/soft/ssn_database.db` (константа `DEFAULT_DB_PATH` в `db_schema.py`)

**Python API:**

```python
from search_engine import SearchEngine
from data_manager import DataManager

# Использование кастомного пути к БД
custom_db_path = "/custom/path/my_database.db"

# Инициализация SearchEngine с кастомным путем
engine = SearchEngine(db_path=custom_db_path)

# Инициализация DataManager с кастомным путем
manager = DataManager(db_path=custom_db_path)

# Использование
result = engine.search_by_ssn("123-45-6789")
```

**CLI:**

```bash
# Использование глобального флага --db-path
python main.py --db-path /custom/path/my_database.db search --ssn 123-45-6789

python main.py --db-path /custom/path/my_database.db add --table ssn_1 \
  --ssn 123-45-6789 \
  --firstname John \
  --lastname Doe
```

---

### 6.2 Отладка и логирование

**CLI - режим отладки:**

```bash
# Использование флага --verbose или -v для уровня DEBUG
python main.py --verbose search --ssn 123-45-6789

# Краткая форма
python main.py -v search --email test@example.com
```

**Python API - настройка логирования:**

```python
import logging
from search_engine import SearchEngine
from data_manager import DataManager

# Базовая настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Инициализация компонентов
engine = SearchEngine()
manager = DataManager()

# Теперь все операции будут логироваться с уровнем DEBUG
result = engine.search_by_ssn("123-45-6789")
```

**Доступные логгеры:**
- `SearchEngine` - логи поисковых операций
- `DataManager` - логи операций с данными
- `db_schema` - логи создания схемы БД
- `csv_importer` - логи импорта и валидации

**Пример вывода логов:**

```
2025-10-27 10:15:23 - SearchEngine - DEBUG - Searching by SSN: 123-45-6789
2025-10-27 10:15:23 - SearchEngine - DEBUG - Normalized SSN: 123456789
2025-10-27 10:15:23 - SearchEngine - DEBUG - Found 1 records
2025-10-27 10:15:24 - DataManager - DEBUG - Upserting record in ssn_1
2025-10-27 10:15:24 - DataManager - INFO - Record upserted successfully: 123-45-6789
```

---

## 7. 📋 Примеры типичных сценариев

### 7.1 Поиск человека по email и обновление телефона

**Полный Python код:**

```python
import json
from search_engine import SearchEngine
from data_manager import DataManager

# Инициализация
engine = SearchEngine()
manager = DataManager()

# Шаг 1: Поиск по email
email_to_find = "john.doe@example.com"
search_result = engine.search_by_email(email_to_find)

# Шаг 2: Парсинг JSON результата
result_data = json.loads(search_result) if isinstance(search_result, str) else search_result

# Шаг 3: Проверка наличия результатов
if result_data["status"] == "success" and result_data["count"] > 0:
    # Шаг 4: Извлечь SSN и source_table из первого результата
    first_record = result_data["results"][0]
    ssn = first_record["ssn"]
    source_table = first_record["source_table"]

    print(f"Найдена запись: {first_record['firstname']} {first_record['lastname']}")
    print(f"Таблица: {source_table}, SSN: {ssn}")

    # Шаг 5: Обновить телефон
    new_phone = "555-9999"
    update_result = manager.update_record(
        table_name=source_table,
        ssn=ssn,
        update_data={"phone": new_phone}
    )

    if update_result["success"]:
        print(f"✅ Телефон успешно обновлен на {new_phone}")
    else:
        print(f"❌ Ошибка обновления: {update_result['error']}")
else:
    print(f"❌ Записи с email {email_to_find} не найдены")
```

---

### 7.2 Массовый импорт с обработкой ошибок

**Полный Python код:**

```python
from data_manager import DataManager

# Инициализация
manager = DataManager()

# Шаг 1: Подготовить список словарей с записями
records_to_import = [
    {
        "ssn": "111-11-1111",
        "firstname": "Alice",
        "lastname": "Johnson",
        "email": "alice@example.com",
        "phone": "555-0001"
    },
    {
        "ssn": "222-22-2222",
        "firstname": "Bob",
        "lastname": "Williams",
        "email": "bob@example.com",
        "phone": "555-0002"
    },
    {
        "ssn": "invalid-ssn",  # Эта запись вызовет ошибку
        "firstname": "Charlie",
        "lastname": "Brown"
    },
    {
        "ssn": "333-33-3333",
        "firstname": "David",
        "lastname": "Davis",
        "email": "david@example.com"
    }
]

# Шаг 2: Выполнить массовый импорт
result = manager.bulk_upsert("ssn_1", records_to_import)

# Шаг 3: Вывести статистику
print("=" * 50)
print("📊 СТАТИСТИКА ИМПОРТА")
print("=" * 50)
print(f"Всего записей: {result['total']}")
print(f"✅ Успешно импортировано: {result['successful']}")
print(f"❌ Ошибок: {result['failed']}")
print()

# Шаг 4: Обработать ошибки
if result['failed'] > 0:
    print("⚠️ ДЕТАЛИ ОШИБОК:")
    print("-" * 50)
    for failed in result['failed_records']:
        print(f"Запись #{failed['index']}:")
        print(f"  SSN: {failed['record'].get('ssn', 'N/A')}")
        print(f"  Имя: {failed['record'].get('firstname', 'N/A')} {failed['record'].get('lastname', 'N/A')}")
        print(f"  Ошибка: {failed['error']}")
        print()

# Пример вывода:
# ==================================================
# 📊 СТАТИСТИКА ИМПОРТА
# ==================================================
# Всего записей: 4
# ✅ Успешно импортировано: 3
# ❌ Ошибок: 1
#
# ⚠️ ДЕТАЛИ ОШИБОК:
# --------------------------------------------------
# Запись #2:
#   SSN: invalid-ssn
#   Имя: Charlie Brown
#   Ошибка: Invalid SSN format
```

---

### 7.3 Проверка существования перед созданием

**Полный Python код:**

```python
from data_manager import DataManager

# Инициализация
manager = DataManager()

# Данные для обработки
ssn = "123-45-6789"
table = "ssn_1"

# Новые данные
new_data = {
    "ssn": ssn,
    "firstname": "John",
    "lastname": "Doe",
    "email": "john.doe@example.com",
    "phone": "555-1234"
}

# Данные для обновления
update_data = {
    "email": "updated@example.com",
    "phone": "555-9999"
}

# Шаг 1: Проверить существование записи
if manager.record_exists(table, ssn):
    print(f"✅ Запись с SSN {ssn} уже существует в {table}")

    # Шаг 2a: Обновить существующую запись
    print("🔄 Обновление существующей записи...")
    result = manager.update_record(table, ssn, update_data)

    if result["success"]:
        print(f"✅ Запись обновлена. Обновленные поля: {result['updated_fields']}")
    else:
        print(f"❌ Ошибка обновления: {result['error']}")
else:
    print(f"❌ Запись с SSN {ssn} не найдена в {table}")

    # Шаг 2b: Создать новую запись
    print("➕ Создание новой записи...")
    result = manager.upsert_record(table, new_data)

    if result["success"]:
        print(f"✅ Новая запись создана с ID: {result['record_id']}")
    else:
        print(f"❌ Ошибка создания: {result.get('error', 'Unknown error')}")

# Альтернативный вариант: умное обновление
def smart_upsert(manager, table, ssn, data, partial_update=None):
    """
    Умное обновление: создает или частично обновляет запись

    Args:
        manager: DataManager instance
        table: Имя таблицы
        ssn: SSN для поиска
        data: Полные данные для создания
        partial_update: Частичные данные для обновления (если None, используется data)
    """
    if manager.record_exists(table, ssn):
        # Запись существует - частичное обновление
        update_fields = partial_update if partial_update else data
        return manager.update_record(table, ssn, update_fields)
    else:
        # Запись не существует - создание
        return manager.upsert_record(table, data)

# Использование
result = smart_upsert(
    manager=manager,
    table="ssn_1",
    ssn="999-99-9999",
    data={
        "ssn": "999-99-9999",
        "firstname": "Smart",
        "lastname": "User",
        "email": "smart@example.com"
    },
    partial_update={"email": "new.smart@example.com"}
)

print(result)
```

---

## 8. ⚠️ Важные замечания

### 🔐 Ограничения целостности данных
- ✅ **SSN уникален** в каждой таблице (`UNIQUE` constraint)
- ✅ Попытка вставить дубликат SSN через обычный INSERT вызовет ошибку
- ✅ UPSERT автоматически обрабатывает дубликаты через `INSERT OR REPLACE`

### 📋 Доступные таблицы
- ✅ Только **`ssn_1`** и **`ssn_2`** доступны
- ❌ Валидация через `validate_table_name()` в `db_schema.py`
- ❌ Попытка использовать другие таблицы вызовет ошибку

### 🔍 Автоматический поиск
- ✅ Все методы поиска автоматически ищут в **обеих таблицах** через `UNION ALL`
- ✅ Результаты включают поле `source_table` для идентификации источника

### 📝 Обработка невалидных данных
- ⚠️ Невалидные данные **логируются как warning**, но не останавливают операцию
- ⚠️ В bulk операциях невалидные записи пропускаются, остальные обрабатываются

### 💾 Транзакции
- ✅ Bulk операции используют **транзакции** для атомарности
- ✅ При ошибке откатывается вся транзакция (для обычных bulk операций)

### ⚡ Оптимизация
Созданы оптимизированные индексы для быстрого поиска:
- `idx_{table}_name_zip` - композитный индекс для поиска по имени + ZIP
- `idx_{table}_name_state` - композитный индекс для поиска по имени + штат
- `idx_{table}_email` - индекс для поиска по email

### 🚀 Режим производительности
- ✅ База данных использует **WAL режим** (`PRAGMA journal_mode = WAL`)
- ✅ Повышает производительность параллельных операций чтения/записи

---

## 9. 🚀 Быстрый старт - Пошаговая инструкция

### Шаг 1: Инициализация базы данных

```bash
python db_schema.py
```

**Результат:**
- Создается файл `/root/soft/ssn_database.db`
- Создаются таблицы `ssn_1` и `ssn_2`
- Создаются все необходимые индексы
- Устанавливается WAL режим

---

### Шаг 2: Добавление первой записи

```bash
python main.py add --table ssn_1 \
  --ssn 123-45-6789 \
  --firstname John \
  --lastname Doe \
  --email john.doe@example.com \
  --phone 555-1234 \
  --city Springfield \
  --state IL \
  --zip 62701
```

**Результат:**
```json
{
  "success": true,
  "record_id": 1,
  "ssn": "123-45-6789",
  "message": "Record upserted successfully in ssn_1"
}
```

---

### Шаг 3: Поиск записи по SSN

```bash
python main.py search --ssn 123-45-6789
```

**Результат:**
```json
{
  "status": "success",
  "count": 1,
  "results": [
    {
      "id": 1,
      "firstname": "John",
      "lastname": "Doe",
      "ssn": "123-45-6789",
      "email": "john.doe@example.com",
      "phone": "555-1234",
      "city": "Springfield",
      "state": "IL",
      "zip": "62701",
      "source_table": "ssn_1"
    }
  ]
}
```

---

### Шаг 4: Обновление email записи

```bash
python main.py update --table ssn_1 \
  --ssn 123-45-6789 \
  --email new.john.doe@example.com
```

**Результат:**
```json
{
  "success": true,
  "record_id": 1,
  "ssn": "123-45-6789",
  "message": "Record updated successfully in ssn_1",
  "updated_fields": ["email"]
}
```

---

### Шаг 5: Поиск по новому email

```bash
python main.py search --email new.john.doe@example.com
```

**Результат:**
```json
{
  "status": "success",
  "count": 1,
  "results": [
    {
      "id": 1,
      "firstname": "John",
      "lastname": "Doe",
      "ssn": "123-45-6789",
      "email": "new.john.doe@example.com",
      "source_table": "ssn_1"
    }
  ]
}
```

---

### 🎉 Готово!

Теперь вы готовы использовать SSN Database Management System для:
- 🔍 Поиска людей по различным критериям
- ➕ Создания и массового импорта записей
- 🔄 Обновления существующих данных
- 🗑️ Удаления записей

---

## 📚 Дополнительные ресурсы

### Файлы проекта
- `search_engine.py` - Поисковый движок
- `data_manager.py` - Менеджер данных
- `main.py` - CLI интерфейс
- `db_schema.py` - Схема базы данных
- `csv_importer.py` - Валидация и импорт

### Справка по CLI
```bash
# Общая справка
python main.py --help

# Справка по команде search
python main.py search --help

# Справка по команде add
python main.py add --help

# Справка по команде update
python main.py update --help
```

---

**© 2025 SSN Database Management System**
