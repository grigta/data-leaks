#!/usr/bin/env python3
"""
Fix Bloom Keys Script

Исправляет bloom_key_address для записей, где первая буква улицы была обрезана.
Затрагивает ~2.16M записей.

Использование:
    python scripts/fix_bloom_keys.py [--dry-run] [--batch-size 10000] [--max-records 1000000]
"""

import argparse
import logging
import sys
import os
import time

# Add shared directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
shared_dir = os.path.join(project_root, 'shared')
sys.path.insert(0, shared_dir)

from database.clickhouse_client import execute_query, execute_command
from database.bloom_key_generator import generate_bloom_key_address

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Паттерны неправильных bloom_key_address (первая буква обрезана)
WRONG_PATTERNS = [
    # S stripped
    ("address LIKE '%SOUTH%'", "bloom_key_address LIKE '%:outh:%'"),
    ("address LIKE '%SPRING%'", "bloom_key_address LIKE '%:pring:%'"),
    ("address LIKE '%SUNSET%'", "bloom_key_address LIKE '%:unset:%'"),
    ("address LIKE '%STONE%'", "bloom_key_address LIKE '%:tone:%'"),
    ("address LIKE '%STATE%'", "bloom_key_address LIKE '%:tate:%'"),
    ("address LIKE '%SUMMIT%'", "bloom_key_address LIKE '%:ummit:%'"),
    ("address LIKE '%SENECA%'", "bloom_key_address LIKE '%:eneca:%'"),
    ("address LIKE '%SMITH%'", "bloom_key_address LIKE '%:mith:%'"),
    ("address LIKE '%SHERIDAN%'", "bloom_key_address LIKE '%:heridan:%'"),
    ("address LIKE '%SHERMAN%'", "bloom_key_address LIKE '%:herman:%'"),
    ("address LIKE '%STANLEY%'", "bloom_key_address LIKE '%:tanley:%'"),
    ("address LIKE '%SIERRA%'", "bloom_key_address LIKE '%:ierra:%'"),
    ("address LIKE '%SYLVAN%'", "bloom_key_address LIKE '%:ylvan:%'"),
    ("address LIKE '%STERLING%'", "bloom_key_address LIKE '%:terling:%'"),
    ("address LIKE '%SYCAMORE%'", "bloom_key_address LIKE '%:ycamore:%'"),
    ("address LIKE '%SILVER%'", "bloom_key_address LIKE '%:ilver:%'"),
    ("address LIKE '%SOMERSET%'", "bloom_key_address LIKE '%:omerset:%'"),
    ("address LIKE '%SOUTHERN%'", "bloom_key_address LIKE '%:outhern:%'"),
    ("address LIKE '%STEWART%'", "bloom_key_address LIKE '%:tewart:%'"),
    ("address LIKE '%STUART%'", "bloom_key_address LIKE '%:tuart:%'"),
    ("address LIKE '%STANFORD%'", "bloom_key_address LIKE '%:tanford:%'"),
    ("address LIKE '%SANFORD%'", "bloom_key_address LIKE '%:anford:%'"),
    # N stripped
    ("address LIKE '%NORTH%'", "bloom_key_address LIKE '%:orth:%'"),
    ("address LIKE '%NOBLE%'", "bloom_key_address LIKE '%:oble:%'"),
    ("address LIKE '%NORMAN%'", "bloom_key_address LIKE '%:orman:%'"),
    ("address LIKE '%NEWPORT%'", "bloom_key_address LIKE '%:ewport:%'"),
    ("address LIKE '%NORTHERN%'", "bloom_key_address LIKE '%:orthern:%'"),
    ("address LIKE '%NEVADA%'", "bloom_key_address LIKE '%:evada:%'"),
    ("address LIKE '%NORFOLK%'", "bloom_key_address LIKE '%:orfolk:%'"),
    # E stripped
    ("address LIKE '%EAST%'", "bloom_key_address LIKE '%:ast:%'"),
    ("address LIKE '% ELM%'", "bloom_key_address LIKE '%:lm:%'"),
    ("address LIKE '%EAGLE%'", "bloom_key_address LIKE '%:agle:%'"),
    ("address LIKE '%EDGE%'", "bloom_key_address LIKE '%:dge:%'"),
    ("address LIKE '%EVANS%'", "bloom_key_address LIKE '%:vans:%'"),
    ("address LIKE '%ELMWOOD%'", "bloom_key_address LIKE '%:lmwood:%'"),
    ("address LIKE '%ELLIS%'", "bloom_key_address LIKE '%:llis:%'"),
    ("address LIKE '%EVERETT%'", "bloom_key_address LIKE '%:verett:%'"),
    ("address LIKE '%EASTERN%'", "bloom_key_address LIKE '%:astern:%'"),
    ("address LIKE '%ELIZABETH%'", "bloom_key_address LIKE '%:lizabeth:%'"),
    ("address LIKE '%ESSEX%'", "bloom_key_address LIKE '%:ssex:%'"),
    # W stripped
    ("address LIKE '%WEST%'", "bloom_key_address LIKE '%:est:%'"),
    ("address LIKE '%WASHINGTON%'", "bloom_key_address LIKE '%:ashington:%'"),
    ("address LIKE '%WILSON%'", "bloom_key_address LIKE '%:ilson:%'"),
    ("address LIKE '%WHITEHALL%'", "bloom_key_address LIKE '%:hitehall:%'"),
    ("address LIKE '% WOOD%'", "bloom_key_address LIKE '%:ood:%'"),
    ("address LIKE '%WALNUT%'", "bloom_key_address LIKE '%:alnut:%'"),
    ("address LIKE '%WILLOW%'", "bloom_key_address LIKE '%:illow:%'"),
    ("address LIKE '%WILLIAM%'", "bloom_key_address LIKE '%:illiam:%'"),
    ("address LIKE '%WESTERN%'", "bloom_key_address LIKE '%:estern:%'"),
    ("address LIKE '%WINDSOR%'", "bloom_key_address LIKE '%:indsor:%'"),
    ("address LIKE '%WARREN%'", "bloom_key_address LIKE '%:arren:%'"),
    ("address LIKE '%WOODLAND%'", "bloom_key_address LIKE '%:oodland:%'"),
    ("address LIKE '%WESTWOOD%'", "bloom_key_address LIKE '%:estwood:%'"),
    ("address LIKE '%WEBSTER%'", "bloom_key_address LIKE '%:ebster:%'"),
    ("address LIKE '%WHITNEY%'", "bloom_key_address LIKE '%:hitney:%'"),
    ("address LIKE '%WILSHIRE%'", "bloom_key_address LIKE '%:ilshire:%'"),
    ("address LIKE '%WILDWOOD%'", "bloom_key_address LIKE '%:ildwood:%'"),
]


