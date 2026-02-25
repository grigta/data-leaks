#!/usr/bin/env python3
"""Parallel search_keys migration using multiprocessing."""

import sys
sys.path.insert(0, '/app')

import logging
import time
import multiprocessing as mp
from typing import Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(process)d] %(message)s'
)
logger = logging.getLogger(__name__)

# Import after path setup
from database.clickhouse_client import execute_query, execute_command, get_connection
from database.search_key_generator import generate_search_keys


def process_range(args: Tuple[str, str, int, int, int]):
    """Process a range of IDs."""
    source_table, target_table, start_id, end_id, worker_id = args

    # Each worker needs its own connection
    import clickhouse_connect
    client = clickhouse_connect.get_client(
        host='clickhouse',
        port=8123,
        database='ssn_database',
        username='ssn_user',
        password='change_me_clickhouse_password'
    )

    def query(sql):
        return client.query(sql).result_rows

    def command(sql):
        client.command(sql)

    batch_size = 100000
    current_id = start_id
    processed = 0
    start_time = time.time()

    logger.info(f'Worker {worker_id}: Processing IDs {start_id:,} to {end_id:,}')

    while current_id < end_id:
        # Read batch
        rows = query(f"""
            SELECT id, firstname, middlename, lastname, dob, phone, address, state
            FROM {source_table}
            WHERE id > {current_id} AND id <= {end_id}
            ORDER BY id
            LIMIT {batch_size}
        """)

        if not rows:
            break

        # Generate keys and build INSERT
        values = []
        for r in rows:
            rid, fn, mn, ln, dob, phone, addr, state = r
            keys = generate_search_keys(
                firstname=fn or '',
                middlename=mn,
                lastname=ln or '',
                dob=dob,
                phone=phone,
                address=addr,
                state=state
            )

            vals = [str(rid)]
            for i in range(1, 9):
                k = keys[f'search_key_{i}'] or ''
                k = k.replace('\\', '\\\\').replace("'", "\\'")
                vals.append(f"'{k}'")
            values.append(f"({','.join(vals)})")

        # Insert in chunks
        chunk_size = 10000
        for i in range(0, len(values), chunk_size):
            chunk = values[i:i+chunk_size]
            command(f"INSERT INTO {target_table} VALUES {','.join(chunk)}")

        processed += len(rows)
        current_id = rows[-1][0]

        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        remaining = (end_id - current_id) / (current_id - start_id) * processed if current_id > start_id else 0
        eta_min = remaining / rate / 60 if rate > 0 else 0

        logger.info(f'Worker {worker_id}: {processed:,} done | {rate:.0f} rec/s | ETA: {eta_min:.0f}min')

    logger.info(f'Worker {worker_id}: COMPLETE - {processed:,} records')
    return processed


def main():
    # Get current state
    result = execute_query("SELECT max(id) FROM ssn_data")
    max_id = result[0]['max(id)'] if result else 0

    result = execute_query("SELECT COALESCE(max(id), 0) FROM ssn_search_keys")
    last_done = result[0]['COALESCE(max(id), 0)'] if result else 0

    logger.info(f'Max ID: {max_id:,}, Last done: {last_done:,}')

    # Split into 4 ranges
    remaining = max_id - last_done
    chunk = remaining // 4

    ranges = [
        ('ssn_data', 'ssn_search_keys', last_done, last_done + chunk, 1),
        ('ssn_data', 'ssn_search_keys', last_done + chunk, last_done + chunk * 2, 2),
        ('ssn_data', 'ssn_search_keys', last_done + chunk * 2, last_done + chunk * 3, 3),
        ('ssn_data', 'ssn_search_keys', last_done + chunk * 3, max_id + 1, 4),
    ]

    logger.info(f'Starting 4 parallel workers...')

    with mp.Pool(4) as pool:
        results = pool.map(process_range, ranges)

    total = sum(results)
    logger.info(f'=== SSN_DATA COMPLETE: {total:,} records ===')

    # Now do ssn_mutants
    result = execute_query("SELECT max(id) FROM ssn_mutants")
    max_id = result[0]['max(id)'] if result else 0

    # Create table if needed
    execute_command('DROP TABLE IF EXISTS ssn_mutants_search_keys')
    execute_command("""CREATE TABLE ssn_mutants_search_keys (
        id UInt64, search_key_1 String DEFAULT '', search_key_2 String DEFAULT '',
        search_key_3 String DEFAULT '', search_key_4 String DEFAULT '',
        search_key_5 String DEFAULT '', search_key_6 String DEFAULT '',
        search_key_7 String DEFAULT '', search_key_8 String DEFAULT ''
    ) ENGINE = MergeTree() ORDER BY id""")

    chunk = max_id // 4
    ranges = [
        ('ssn_mutants', 'ssn_mutants_search_keys', 0, chunk, 1),
        ('ssn_mutants', 'ssn_mutants_search_keys', chunk, chunk * 2, 2),
        ('ssn_mutants', 'ssn_mutants_search_keys', chunk * 2, chunk * 3, 3),
        ('ssn_mutants', 'ssn_mutants_search_keys', chunk * 3, max_id + 1, 4),
    ]

    logger.info(f'Starting ssn_mutants migration with 4 workers...')

    with mp.Pool(4) as pool:
        results = pool.map(process_range, ranges)

    total = sum(results)
    logger.info(f'=== SSN_MUTANTS COMPLETE: {total:,} records ===')
    logger.info('=== ALL DONE ===')


if __name__ == '__main__':
    mp.set_start_method('spawn')
    main()
