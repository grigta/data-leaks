#!/usr/bin/env python3
"""
Gradual migration script for search_keys with mutation waiting.
Processes small batches and waits for mutations to complete.
"""

import sys
import time
import logging

sys.path.insert(0, '/app')

from database.clickhouse_client import execute_query, execute_command
from database.search_key_generator import generate_search_keys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def wait_for_mutations(table: str, max_wait: int = 300) -> bool:
    """Wait for all mutations on table to complete."""
    start = time.time()
    while True:
        result = execute_query(f"""
            SELECT count() as pending
            FROM system.mutations
            WHERE is_done = 0 AND table = '{table}'
        """)
        pending = result[0]['pending'] if result else 0

        if pending == 0:
            return True

        elapsed = time.time() - start
        if elapsed > max_wait:
            logger.warning(f"Timeout waiting for {pending} mutations after {max_wait}s")
            return False

        logger.debug(f"Waiting for {pending} mutations... ({int(elapsed)}s)")
        time.sleep(5)


def process_batch(table: str, offset: int, batch_size: int) -> dict:
    """Process a single batch of records."""
    # Read records
    query = f"""
        SELECT id, firstname, middlename, lastname, dob, phone, address, state
        FROM {table}
        ORDER BY id
        LIMIT {batch_size}
        OFFSET {offset}
    """
    records = execute_query(query)

    if not records:
        return {'processed': 0, 'keys': {}}

    # Generate keys
    updates = {f'search_key_{i}': [] for i in range(1, 9)}

    for record in records:
        keys = generate_search_keys(
            firstname=record.get('firstname', ''),
            middlename=record.get('middlename'),
            lastname=record.get('lastname', ''),
            dob=record.get('dob'),
            phone=record.get('phone'),
            address=record.get('address'),
            state=record.get('state')
        )

        record_id = record['id']
        for i in range(1, 9):
            key = keys[f'search_key_{i}']
            if key:
                updates[f'search_key_{i}'].append((record_id, key))

    # Apply updates for each key column separately
    keys_count = {}
    for key_col, values in updates.items():
        if not values:
            keys_count[key_col] = 0
            continue

        # Build UPDATE with multiIf
        cases = ', '.join([f"id = {rid}, '{val}'" for rid, val in values])
        ids = ', '.join([str(rid) for rid, _ in values])

        update_query = f"""
            ALTER TABLE {table}
            UPDATE {key_col} = multiIf({cases}, {key_col})
            WHERE id IN ({ids})
            SETTINGS mutations_sync = 1
        """

        try:
            execute_command(update_query)
            keys_count[key_col] = len(values)
        except Exception as e:
            logger.error(f"Error updating {key_col}: {e}")
            keys_count[key_col] = 0

    return {'processed': len(records), 'keys': keys_count}


def migrate_table(table: str, batch_size: int = 500, start_offset: int = 0):
    """Migrate a table with gradual processing."""
    # Get total count
    result = execute_query(f"SELECT count() as cnt FROM {table}")
    total = result[0]['cnt'] if result else 0

    logger.info(f"Starting migration for {table}: {total:,} records")
    logger.info(f"Batch size: {batch_size}, starting offset: {start_offset}")

    offset = start_offset
    total_processed = 0
    total_keys = {f'search_key_{i}': 0 for i in range(1, 9)}
    batch_num = 0

    while offset < total:
        batch_num += 1
        start_time = time.time()

        # Wait for any pending mutations first
        wait_for_mutations(table, max_wait=60)

        # Process batch
        result = process_batch(table, offset, batch_size)

        if result['processed'] == 0:
            break

        total_processed += result['processed']
        for k, v in result['keys'].items():
            total_keys[k] += v

        elapsed = time.time() - start_time
        progress = (offset + result['processed']) / total * 100

        logger.info(
            f"Batch {batch_num}: {result['processed']} records in {elapsed:.1f}s | "
            f"Progress: {offset + result['processed']:,}/{total:,} ({progress:.1f}%)"
        )

        offset += batch_size

        # Small delay between batches
        time.sleep(1)

    logger.info(f"\n=== {table} Migration Complete ===")
    logger.info(f"Total processed: {total_processed:,}")
    for k, v in total_keys.items():
        logger.info(f"  {k}: {v:,}")

    return {'total_processed': total_processed, 'keys': total_keys}


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--table', default='ssn_data')
    parser.add_argument('--batch-size', type=int, default=500)
    parser.add_argument('--start-offset', type=int, default=0)
    args = parser.parse_args()

    migrate_table(args.table, args.batch_size, args.start_offset)
