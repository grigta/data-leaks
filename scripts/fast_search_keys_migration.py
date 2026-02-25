#!/usr/bin/env python3
"""Fast search_keys migration via INSERT (no mutations)."""

import sys
sys.path.insert(0, '/app')

import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/search_keys_fast.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from database.clickhouse_client import execute_query, execute_command
from database.search_key_generator import generate_search_keys


def insert_batch(target_table, records):
    """Insert batch of records with generated search keys."""
    if not records:
        return 0

    values = []
    for r in records:
        keys = generate_search_keys(
            firstname=r.get('firstname', ''),
            middlename=r.get('middlename'),
            lastname=r.get('lastname', ''),
            dob=r.get('dob'),
            phone=r.get('phone'),
            address=r.get('address'),
            state=r.get('state')
        )

        vals = [str(r['id'])]
        for i in range(1, 9):
            k = keys[f'search_key_{i}'] or ''
            # Escape for ClickHouse
            k = k.replace('\\', '\\\\').replace("'", "\\'")
            vals.append(f"'{k}'")

        values.append(f"({','.join(vals)})")

    # Insert in chunks to avoid query size limits
    chunk_size = 5000
    for i in range(0, len(values), chunk_size):
        chunk = values[i:i+chunk_size]
        insert = f"INSERT INTO {target_table} VALUES {','.join(chunk)}"
        execute_command(insert)

    return len(records)


def migrate_table(source_table, target_table, batch_size=50000):
    """Migrate a table to search_keys table."""
    result = execute_query(f"SELECT count() as cnt FROM {source_table}")
    total = result[0]['cnt'] if result else 0

    result = execute_query(f"SELECT max(id) as max_id FROM {target_table}")
    last_id = result[0]['max_id'] if result and result[0]['max_id'] else 0

    logger.info(f'=== Migrating {source_table} -> {target_table} ===')
    logger.info(f'Total: {total:,}, Last ID: {last_id:,}')

    offset = 0
    if last_id > 0:
        result = execute_query(f"SELECT count() as cnt FROM {source_table} WHERE id <= {last_id}")
        offset = result[0]['cnt'] if result else 0
        logger.info(f'Resuming from offset {offset:,}')

    batches = 0
    processed = 0
    start_time = time.time()

    while True:
        records = execute_query(f"""
            SELECT id, firstname, middlename, lastname, dob, phone, address, state
            FROM {source_table}
            WHERE id > {last_id}
            ORDER BY id
            LIMIT {batch_size}
        """)

        if not records:
            break

        n = insert_batch(target_table, records)
        processed += n
        batches += 1
        last_id = records[-1]['id']

        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        progress = (offset + processed) / total * 100
        eta_hours = (total - offset - processed) / rate / 3600 if rate > 0 else 0

        logger.info(
            f'Batch {batches}: {offset+processed:,}/{total:,} ({progress:.1f}%) | '
            f'{rate:.0f} rec/s | ETA: {eta_hours:.1f}h'
        )

    logger.info(f'=== {source_table} COMPLETE: {processed:,} records ===')
    return processed


def main():
    # Recreate ssn_search_keys table
    logger.info('Recreating ssn_search_keys table...')
    execute_command('DROP TABLE IF EXISTS ssn_search_keys')
    execute_command("""
        CREATE TABLE ssn_search_keys (
            id UInt64,
            search_key_1 String DEFAULT '',
            search_key_2 String DEFAULT '',
            search_key_3 String DEFAULT '',
            search_key_4 String DEFAULT '',
            search_key_5 String DEFAULT '',
            search_key_6 String DEFAULT '',
            search_key_7 String DEFAULT '',
            search_key_8 String DEFAULT ''
        ) ENGINE = MergeTree()
        ORDER BY id
        SETTINGS index_granularity = 8192
    """)

    # Migrate ssn_data
    migrate_table('ssn_data', 'ssn_search_keys', batch_size=50000)

    # Recreate ssn_mutants_search_keys table
    logger.info('Recreating ssn_mutants_search_keys table...')
    execute_command('DROP TABLE IF EXISTS ssn_mutants_search_keys')
    execute_command("""
        CREATE TABLE ssn_mutants_search_keys (
            id UInt64,
            search_key_1 String DEFAULT '',
            search_key_2 String DEFAULT '',
            search_key_3 String DEFAULT '',
            search_key_4 String DEFAULT '',
            search_key_5 String DEFAULT '',
            search_key_6 String DEFAULT '',
            search_key_7 String DEFAULT '',
            search_key_8 String DEFAULT ''
        ) ENGINE = MergeTree()
        ORDER BY id
        SETTINGS index_granularity = 8192
    """)

    # Migrate ssn_mutants
    migrate_table('ssn_mutants', 'ssn_mutants_search_keys', batch_size=50000)

    logger.info('=== ALL MIGRATIONS COMPLETE ===')


if __name__ == '__main__':
    main()
