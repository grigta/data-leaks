# Итоговая информация по импорту данных

## Текущее состояние базы данных

**Путь к базе:** `/root/soft/data/ssn_database.db`
**Размер:** 119 GB

**Количество записей:**
- `ssn_1`: 239,582,275 записей (~240M)
- `ssn_2`: 159,538,617 записей (~160M)

## CSV файлы для импорта

**Путь:** `/root/soft/newdata/`

| Файл | Строк | Описание |
|------|-------|----------|
| att_final.csv | 88,320,018 | Основные данные (имена, адреса, SSN, DOB, email, phone) |
| dob_mapping.csv | 43,525 | Маппинг зашифрованных дат рождения |
| ssn_mapping.csv | 43,989,218 | Маппинг зашифрованных SSN |

## Статистика данных (выборка 50K записей)

- **SSN**: 73.4% записей имеют SSN (~1% зашифрованных)
- **DOB**: 98.2% записей имеют DOB (~6% зашифрованных)
- **Email**: 100% записей
- **Phone**: 100% записей
- **Address**: 100% записей

## Созданные скрипты

### 1. scripts/preview_csv_data.py
**Назначение:** Предварительный просмотр и анализ CSV данных

**Использование:**
```bash
# Базовый просмотр
python3 scripts/preview_csv_data.py --rows 20

# С анализом статистики
python3 scripts/preview_csv_data.py --rows 20 --analyze --sample-size 50000
```

**Что делает:**
- Показывает примеры обработанных записей
- Парсит имена на firstname, middlename, lastname
- Парсит адреса на address, city, state, zip
- Нормализует SSN и телефоны
- Показывает статистику заполненности полей

### 2. scripts/import_csv_data.py
**Назначение:** Импорт CSV данных в SQLite базу

**Использование:**
```bash
# Базовый импорт в ssn_1
python3 scripts/import_csv_data.py

# Импорт в ssn_2
python3 scripts/import_csv_data.py --table ssn_2

# С кастомными параметрами
python3 scripts/import_csv_data.py --table ssn_1 --batch-size 50000 --load-mappings
```

**Параметры:**
- `--table {ssn_1,ssn_2}` - целевая таблица
- `--batch-size N` - размер батча (по умолчанию: 10000)
- `--load-mappings` - загрузить маппинги для расшифровки
- `--allow-duplicates` - разрешить дубликаты SSN

**Что делает:**
- Парсит и нормализует данные из CSV
- Применяет маппинги для зашифрованных значений
- Вставляет данные батчами (высокая производительность)
- Пропускает дубликаты по SSN (по умолчанию)
- Создает дополнительные индексы после импорта
- Оптимизирует базу (VACUUM, ANALYZE)

**Производительность:**
- Без маппингов: ~2-4 часа для 88M записей
- С маппингами: ~4-8 часов для 88M записей

### 3. scripts/add_indexes.py
**Назначение:** Добавление дополнительных индексов к существующей базе

**Использование:**
```bash
# Добавить к обеим таблицам
python3 scripts/add_indexes.py

# Только к ssn_1
python3 scripts/add_indexes.py --table ssn_1
```

**Создаваемые индексы:**
- `idx_{table}_email` - поиск по email (case-insensitive)
- `idx_{table}_city_state` - поиск по городу + штату
- `idx_{table}_lastname_firstname` - поиск по фамилии + имени
- `idx_{table}_address` - поиск по адресу (case-insensitive)
- `idx_{table}_zip` - поиск по ZIP коду

**Время выполнения:** ~10-30 минут на таблицу (зависит от размера)

## Схема базы данных

```sql
CREATE TABLE ssn_1 (
    id INTEGER PRIMARY KEY,
    firstname TEXT,
    lastname TEXT,
    middlename TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    zip TEXT,
    phone TEXT,
    ssn TEXT UNIQUE NOT NULL,
    dob TEXT,
    email TEXT
);
```

## Существующие индексы в ssn_1

- `sqlite_autoindex_ssn_1_1` - уникальный на ssn (автоматически)
- `idx_ssn_1_name_address` - firstname + lastname + address
- `idx_ssn_1_name_zip` - firstname + lastname + zip
- `idx_ssn_1_ssn` - ssn
- `idx_ssn_1_name_phone` - firstname + lastname + phone
- `idx_ssn_1_addr_dob_fname` - address + dob + firstname
- `idx_ssn_1_dob` - date of birth
- `idx_ssn_1_name_state` - firstname + lastname + state
- `idx_ssn_1_phone` - phone

## Процесс импорта данных

### Шаг 1: Предварительный просмотр
```bash
python3 scripts/preview_csv_data.py --rows 20 --analyze --sample-size 50000
```

### Шаг 2: Резервная копия базы (рекомендуется)
```bash
cp /root/soft/data/ssn_database.db /root/soft/data/ssn_database_backup_$(date +%Y%m%d_%H%M%S).db
```

