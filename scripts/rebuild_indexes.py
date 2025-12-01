#!/usr/bin/env python3
"""
Скрипт для пересоздания индексов SQLite базы данных.

Этот скрипт удаляет старые индексы и создает новые индексы с COLLATE NOCASE
для оптимизации поиска без учета регистра. Используется для исправления
производительности поиска после обновления схемы индексов.

Использование:
    python scripts/rebuild_indexes.py [--db-path PATH] [--vacuum]

Опции:
    --db-path PATH    Путь к SQLite базе данных (по умолчанию: /root/soft/data/ssn_database.db)
    --vacuum          Выполнить VACUUM после пересоздания индексов для оптимизации БД
"""

import sqlite3
import argparse
import logging
import time
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Константы
DEFAULT_DB_PATH = '/root/soft/data/ssn_database.db'
TABLES = ['ssn_1', 'ssn_2']


def validate_table_name(table_name):
    """
    Проверка что имя таблицы допустимо.

    Args:
        table_name: Имя таблицы для проверки

    Raises:
        ValueError: Если имя таблицы не в списке допустимых
    """
    if table_name not in TABLES:
        raise ValueError(f"Invalid table name: {table_name}. Allowed: {TABLES}")


def rebuild_table_indexes(cursor, table_name):
    """
    Пересоздать индексы для указанной таблицы.

    Args:
        cursor: SQLite cursor object
        table_name: Имя таблицы для пересоздания индексов

    Returns:
        int: Количество пересозданных индексов
    """
    validate_table_name(table_name)

    # Список ВСЕХ старых индексов для удаления (9 индексов)
    old_indexes = [
        f'idx_{table_name}_name_zip',
        f'idx_{table_name}_name_state',
        f'idx_{table_name}_name',
        f'idx_{table_name}_email',
        f'idx_{table_name}_ssn_last4',
        f'idx_{table_name}_phone',
        f'idx_{table_name}_zip',
        f'idx_{table_name}_city',
        f'idx_{table_name}_dob'
    ]

    logger.info(f"Пересоздание индексов для таблицы {table_name}...")

    # Удаление ВСЕХ старых индексов
    logger.info(f"  Удаление {len(old_indexes)} старых индексов...")
    for index_name in old_indexes:
        try:
            cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
            logger.info(f"    ✓ Удален: {index_name}")
        except Exception as e:
            logger.warning(f"    ✗ Ошибка при удалении {index_name}: {e}")

    # Создание ТОЛЬКО 3 новых индексов
    logger.info(f"  Создание 3 новых индексов...")

    new_indexes = [
        {
            'name': f'idx_{table_name}_name_address',
            'sql': f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_name_address
                ON {table_name}(firstname COLLATE NOCASE, lastname COLLATE NOCASE, address COLLATE NOCASE)
            """,
            'description': 'firstname + lastname + address'
        },
        {
            'name': f'idx_{table_name}_name_zip',
            'sql': f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_name_zip
                ON {table_name}(firstname COLLATE NOCASE, lastname COLLATE NOCASE, zip)
            """,
            'description': 'firstname + lastname + zip'
        },
        {
            'name': f'idx_{table_name}_ssn',
            'sql': f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_ssn
                ON {table_name}(ssn)
            """,
            'description': 'ssn'
        }
    ]

    created_count = 0
    for index_def in new_indexes:
        try:
            cursor.execute(index_def['sql'])
            created_count += 1
            logger.info(f"    ✓ Создан: {index_def['name']} ({index_def['description']})")
        except Exception as e:
            logger.error(f"    ✗ Ошибка при создании {index_def['name']}: {e}")

    return created_count


def rebuild_all_indexes(db_path, vacuum=False):
    """
    Пересоздать все индексы в базе данных.

    Args:
        db_path: Путь к SQLite базе данных
        vacuum: Выполнить ли VACUUM после пересоздания индексов

    Returns:
        bool: True если успешно, False в случае ошибки
    """
    start_time = time.time()

    # Проверка что файл базы данных существует
    db_file = Path(db_path)
    if not db_file.exists():
        logger.error(f"Файл базы данных не найден: {db_path}")
        return False

    logger.info(f"Подключение к базе данных: {db_path}")

    try:
        # Подключение к базе данных
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Пересоздать индексы для каждой таблицы
        total_indexes = 0
        for table_name in TABLES:
            try:
                count = rebuild_table_indexes(cursor, table_name)
                total_indexes += count
            except Exception as e:
                logger.error(f"Ошибка при обработке таблицы {table_name}: {e}")
                continue

        # Обновить статистику запросов
        logger.info("Обновление статистики запросов (ANALYZE)...")
        cursor.execute("ANALYZE")

        # Зафиксировать изменения
        conn.commit()

        # VACUUM для оптимизации базы данных (опционально)
        if vacuum:
            logger.info("Выполнение VACUUM для оптимизации базы данных...")
            logger.warning("VACUUM может занять продолжительное время для больших БД")
            cursor.execute("VACUUM")

        # Закрыть соединение
        cursor.close()
        conn.close()

        elapsed_time = time.time() - start_time
        logger.info(f"✓ Успешно пересоздано {total_indexes} индексов")
        logger.info(f"✓ Время выполнения: {elapsed_time:.2f} секунд")

        return True

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        return False


def main():
    """
    Главная функция для запуска скрипта из командной строки.
    """
    parser = argparse.ArgumentParser(
        description='Пересоздание индексов SQLite базы данных для оптимизации поиска',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Пересоздать индексы в базе данных по умолчанию
  python scripts/rebuild_indexes.py

  # Указать путь к базе данных
  python scripts/rebuild_indexes.py --db-path /path/to/database.db

  # Выполнить VACUUM после пересоздания индексов
  python scripts/rebuild_indexes.py --vacuum

Этот скрипт создает индексы с COLLATE NOCASE для оптимизации
поиска без учета регистра. Используйте после обновления схемы
индексов или при проблемах с производительностью поиска.
        """
    )

    parser.add_argument(
        '--db-path',
        default=DEFAULT_DB_PATH,
        help=f'Путь к SQLite базе данных (по умолчанию: {DEFAULT_DB_PATH})'
    )

    parser.add_argument(
        '--vacuum',
        action='store_true',
        help='Выполнить VACUUM после пересоздания индексов (оптимизация БД)'
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("Скрипт пересоздания индексов SQLite базы данных")
    logger.info("=" * 70)

    # Выполнить пересоздание индексов
    success = rebuild_all_indexes(args.db_path, args.vacuum)

    if success:
        logger.info("=" * 70)
        logger.info("✓ Пересоздание индексов завершено успешно")
        logger.info("=" * 70)
        return 0
    else:
        logger.error("=" * 70)
        logger.error("✗ Пересоздание индексов завершилось с ошибками")
        logger.error("=" * 70)
        return 1


if __name__ == '__main__':
    exit(main())
