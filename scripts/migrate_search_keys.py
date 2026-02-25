#!/usr/bin/env python3
"""
Migration script for populating search_key_1-8 columns in ClickHouse.

Uses INSERT SELECT approach instead of ALTER TABLE UPDATE for better performance
on large datasets (437M+ records).

Approach:
1. Create temp table with same structure + search_keys
2. INSERT SELECT in batches, generating keys via Python
3. Swap tables at the end

Usage:
    python migrate_search_keys.py --table ssn_data --batch-size 100000
"""

import argparse
import logging
import sys
import time
from typing import Dict, List, Optional, Tuple

# Add shared to path
sys.path.insert(0, '/app')

from database.clickhouse_client import execute_query, execute_command, get_connection
from database.search_key_generator import generate_search_keys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_table_count(table: str) -> int:
    """Get total record count for table."""
    result = execute_query(f"SELECT count() as cnt FROM {table}")
    return result[0]['cnt'] if result else 0


def get_columns(table: str) -> List[str]:
    """Get column names for table."""
    result = execute_query(f"DESCRIBE TABLE {table}")
    return [row['name'] for row in result]


def wait_for_mutations(table: str, max_wait_seconds: int = 300) -> bool:
    """Wait for all mutations on table to complete."""
    logger.info(f"Waiting for mutations on {table} to complete...")
    start = time.time()

    while True:
        result = execute_query(f"""
            SELECT count() as pending
            FROM system.mutations
            WHERE is_done = 0 AND table = '{table}'
        """)
        pending = result[0]['pending'] if result else 0

        if pending == 0:
            logger.info(f"All mutations completed for {table}")
            return True

        elapsed = time.time() - start
        if elapsed > max_wait_seconds:
            logger.warning(f"Timeout waiting for mutations: {pending} still pending")
            return False

        logger.info(f"Waiting for {pending} mutations... ({int(elapsed)}s elapsed)")
        time.sleep(10)


def process_batch_direct(
    table: str,
    offset: int,
    batch_size: int,
    columns: List[str]
) -> Tuple[int, Dict[str, int]]:
    """
    Process a batch using direct INSERT with pre-computed values.

    Reads records, generates keys in Python, then inserts with all values.
    Returns (records_processed, keys_generated_counts)
    """
    # Read batch
    query = f"""
        SELECT *
        FROM {table}
        ORDER BY id
        LIMIT {batch_size}
        OFFSET {offset}
    """
    records = execute_query(query)

    if not records:
        return 0, {}

    # Generate keys for each record
    keys_count = {f'search_key_{i}': 0 for i in range(1, 9)}

    # Build INSERT data
    insert_values = []
    for record in records:
        # Generate search keys
        keys = generate_search_keys(
            firstname=record.get('firstname', ''),
            middlename=record.get('middlename'),
            lastname=record.get('lastname', ''),
            dob=record.get('dob'),
            phone=record.get('phone'),
            address=record.get('address'),
            state=record.get('state')
        )

        # Count generated keys
        for i in range(1, 9):
            if keys[f'search_key_{i}']:
                keys_count[f'search_key_{i}'] += 1

        # Build value tuple
        values = []
        for col in columns:
            if col.startswith('search_key_'):
                val = keys.get(col)
            else:
                val = record.get(col)

            if val is None:
                values.append('NULL')
            elif isinstance(val, str):
                # Escape quotes
                escaped = val.replace("'", "\\'").replace("\\", "\\\\")
                values.append(f"'{escaped}'")
            elif isinstance(val, (int, float)):
                values.append(str(val))
            else:
                values.append(f"'{val}'")

        insert_values.append(f"({','.join(values)})")

    # Insert in chunks to avoid query size limits
    chunk_size = 1000
    for i in range(0, len(insert_values), chunk_size):
        chunk = insert_values[i:i + chunk_size]
        insert_query = f"""
            INSERT INTO {table}_new ({','.join(columns)})
            VALUES {','.join(chunk)}
        """
        execute_command(insert_query)

    return len(records), keys_count