### Шаг 3: Импорт данных
```bash
# Запустить импорт
python3 scripts/import_csv_data.py --table ssn_1 --batch-size 10000

# Мониторинг в реальном времени
# Скрипт выводит прогресс каждые 10,000 записей:
# INFO - Обработано: 10,000 | Вставлено: 9,847 | Пропущено: 153
```

### Шаг 4: Добавление индексов
```bash
python3 scripts/add_indexes.py --table ssn_1
```

### Шаг 5: Проверка результатов
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/soft/data/ssn_database.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM ssn_1')
print(f'Всего записей: {cursor.fetchone()[0]:,}')
conn.close()
"
```

## Обработка данных

### Парсинг имен
```
"RONALD DYMOND" → firstname="RONALD", lastname="DYMOND", middlename=""
"CINDY. GUITRON" → firstname="CINDY", lastname="GUITRON", middlename=""
"JOHN M SMITH" → firstname="JOHN", middlename="M", lastname="SMITH"
```

### Парсинг адресов
```
"170 SUMTER DR, MARIETTA GA" →
  address="170 SUMTER DR"
  city="MARIETTA"
  state="GA"
  zip=""

"39800 FREMONT BL, FMT CA 94538" →
  address="39800 FREMONT BL"
  city="FMT"
  state="CA"
  zip="94538"
```

### Нормализация SSN
```
"253497052" → "253-49-7052"
"253-49-7052" → "253-49-7052"
"*10000FqN6k+A=" → расшифровывается из ssn_mapping.csv (если --load-mappings)
```

### Нормализация телефонов
```
"7706932819" → "(770) 693-2819"
"770-693-2819" → "(770) 693-2819"
```

## Особенности импорта

### Дубликаты SSN
- По умолчанию используется `INSERT OR IGNORE`
- Записи с дублирующимся SSN пропускаются
- Используйте `--allow-duplicates` для изменения поведения

### Записи без SSN
- По умолчанию пропускаются (т.к. SSN - UNIQUE NOT NULL)
- ~27% записей в att_final.csv не имеют SSN

### Зашифрованные значения
- Значения начинающиеся с `*` считаются зашифрованными
- Используйте `--load-mappings` для расшифровки
- Без маппингов зашифрованные значения сохраняются как есть

### Производительность
- Batch size влияет на скорость: больше = быстрее, но больше памяти
- Оптимальный batch_size: 10000-50000
- Индексы создаются ПОСЛЕ импорта для скорости

## Мониторинг импорта

### Прогресс в реальном времени
```bash
# Скрипт выводит статистику каждые BATCH_SIZE записей
2025-12-01 12:00:00 - INFO - Обработано: 10,000 | Вставлено: 9,847 | Пропущено: 153
2025-12-01 12:00:15 - INFO - Обработано: 20,000 | Вставлено: 19,694 | Пропущено: 306
```

### Итоговая статистика
```
==================== ИМПОРТ ЗАВЕРШЕН ====================
Обработано строк: 88,320,018
Вставлено записей: 64,870,453
Пропущено записей: 23,449,565
Ошибок: 0
=========================================================
```

## Проверка данных

### Примеры записей
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/soft/data/ssn_database.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute('SELECT * FROM ssn_1 WHERE ssn = \"253-49-7052\"')
row = cursor.fetchone()
if row:
    print(dict(row))
conn.close()
"
```

### Статистика
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/soft/data/ssn_database.db')
cursor = conn.cursor()

# Всего записей
cursor.execute('SELECT COUNT(*) FROM ssn_1')
print(f'Всего: {cursor.fetchone()[0]:,}')

# С SSN
cursor.execute('SELECT COUNT(*) FROM ssn_1 WHERE ssn IS NOT NULL')
print(f'С SSN: {cursor.fetchone()[0]:,}')

# С email
cursor.execute('SELECT COUNT(*) FROM ssn_1 WHERE email IS NOT NULL')
print(f'С email: {cursor.fetchone()[0]:,}')

# С DOB
cursor.execute('SELECT COUNT(*) FROM ssn_1 WHERE dob IS NOT NULL')
print(f'С DOB: {cursor.fetchone()[0]:,}')

conn.close()
"
```

## Troubleshooting

### База данных заблокирована
```bash
# Найти процессы использующие базу
lsof /root/soft/data/ssn_database.db
# или
fuser /root/soft/data/ssn_database.db
```

### Недостаточно места
```bash
# Проверить свободное место (нужно ~50-100GB для импорта)
df -h /root/soft/data/
```

### Медленный импорт
- Увеличьте `--batch-size` до 50000
- Используйте SSD диск
- Убедитесь что база не используется другими процессами
- Не используйте `--load-mappings` если не нужно

### Ошибки памяти
- Уменьшите `--batch-size` до 5000
- Не используйте `--load-mappings` (маппинги занимают много памяти)

## Дополнительные ресурсы

- Полное руководство: [CSV_IMPORT_GUIDE.md](./CSV_IMPORT_GUIDE.md)
- Архитектура проекта: [CLAUDE.md](../CLAUDE.md)
- API документация: [README_API.md](../README_API.md)
