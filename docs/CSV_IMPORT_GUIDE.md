# Руководство по импорту CSV данных

Это руководство описывает процесс импорта данных из CSV файлов в SQLite базу данных.

## Обзор данных

В директории `/root/soft/newdata/` находятся следующие файлы:

- **att_final.csv** (~88M записей) - основной файл с данными о пользователях
- **dob_mapping.csv** (~43K записей) - маппинг зашифрованных дат рождения
- **ssn_mapping.csv** (~44M записей) - маппинг зашифрованных SSN

### Структура att_final.csv

Поля в CSV файле:
- `Name` - полное имя (FIRSTNAME LASTNAME или FIRSTNAME MIDDLENAME LASTNAME)
- `Phone1`, `Phone2` - номера телефонов
- `SSN` - Social Security Number (может быть пустым или зашифрованным с префиксом `*`)
- `DOB` - дата рождения (может быть пустой или зашифрованной с префиксом `*`)
- `Email` - email адрес
- `Address` - полный адрес в формате "ADDRESS, CITY STATE ZIP"

### Статистика данных (на выборке 50K записей)

- **73.4%** записей имеют SSN (только ~1% зашифрованных)
- **98.2%** записей имеют DOB (~6% зашифрованных)
- **100%** записей имеют Email, Phone и Address

## Скрипты для работы с данными

### 1. Предварительный просмотр данных

**scripts/preview_csv_data.py** - просмотр и анализ CSV данных перед импортом

```bash
# Просмотр первых 10 записей
python3 scripts/preview_csv_data.py --rows 10

# Просмотр с анализом статистики
python3 scripts/preview_csv_data.py --rows 20 --analyze --sample-size 100000

# Справка
python3 scripts/preview_csv_data.py --help
```

**Параметры:**
- `--csv PATH` - путь к CSV файлу (по умолчанию: /root/soft/newdata/att_final.csv)
- `--rows N` - количество строк для просмотра (по умолчанию: 20)
- `--analyze` - показать статистику данных
- `--sample-size N` - размер выборки для анализа (по умолчанию: 10000)

### 2. Импорт данных

**scripts/import_csv_data.py** - импорт CSV данных в SQLite базу

```bash
# Базовый импорт в таблицу ssn_1 (пропускает дубликаты)
python3 scripts/import_csv_data.py

# Импорт в таблицу ssn_2
python3 scripts/import_csv_data.py --table ssn_2

# Импорт с кастомным размером батча
python3 scripts/import_csv_data.py --batch-size 50000

# Импорт с загрузкой маппингов (замедляет процесс)
python3 scripts/import_csv_data.py --load-mappings

# Импорт с разрешением дубликатов
python3 scripts/import_csv_data.py --allow-duplicates

# Справка
python3 scripts/import_csv_data.py --help
```

**Параметры:**
- `--table {ssn_1,ssn_2}` - таблица для импорта (по умолчанию: ssn_1)
- `--csv PATH` - путь к CSV файлу
- `--db PATH` - путь к базе данных
- `--batch-size N` - размер батча для вставки (по умолчанию: 10000)
- `--load-mappings` - загрузить маппинги для зашифрованных данных
- `--allow-duplicates` - разрешить дубликаты SSN

**Что делает скрипт:**
1. Парсит полное имя на firstname, middlename, lastname
2. Парсит адрес на address, city, state, zip
3. Нормализует SSN в формат XXX-XX-XXXX
4. Нормализует телефон в формат (XXX) XXX-XXXX
5. Применяет маппинги для зашифрованных значений (если `--load-mappings`)
6. Вставляет данные батчами для производительности
7. Создает дополнительные индексы после импорта
8. Оптимизирует базу данных (VACUUM, ANALYZE)

### 3. Добавление индексов

**scripts/add_indexes.py** - добавление дополнительных индексов к существующей базе

```bash
# Добавить индексы к обеим таблицам
python3 scripts/add_indexes.py

# Добавить индексы только к ssn_1
python3 scripts/add_indexes.py --table ssn_1

# Справка
python3 scripts/add_indexes.py --help
```

**Создаваемые индексы:**
- `idx_{table}_email` - индекс на email (case-insensitive)
- `idx_{table}_city_state` - композитный индекс на city + state
- `idx_{table}_lastname_firstname` - композитный индекс на lastname + firstname
- `idx_{table}_address` - индекс на address (case-insensitive)
- `idx_{table}_zip` - индекс на zip code

## Схема базы данных

### Таблицы: ssn_1, ssn_2

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

### Существующие индексы

Базовые индексы (создаются при инициализации):
- `sqlite_autoindex_{table}_1` - уникальный индекс на ssn
- `idx_{table}_name_address` - firstname + lastname + address
- `idx_{table}_name_zip` - firstname + lastname + zip
- `idx_{table}_ssn` - ssn

Дополнительные индексы (могут быть созданы):
- `idx_{table}_name_phone` - firstname + lastname + phone
- `idx_{table}_addr_dob_fname` - address + dob + firstname
- `idx_{table}_dob` - date of birth
- `idx_{table}_name_state` - firstname + lastname + state
- `idx_{table}_phone` - phone
- `idx_{table}_email` - email
- `idx_{table}_city_state` - city + state
- `idx_{table}_lastname_firstname` - lastname + firstname
- `idx_{table}_address` - address
- `idx_{table}_zip` - zip code

