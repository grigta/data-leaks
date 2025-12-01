#!/usr/bin/env python3
"""
Скрипт для импорта CSV данных в SQLite базу данных.
Импортирует данные из att_final.csv с обработкой маппингов из dob_mapping.csv и ssn_mapping.csv
"""

import sqlite3
import csv
import re
import sys
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Константы
DB_PATH = '/root/soft/data/ssn_database.db'
ATT_FINAL_CSV = '/root/soft/newdata/att_final.csv'
DOB_MAPPING_CSV = '/root/soft/newdata/dob_mapping.csv'
SSN_MAPPING_CSV = '/root/soft/newdata/ssn_mapping.csv'
BATCH_SIZE = 10000  # Размер батча для вставки


def load_mapping(csv_path: str, key_col: str, value_col: str) -> Dict[str, str]:
    """
    Загрузить маппинг из CSV файла в память.

    Args:
        csv_path: Путь к CSV файлу
        key_col: Название колонки с ключом
        value_col: Название колонки со значением

    Returns:
        Словарь с маппингом
    """
    mapping = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row.get(key_col, '').strip()
                value = row.get(value_col, '').strip()
                if key:
                    mapping[key] = value
        logger.info(f"Загружено {len(mapping)} записей из {csv_path}")
    except Exception as e:
        logger.warning(f"Не удалось загрузить маппинг из {csv_path}: {e}")
    return mapping


def parse_name(full_name: str) -> Tuple[str, str, str]:
    """
    Разобрать полное имя на firstname, middlename, lastname.

    Args:
        full_name: Полное имя в формате "FIRSTNAME MIDDLENAME LASTNAME"

    Returns:
        Кортеж (firstname, middlename, lastname)
    """
    # Убираем точки и лишние пробелы
    clean_name = re.sub(r'\s+', ' ', full_name.replace('.', ' ')).strip()

    parts = clean_name.split()

    if len(parts) == 0:
        return '', '', ''
    elif len(parts) == 1:
        return parts[0], '', ''
    elif len(parts) == 2:
        return parts[0], '', parts[1]
    else:
        # Если частей больше 2, первая - firstname, последняя - lastname, остальное - middlename
        return parts[0], ' '.join(parts[1:-1]), parts[-1]


def parse_address(address_str: str) -> Tuple[str, str, str, str]:
    """
    Разобрать адрес на address, city, state, zip.

    Args:
        address_str: Строка адреса в формате "ADDRESS, CITY STATE" или "ADDRESS, CITY STATE ZIP"

    Returns:
        Кортеж (address, city, state, zip)
    """
    # Паттерн для адреса: "ADDRESS, CITY STATE ZIP" или "ADDRESS, CITY STATE"
    # Примеры:
    # "170 SUMTER DR, MARIETTA GA"
    # "39800 FREMONT BL, FMT CA 94538"

    if not address_str:
        return '', '', '', ''

    # Разделяем по запятой
    parts = address_str.split(',', 1)

    if len(parts) < 2:
        # Нет запятой, возвращаем весь адрес
        return address_str.strip(), '', '', ''

    address = parts[0].strip()
    city_state_zip = parts[1].strip()

    # Пытаемся извлечь ZIP (5 цифр в конце)
    zip_match = re.search(r'\b(\d{5})$', city_state_zip)
    zip_code = zip_match.group(1) if zip_match else ''

    if zip_code:
        city_state = city_state_zip[:zip_match.start()].strip()
    else:
        city_state = city_state_zip

    # Пытаемся извлечь STATE (2 заглавные буквы в конце или перед ZIP)
    state_match = re.search(r'\b([A-Z]{2})$', city_state)
    state = state_match.group(1) if state_match else ''

    if state:
        city = city_state[:state_match.start()].strip()
    else:
        city = city_state

    return address, city, state, zip_code


def normalize_ssn(ssn: str) -> str:
    """
    Нормализовать SSN в формат XXX-XX-XXXX.

    Args:
        ssn: SSN в любом формате

    Returns:
        Нормализованный SSN или пустая строка
    """
    if not ssn:
        return ''

    # Убираем все кроме цифр
    digits = re.sub(r'\D', '', ssn)

    if len(digits) == 9:
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"

    return ssn  # Возвращаем как есть если формат не стандартный


