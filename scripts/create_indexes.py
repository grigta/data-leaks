#!/usr/bin/env python3
"""
Скрипт для создания оптимальных индексов в SQLite базе данных SSN.

Индексы оптимизируют следующие типы поиска:
1. Поиск по SSN (уже есть)
2. Поиск по имени + фамилии + ZIP (уже есть)
3. Поиск по имени + фамилии + адресу (уже есть)
4. Поиск по имени + фамилии + телефону (НОВЫЙ)
5. Поиск по адресу + DOB + имени (НОВЫЙ - для fallback)
6. Поиск по имени + фамилии + state (НОВЫЙ)
7. Поиск по DOB (НОВЫЙ)
8. Поиск по телефону (НОВЫЙ)
"""

import sqlite3
import time
from datetime import datetime

# Путь к базе данных
DB_PATH = '/app/data/ssn_database.db'

# Определяем индексы для создания
# Формат: (название_индекса, столбцы, описание)
NEW_INDEXES = [
    # Для поиска по телефону (Priority 1 в search_by_searchbug_data)
    ('idx_{table}_name_phone', 'firstname, lastname, phone',
     'Оптимизация поиска по имени + фамилии + телефону'),

    # Для fallback поиска (address + DOB + firstname)
    ('idx_{table}_addr_dob_fname', 'address, dob, firstname',
     'Оптимизация fallback поиска (разные фамилии)'),

    # Для поиска по имени + фамилии + state (Priority 4)
    ('idx_{table}_name_state', 'firstname, lastname, state',
     'Оптимизация поиска по имени + фамилии + state'),

    # Для фильтрации по DOB
    ('idx_{table}_dob', 'dob',
     'Оптимизация фильтрации по дате рождения'),

    # Для поиска по телефону (отдельный индекс)
    ('idx_{table}_phone', 'phone',
     'Оптимизация поиска по телефону'),
]


def check_index_exists(cursor, table_name, index_name):
    """Проверяет, существует ли индекс."""
    cursor.execute(f"PRAGMA index_list({table_name})")
    indexes = cursor.fetchall()
    return any(idx[1] == index_name for idx in indexes)


def get_table_size(cursor, table_name):
    """Получает количество записей в таблице."""
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0]


def create_index(cursor, table_name, index_name, columns, description):
    """Создает индекс с отслеживанием времени."""
    full_index_name = index_name.format(table=table_name)

    # Проверяем, существует ли индекс
    if check_index_exists(cursor, table_name, full_index_name):
        print(f"  ⏭️  Индекс {full_index_name} уже существует, пропускаем")
        return False

    print(f"\n  🔨 Создание: {full_index_name}")
    print(f"     Столбцы: {columns}")
    print(f"     Цель: {description}")

    # Создаем индекс с замером времени
    start_time = time.time()
    print(f"     Начало: {datetime.now().strftime('%H:%M:%S')}")

    try:
        cursor.execute(f"CREATE INDEX IF NOT EXISTS {full_index_name} ON {table_name} ({columns})")

        elapsed = time.time() - start_time
        print(f"     ✅ Готово за {elapsed:.1f}s")
        return True

    except Exception as e:
        print(f"     ❌ Ошибка: {e}")
        return False


def main():
    """Главная функция."""
    print("=" * 70)
    print("🚀 СОЗДАНИЕ ИНДЕКСОВ ДЛЯ ОПТИМИЗАЦИИ ПОИСКА SSN")
    print("=" * 70)

    # Подключаемся к базе данных
    print(f"\n📂 Подключение к базе: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Получаем размеры таблиц
    tables = ['ssn_1', 'ssn_2']
    table_sizes = {}

    print("\n📊 Размеры таблиц:")
    for table in tables:
        size = get_table_size(cursor, table)
        table_sizes[table] = size
        print(f"  • {table}: {size:,} записей")

    total_records = sum(table_sizes.values())
    print(f"  • ВСЕГО: {total_records:,} записей")

    # Создаем индексы для каждой таблицы
    total_created = 0
    total_skipped = 0

    for table in tables:
        print(f"\n{'=' * 70}")
        print(f"📋 Таблица: {table} ({table_sizes[table]:,} записей)")
        print(f"{'=' * 70}")

        for index_template, columns, description in NEW_INDEXES:
            created = create_index(cursor, table, index_template, columns, description)
            if created:
                total_created += 1
            else:
                total_skipped += 1

    # Сохраняем изменения
    print(f"\n{'=' * 70}")
    print("💾 Сохранение изменений...")
    conn.commit()
    print("✅ Изменения сохранены")

    # Итоговая статистика
    print(f"\n{'=' * 70}")
    print("📈 ИТОГОВАЯ СТАТИСТИКА")
    print(f"{'=' * 70}")
    print(f"  ✅ Создано новых индексов: {total_created}")
    print(f"  ⏭️  Пропущено (уже существуют): {total_skipped}")
    print(f"  📊 Всего индексов обработано: {total_created + total_skipped}")

    # Закрываем соединение
    conn.close()
    print(f"\n{'=' * 70}")
    print("✨ ГОТОВО!")
    print(f"{'=' * 70}")


if __name__ == '__main__':
    main()