def create_temp_table(source_table: str, temp_table: str):
    """Create temp table with same structure as source."""
    logger.info(f"Creating temp table {temp_table}...")

    # Get CREATE TABLE statement
    result = execute_query(f"SHOW CREATE TABLE {source_table}")
    create_stmt = result[0]['statement'] if result else None

    if not create_stmt:
        raise RuntimeError(f"Could not get CREATE TABLE for {source_table}")

    # Replace table name
    create_stmt = create_stmt.replace(f"CREATE TABLE {source_table}", f"CREATE TABLE {temp_table}")
    create_stmt = create_stmt.replace(f"CREATE TABLE ssn_database.{source_table}", f"CREATE TABLE ssn_database.{temp_table}")

    # Drop if exists
    execute_command(f"DROP TABLE IF EXISTS {temp_table}")

    # Create new table
    execute_command(create_stmt)
    logger.info(f"Created temp table {temp_table}")


def swap_tables(old_table: str, new_table: str, backup_table: str):
    """Swap tables: old -> backup, new -> old."""
    logger.info(f"Swapping tables: {new_table} -> {old_table}")

    # Rename old to backup
    execute_command(f"RENAME TABLE {old_table} TO {backup_table}")
    logger.info(f"Renamed {old_table} -> {backup_table}")

    # Rename new to old
    execute_command(f"RENAME TABLE {new_table} TO {old_table}")
    logger.info(f"Renamed {new_table} -> {old_table}")

    logger.info("Table swap completed successfully")


def migrate_table(
    table: str,
    batch_size: int = 50000,
    max_records: Optional[int] = None,
    offset: int = 0
):
    """
    Migrate a table by populating search_key columns.

    Uses INSERT into new table approach for efficiency.
    """
    temp_table = f"{table}_new"
    backup_table = f"{table}_backup_{int(time.time())}"

    # Get table info
    total = get_table_count(table)
    columns = get_columns(table)

    logger.info(f"Starting migration for {table}")
    logger.info(f"Total records: {total:,}")
    logger.info(f"Columns: {len(columns)}")

    if max_records:
        total = min(total, max_records + offset)

    # Create temp table
    create_temp_table(table, temp_table)

    # Process in batches
    current_offset = offset
    total_keys = {f'search_key_{i}': 0 for i in range(1, 9)}
    batch_num = 0

    try:
        while current_offset < total:
            batch_num += 1
            start_time = time.time()

            processed, keys_count = process_batch_direct(
                table, current_offset, batch_size, columns
            )

            if processed == 0:
                break

            # Accumulate counts
            for k, v in keys_count.items():
                total_keys[k] += v

            elapsed = time.time() - start_time
            progress = (current_offset + processed) / total * 100

            logger.info(
                f"Batch {batch_num}: {processed:,} records in {elapsed:.1f}s "
                f"({processed/elapsed:.0f} rec/s) - "
                f"Progress: {current_offset + processed:,}/{total:,} ({progress:.1f}%)"
            )

            current_offset += batch_size

        # Verify counts
        new_count = get_table_count(temp_table)
        logger.info(f"New table has {new_count:,} records (original: {total:,})")

        if new_count != total:
            logger.error(f"Record count mismatch! Expected {total:,}, got {new_count:,}")
            logger.error("NOT swapping tables. Manual verification required.")
            return

        # Swap tables
        swap_tables(table, temp_table, backup_table)

        logger.info(f"\n=== Migration Summary for {table} ===")
        logger.info(f"Total records migrated: {new_count:,}")
        for k, v in total_keys.items():
            pct = v / new_count * 100 if new_count > 0 else 0
            logger.info(f"  {k}: {v:,} ({pct:.1f}%)")
        logger.info(f"Backup table: {backup_table}")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        logger.info(f"Cleaning up temp table {temp_table}...")
        execute_command(f"DROP TABLE IF EXISTS {temp_table}")
        raise


def main():
    parser = argparse.ArgumentParser(description='Migrate search_key columns in ClickHouse')
    parser.add_argument('--table', default='ssn_data', help='Table to migrate')
    parser.add_argument('--batch-size', type=int, default=50000, help='Batch size')
    parser.add_argument('--max-records', type=int, help='Max records to process (for testing)')
    parser.add_argument('--offset', type=int, default=0, help='Starting offset')
    parser.add_argument('--wait-mutations', action='store_true', help='Wait for pending mutations first')

    args = parser.parse_args()

    if args.wait_mutations:
        wait_for_mutations(args.table, max_wait_seconds=600)

    migrate_table(
        table=args.table,
        batch_size=args.batch_size,
        max_records=args.max_records,
        offset=args.offset
    )


if __name__ == '__main__':
    main()