def normalize_phone(phone: str) -> str:
    """
    Нормализовать телефон.

    Args:
        phone: Номер телефона

    Returns:
        Нормализованный телефон
    """
    if not phone:
        return ''

    # Убираем все кроме цифр
    digits = re.sub(r'\D', '', phone)

    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"

    return phone


def create_import_indexes(cursor: sqlite3.Cursor, table_name: str):
    """
    Создать дополнительные индексы для оптимизации импорта и поиска.

    Args:
        cursor: Курсор SQLite
        table_name: Имя таблицы
    """
    logger.info(f"Создание дополнительных индексов для {table_name}...")

    # Индекс для email
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_email
        ON {table_name}(email COLLATE NOCASE)
    """)

    # Индекс для phone
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_phone
        ON {table_name}(phone)
    """)

    # Индекс для dob
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_dob
        ON {table_name}(dob)
    """)

    # Композитный индекс для city + state
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_city_state
        ON {table_name}(city COLLATE NOCASE, state)
    """)

    logger.info(f"Индексы для {table_name} созданы успешно")


def import_att_final(
    csv_path: str,
    db_path: str,
    table_name: str,
    dob_mapping: Optional[Dict[str, str]] = None,
    ssn_mapping: Optional[Dict[str, str]] = None,
    skip_duplicates: bool = True,
    batch_size: int = BATCH_SIZE
):
    """
    Импортировать данные из att_final.csv в SQLite базу.

    Args:
        csv_path: Путь к CSV файлу
        db_path: Путь к базе данных SQLite
        table_name: Имя таблицы для импорта
        dob_mapping: Маппинг для дат рождения (опционально)
        ssn_mapping: Маппинг для SSN (опционально)
        skip_duplicates: Пропускать дубликаты по SSN
        batch_size: Размер батча для вставки
    """
    logger.info(f"Начинаем импорт из {csv_path} в таблицу {table_name}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Отключаем автокоммит для ускорения
    cursor.execute("PRAGMA synchronous = OFF")
    cursor.execute("PRAGMA journal_mode = MEMORY")
    cursor.execute("PRAGMA cache_size = -64000")  # 64MB cache

    batch = []
    processed = 0
    inserted = 0
    skipped = 0
    errors = 0

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            for row in reader:
                try:
                    # Извлекаем данные
                    full_name = row.get('Name', '').strip()
                    phone1 = row.get('Phone1', '').strip()
                    phone2 = row.get('Phone2', '').strip()
                    ssn = row.get('SSN', '').strip()
                    dob = row.get('DOB', '').strip()
                    email = row.get('Email', '').strip()
                    address_full = row.get('Address', '').strip()

                    # Применяем маппинги если нужно
                    if dob_mapping and dob and dob.startswith('*'):
                        dob = dob_mapping.get(dob, dob)

                    if ssn_mapping and ssn and ssn.startswith('*'):
                        ssn = ssn_mapping.get(ssn, ssn)

                    # Пропускаем записи без SSN если требуется
                    if not ssn and skip_duplicates:
                        skipped += 1
                        processed += 1
                        continue

                    # Парсим имя
                    firstname, middlename, lastname = parse_name(full_name)

                    # Парсим адрес
                    address, city, state, zip_code = parse_address(address_full)

                    # Нормализуем телефон (берем первый если есть)
                    phone = normalize_phone(phone1 if phone1 else phone2)

                    # Нормализуем SSN
                    ssn = normalize_ssn(ssn)

                    # Добавляем в батч
                    batch.append((
                        firstname,
                        lastname,
                        middlename,
                        address,
                        city,
                        state,
                        zip_code,
                        phone,
                        ssn,
                        dob,
                        email
                    ))

                    processed += 1

                    # Вставляем батч
                    if len(batch) >= batch_size:
                        try:
                            if skip_duplicates:
                                cursor.executemany(f"""
                                    INSERT OR IGNORE INTO {table_name}
                                    (firstname, lastname, middlename, address, city, state, zip, phone, ssn, dob, email)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, batch)
                            else:
                                cursor.executemany(f"""
                                    INSERT INTO {table_name}
                                    (firstname, lastname, middlename, address, city, state, zip, phone, ssn, dob, email)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, batch)

                            inserted += cursor.rowcount
                            conn.commit()
                            logger.info(f"Обработано: {processed:,} | Вставлено: {inserted:,} | Пропущено: {skipped:,}")
                        except sqlite3.IntegrityError as e:
                            logger.warning(f"Ошибка целостности при вставке батча: {e}")
                            errors += 1

                        batch = []

                except Exception as e:
                    logger.error(f"Ошибка обработки строки {processed}: {e}")
                    errors += 1
                    continue

        # Вставляем оставшиеся записи
        if batch:
            try:
                if skip_duplicates:
                    cursor.executemany(f"""
                        INSERT OR IGNORE INTO {table_name}
                        (firstname, lastname, middlename, address, city, state, zip, phone, ssn, dob, email)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, batch)
                else:
                    cursor.executemany(f"""
                        INSERT INTO {table_name}
                        (firstname, lastname, middlename, address, city, state, zip, phone, ssn, dob, email)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, batch)

                inserted += cursor.rowcount
                conn.commit()
            except sqlite3.IntegrityError as e:
                logger.warning(f"Ошибка целостности при вставке последнего батча: {e}")
                errors += 1

        logger.info(f"""
        ==================== ИМПОРТ ЗАВЕРШЕН ====================
        Обработано строк: {processed:,}
        Вставлено записей: {inserted:,}
        Пропущено записей: {skipped:,}
        Ошибок: {errors}
        =========================================================
        """)

        # Создаем дополнительные индексы после импорта
        create_import_indexes(cursor, table_name)

        # Оптимизируем базу данных
        logger.info("Оптимизация базы данных...")
        cursor.execute("VACUUM")
        cursor.execute("ANALYZE")

        conn.commit()
        logger.info("Оптимизация завершена")

    except Exception as e:
        logger.error(f"Критическая ошибка при импорте: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()


def main():
    """Главная функция скрипта."""
    import argparse

    parser = argparse.ArgumentParser(description='Импорт CSV данных в SQLite базу')
    parser.add_argument(
        '--table',
        default='ssn_1',
        choices=['ssn_1', 'ssn_2'],
        help='Таблица для импорта (по умолчанию: ssn_1)'
    )
    parser.add_argument(
        '--csv',
        default=ATT_FINAL_CSV,
        help=f'Путь к CSV файлу (по умолчанию: {ATT_FINAL_CSV})'
    )
    parser.add_argument(
        '--db',
        default=DB_PATH,
        help=f'Путь к базе данных (по умолчанию: {DB_PATH})'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=BATCH_SIZE,
        help=f'Размер батча для вставки (по умолчанию: {BATCH_SIZE})'
    )
    parser.add_argument(
        '--load-mappings',
        action='store_true',
        help='Загрузить маппинги для SSN и DOB (замедляет импорт)'
    )
    parser.add_argument(
        '--allow-duplicates',
        action='store_true',
        help='Разрешить дубликаты SSN (по умолчанию пропускаются)'
    )

    args = parser.parse_args()

    # Загружаем маппинги если требуется
    dob_mapping = None
    ssn_mapping = None

    if args.load_mappings:
        logger.info("Загрузка маппингов...")
        dob_mapping = load_mapping(DOB_MAPPING_CSV, 'encrypted_value', 'decrypted_value')
        # SSN mapping очень большой, загружаем только если действительно нужно
        # ssn_mapping = load_mapping(SSN_MAPPING_CSV, 'Encrypted Value', 'SSN')

    # Проверяем существование файлов
    if not Path(args.csv).exists():
        logger.error(f"CSV файл не найден: {args.csv}")
        sys.exit(1)

    if not Path(args.db).exists():
        logger.error(f"База данных не найдена: {args.db}")
        logger.info("Сначала инициализируйте базу данных: python database/db_schema.py")
        sys.exit(1)

    # Запускаем импорт
    try:
        import_att_final(
            csv_path=args.csv,
            db_path=args.db,
            table_name=args.table,
            dob_mapping=dob_mapping,
            ssn_mapping=ssn_mapping,
            skip_duplicates=not args.allow_duplicates,
            batch_size=args.batch_size
        )
        logger.info("✓ Импорт успешно завершен!")
    except Exception as e:
        logger.error(f"✗ Импорт завершился с ошибкой: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