def build_where_clause():
    """Строит WHERE clause для поиска неправильных записей."""
    conditions = []
    for addr_cond, bloom_cond in WRONG_PATTERNS:
        conditions.append(f"({addr_cond} AND {bloom_cond})")
    return " OR ".join(conditions)


def count_affected_records():
    """Считает количество затронутых записей."""
    where_clause = build_where_clause()
    query = f"""
    SELECT count(*) as cnt
    FROM ssn_database.ssn_data
    WHERE bloom_key_address != '' AND ({where_clause})
    """
    result = execute_query(query)
    return result[0]['cnt'] if result else 0


def get_pending_mutations():
    """Возвращает количество незавершённых мутаций."""
    query = """
    SELECT count() as cnt
    FROM system.mutations
    WHERE database = 'ssn_database' AND table = 'ssn_data' AND is_done = 0
    """
    result = execute_query(query)
    return result[0]['cnt'] if result else 0


def wait_for_mutations(max_pending: int = 100):
    """Ждёт пока количество мутаций не станет меньше max_pending."""
    while True:
        pending = get_pending_mutations()
        if pending < max_pending:
            return
        logger.info(f"Ожидание завершения мутаций: {pending} pending (max: {max_pending})")
        time.sleep(5)


def fix_bloom_keys(batch_size: int = 10000, max_records: int = None, dry_run: bool = False):
    """
    Исправляет bloom_key_address для затронутых записей.

    Args:
        batch_size: Размер батча для обработки
        max_records: Максимальное количество записей (None = все)
        dry_run: Только показать что будет сделано, не менять данные
    """
    where_clause = build_where_clause()

    # Считаем общее количество
    total_affected = count_affected_records()
    logger.info(f"Найдено {total_affected:,} записей с неправильным bloom_key_address")

    if total_affected == 0:
        logger.info("Нет записей для исправления")
        return

    if max_records:
        total_to_process = min(total_affected, max_records)
    else:
        total_to_process = total_affected

    logger.info(f"Будет обработано: {total_to_process:,} записей")

    if dry_run:
        logger.info("DRY RUN - данные не будут изменены")
        # Показываем примеры
        query = f"""
        SELECT id, firstname, lastname, address, state, bloom_key_address
        FROM ssn_database.ssn_data
        WHERE bloom_key_address != '' AND ({where_clause})
        LIMIT 5
        """
        examples = execute_query(query)
        logger.info("Примеры записей для исправления:")
        for rec in examples:
            new_key = generate_bloom_key_address(
                rec['firstname'], rec['lastname'], rec['address'], rec['state']
            )
            logger.info(f"  ID {rec['id']}: {rec['address']}")
            logger.info(f"    Было:  {rec['bloom_key_address']}")
            logger.info(f"    Будет: {new_key}")
        return

    # Обрабатываем батчами
    processed = 0
    fixed = 0
    errors = 0
    start_time = time.time()

    while processed < total_to_process:
        try:
            # Получаем батч записей
            query = f"""
            SELECT id, firstname, lastname, address, state, bloom_key_address
            FROM ssn_database.ssn_data
            WHERE bloom_key_address != '' AND ({where_clause})
            LIMIT {batch_size}
            """
            records = execute_query(query)

            if not records:
                break

            # Генерируем новые ключи
            updates = []
            for rec in records:
                new_key = generate_bloom_key_address(
                    rec['firstname'], rec['lastname'], rec['address'], rec['state']
                )
                if new_key and new_key != rec['bloom_key_address']:
                    # Escape single quotes
                    new_key_escaped = new_key.replace("'", "\\'")
                    updates.append((rec['id'], new_key_escaped))

            # Обновляем записи чанками по 1000 (ограничение max_query_size)
            chunk_size = 1000
            for i in range(0, len(updates), chunk_size):
                # Ждём если слишком много мутаций в очереди
                wait_for_mutations(max_pending=100)

                chunk = updates[i:i + chunk_size]
                if chunk:
                    case_parts = [f"WHEN id = {rid} THEN '{key}'" for rid, key in chunk]
                    ids = [str(rid) for rid, _ in chunk]
                    update_query = f"""
                    ALTER TABLE ssn_database.ssn_data
                    UPDATE bloom_key_address = CASE {' '.join(case_parts)} ELSE bloom_key_address END
                    WHERE id IN ({','.join(ids)})
                    """
                    execute_command(update_query)
                    fixed += len(chunk)

            processed += len(records)

            # Прогресс
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (total_to_process - processed) / rate if rate > 0 else 0

            logger.info(
                f"Прогресс: {processed:,}/{total_to_process:,} ({100*processed/total_to_process:.1f}%) "
                f"| Исправлено: {fixed:,} | Скорость: {rate:.0f} rec/s | ETA: {eta/60:.1f} мин"
            )

        except Exception as e:
            logger.error(f"Ошибка при обработке: {e}")
            errors += 1
            if errors > 10:
                logger.error("Слишком много ошибок, останавливаемся")
                break

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info(f"ЗАВЕРШЕНО")
    logger.info(f"  Обработано: {processed:,}")
    logger.info(f"  Исправлено: {fixed:,}")
    logger.info(f"  Ошибок: {errors}")
    logger.info(f"  Время: {elapsed/60:.1f} мин")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Fix bloom_key_address for affected records')
    parser.add_argument('--dry-run', action='store_true', help='Only show what would be done')
    parser.add_argument('--batch-size', type=int, default=10000, help='Batch size (default: 10000)')
    parser.add_argument('--max-records', type=int, default=None, help='Max records to process')
    parser.add_argument('--count-only', action='store_true', help='Only count affected records')

    args = parser.parse_args()

    if args.count_only:
        count = count_affected_records()
        print(f"Затронутых записей: {count:,}")
        return

    fix_bloom_keys(
        batch_size=args.batch_size,
        max_records=args.max_records,
        dry_run=args.dry_run
    )


if __name__ == '__main__':
    main()
