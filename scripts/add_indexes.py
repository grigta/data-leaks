#!/usr/bin/env python3
"""
Скрипт для добавления дополнительных индексов к существующей базе данных.
"""

import sqlite3
import logging
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = '/root/soft/data/ssn_database.db'


def add_additional_indexes(db_path: str, table_name: str):
    """
    Добавить дополнительные индексы для оптимизации поиска.

    Args:
        db_path: Путь к базе данных
        table_name: Имя таблицы
    """
    logger.info(f"Добавление дополнительных индексов для {table_name}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Проверяем существующие индексы
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='{table_name}'")
        existing_indexes = [row[0] for row in cursor.fetchall()]
        logger.info(f"Существующие индексы: {', '.join(existing_indexes)}")

        # Индекс для email (если нет)
        if f'idx_{table_name}_email' not in existing_indexes:
            logger.info(f"Создание индекса idx_{table_name}_email...")
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_email
                ON {table_name}(email COLLATE NOCASE)
            """)
            logger.info(f"✓ Индекс idx_{table_name}_email создан")
        else:
            logger.info(f"Индекс idx_{table_name}_email уже существует")

        # Композитный индекс для city + state (если нет)
        if f'idx_{table_name}_city_state' not in existing_indexes:
            logger.info(f"Создание индекса idx_{table_name}_city_state...")
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_city_state
                ON {table_name}(city COLLATE NOCASE, state)
            """)
            logger.info(f"✓ Индекс idx_{table_name}_city_state создан")
        else:
            logger.info(f"Индекс idx_{table_name}_city_state уже существует")

        # Композитный индекс для lastname + firstname (если нет)
        if f'idx_{table_name}_lastname_firstname' not in existing_indexes:
            logger.info(f"Создание индекса idx_{table_name}_lastname_firstname...")
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_lastname_firstname
                ON {table_name}(lastname COLLATE NOCASE, firstname COLLATE NOCASE)
            """)
            logger.info(f"✓ Индекс idx_{table_name}_lastname_firstname создан")
        else:
            logger.info(f"Индекс idx_{table_name}_lastname_firstname уже существует")

        # Индекс для address (если нет)
        if f'idx_{table_name}_address' not in existing_indexes:
            logger.info(f"Создание индекса idx_{table_name}_address...")
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_address
                ON {table_name}(address COLLATE NOCASE)
            """)
            logger.info(f"✓ Индекс idx_{table_name}_address создан")
        else:
            logger.info(f"Индекс idx_{table_name}_address уже существует")

        # Индекс для zip (если нет)
        if f'idx_{table_name}_zip' not in existing_indexes:
            logger.info(f"Создание индекса idx_{table_name}_zip...")
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_zip
                ON {table_name}(zip)
            """)
            logger.info(f"✓ Индекс idx_{table_name}_zip создан")
        else:
            logger.info(f"Индекс idx_{table_name}_zip уже существует")

        conn.commit()

        # Показываем финальный список индексов
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='{table_name}'")
        final_indexes = [row[0] for row in cursor.fetchall()]
        logger.info(f"\nФинальный список индексов для {table_name}:")
        for idx in final_indexes:
            logger.info(f"  - {idx}")

        # Оптимизируем базу
        logger.info("\nОптимизация базы данных...")
        cursor.execute("ANALYZE")
        conn.commit()
        logger.info("✓ Оптимизация завершена")

    except Exception as e:
        logger.error(f"Ошибка при создании индексов: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()


def main():
    """Главная функция."""
    import argparse

    parser = argparse.ArgumentParser(description='Добавление дополнительных индексов к базе данных')
    parser.add_argument(
        '--table',
        default='both',
        choices=['ssn_1', 'ssn_2', 'both'],
        help='Таблица для добавления индексов (по умолчанию: both)'
    )
    parser.add_argument(
        '--db',
        default=DB_PATH,
        help=f'Путь к базе данных (по умолчанию: {DB_PATH})'
    )

    args = parser.parse_args()

    try:
        if args.table == 'both':
            logger.info("Добавление индексов к обеим таблицам...")
            add_additional_indexes(args.db, 'ssn_1')
            add_additional_indexes(args.db, 'ssn_2')
        else:
            add_additional_indexes(args.db, args.table)

        logger.info("\n" + "="*80)
        logger.info("✓ Все индексы успешно добавлены!")
        logger.info("="*80)

    except Exception as e:
        logger.error(f"✗ Ошибка: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