## Рекомендуемый процесс импорта

### Шаг 1: Предварительный просмотр

```bash
# Посмотрите как будут выглядеть данные после обработки
python3 scripts/preview_csv_data.py --rows 20 --analyze --sample-size 50000
```

### Шаг 2: Проверка базы данных

```bash
# Проверьте текущее состояние базы
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/soft/data/ssn_database.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM ssn_1')
print(f'Записей в ssn_1: {cursor.fetchone()[0]:,}')
cursor.execute('SELECT COUNT(*) FROM ssn_2')
print(f'Записей в ssn_2: {cursor.fetchone()[0]:,}')
conn.close()
"
```

### Шаг 3: Резервная копия (рекомендуется)

```bash
# Создайте резервную копию базы данных перед импортом
cp /root/soft/data/ssn_database.db /root/soft/data/ssn_database_backup_$(date +%Y%m%d_%H%M%S).db
```

### Шаг 4: Импорт данных

```bash
# Запустите импорт (это может занять несколько часов для 88M записей)
python3 scripts/import_csv_data.py --table ssn_1 --batch-size 10000

# Мониторинг прогресса в логах
# Скрипт выводит статистику каждые 10,000 записей
```

### Шаг 5: Добавление индексов

```bash
# Добавьте дополнительные индексы для оптимизации поиска
python3 scripts/add_indexes.py --table ssn_1
```

### Шаг 6: Проверка результатов

```bash
# Проверьте сколько записей импортировано
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/soft/data/ssn_database.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM ssn_1')
print(f'Всего записей: {cursor.fetchone()[0]:,}')
cursor.execute('SELECT COUNT(*) FROM ssn_1 WHERE ssn IS NOT NULL AND ssn != \"\"')
print(f'Записей с SSN: {cursor.fetchone()[0]:,}')
cursor.execute('SELECT COUNT(*) FROM ssn_1 WHERE email IS NOT NULL AND email != \"\"')
print(f'Записей с Email: {cursor.fetchone()[0]:,}')
conn.close()
"
```

## Производительность

### Ожидаемое время импорта

При импорте 88M записей с batch_size=10000:
- **Без маппингов**: ~2-4 часа (зависит от диска)
- **С маппингами**: ~4-8 часов (дополнительные lookups)

### Оптимизация производительности

1. **Увеличьте batch_size** для более быстрого импорта:
   ```bash
   python3 scripts/import_csv_data.py --batch-size 50000
   ```

2. **Используйте SSD** для базы данных если возможно

3. **Не загружайте маппинги** если большинство данных уже расшифрованы:
   ```bash
   python3 scripts/import_csv_data.py  # без --load-mappings
   ```

4. **Создавайте индексы после импорта**, а не до (это делается автоматически)

## Обработка ошибок

### Ошибки дубликатов SSN

По умолчанию скрипт использует `INSERT OR IGNORE` и пропускает дубликаты.
Если хотите видеть ошибки:
```bash
python3 scripts/import_csv_data.py --allow-duplicates
```

### Записи без SSN

По умолчанию записи без SSN пропускаются. Для их импорта добавьте `--allow-duplicates`.

### Мониторинг импорта

Скрипт выводит прогресс каждые 10,000 записей:
```
2025-12-01 12:00:00 - INFO - Обработано: 10,000 | Вставлено: 9,847 | Пропущено: 153
2025-12-01 12:00:15 - INFO - Обработано: 20,000 | Вставлено: 19,694 | Пропущено: 306
...
```

## Работа с маппингами

### Когда использовать маппинги

Используйте `--load-mappings` если:
- Видите много зашифрованных значений (начинаются с `*`)
- Нужно расшифровать SSN или DOB
- Готовы ждать дольше для полных данных

### Формат маппингов

**dob_mapping.csv:**
```csv
encrypted_value,decrypted_value
*0sUMi0uCwiXIOitMI6mgWAQ==,1900-01-01
```

**ssn_mapping.csv:**
```csv
Encrypted Value,SSN
*10000FqN6k+A=,435-55-5236
```

## Проверка данных после импорта

```bash
# Примеры записей
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/soft/data/ssn_database.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute('SELECT * FROM ssn_1 LIMIT 5')
for row in cursor.fetchall():
    print(dict(row))
conn.close()
"
```

## Troubleshooting

### База данных заблокирована

```bash
# Проверьте нет ли других процессов использующих базу
lsof /root/soft/data/ssn_database.db
```

### Недостаточно места на диске

```bash
# Проверьте свободное место (база может вырасти на 50-100GB)
df -h /root/soft/data/
```

### Медленный импорт

- Увеличьте `--batch-size`
- Убедитесь что используете SSD
- Отключите антивирусные сканеры
- Убедитесь что создание индексов происходит после импорта

## Дополнительная информация

- Архитектура проекта: [CLAUDE.md](../CLAUDE.md)
- API документация: [README_API.md](../README_API.md)
- Deployment: [DEPLOYMENT.md](../DEPLOYMENT.md)
