#!/usr/bin/env python3
"""
Migration script to run inside Docker container.
"""
import os
import sys
import sqlite3
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('migration')

# Configure ClickHouse
os.environ['CLICKHOUSE_HOST'] = 'clickhouse'
os.environ['CLICKHOUSE_HTTP_PORT'] = '8123'
os.environ['CLICKHOUSE_DB'] = 'ssn_database'
os.environ['CLICKHOUSE_USER'] = 'ssn_user'
os.environ['CLICKHOUSE_PASSWORD'] = 'change_me_clickhouse_password'

sys.path.insert(0, '/app')

from database import clickhouse_client as ch_client
from database import clickhouse_schema as ch_schema

SQLITE_PATH = '/app/data/specialservicenumbers.db'
BATCH_SIZE = 50000
TABLES = ['ssn_3', 'ssn_2', 'ssn_1']  # Start with smallest

def migrate_table(conn, table_name):
    """Migrate a single table."""
    cursor = conn.cursor()

    # Get count
    cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
    total = cursor.fetchone()[0]
    logger.info(f"Starting migration of {table_name}: {total:,} records")

    column_names = ['id', 'firstname', 'lastname', 'middlename', 'address',
                    'city', 'state', 'zip', 'phone', 'ssn', 'dob', 'email', 'source_table']

    offset = 0
    written = 0
    start_time = datetime.now()

    while offset < total:
        cursor.execute(f'''
            SELECT id, firstname, lastname, middlename, address, city, state, zip,
                   phone, ssn, dob, email
            FROM {table_name}
            LIMIT {BATCH_SIZE} OFFSET {offset}
        ''')

        rows = cursor.fetchall()
        if not rows:
            break

        records = []
        for row in rows:
            records.append({
                'id': row[0] or 0,
                'firstname': row[1] or '',
                'lastname': row[2] or '',
                'middlename': row[3],
                'address': row[4],
                'city': row[5],
                'state': row[6],
                'zip': row[7],
                'phone': row[8],
                'ssn': row[9],
                'dob': row[10],
                'email': row[11],
                'source_table': table_name,
            })

        try:
            batch_written = ch_client.execute_batch(ch_schema.SSN_TABLE, records, column_names=column_names)
            written += batch_written
        except Exception as e:
            logger.error(f"Error writing batch at offset {offset}: {e}")
            # Continue with next batch

        offset += BATCH_SIZE

        if offset % 500000 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = written / elapsed if elapsed > 0 else 0
            eta = (total - offset) / rate / 3600 if rate > 0 else 0
            logger.info(f"Progress: {offset:,}/{total:,} ({100*offset/total:.1f}%), Rate: {rate:.0f} rec/s, ETA: {eta:.1f}h")

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"Completed {table_name}: {written:,} records in {elapsed:.0f}s")
    return written

def main():
    logger.info("Starting migration...")

    # Check ClickHouse
    is_healthy, msg = ch_client.health_check()
    logger.info(f"ClickHouse: {msg}")

    if not is_healthy:
        logger.error("ClickHouse not available")
        sys.exit(1)

    # Connect to SQLite
    conn = sqlite3.connect(SQLITE_PATH)

    total_written = 0
    start_time = datetime.now()

    try:
        for table in TABLES:
            written = migrate_table(conn, table)
            total_written += written
    finally:
        conn.close()

    elapsed = (datetime.now() - start_time).total_seconds()

    # Get final count
    count = ch_client.get_table_count(ch_schema.SSN_TABLE)

    logger.info("=" * 60)
    logger.info(f"Migration Complete!")
    logger.info(f"Total written: {total_written:,}")
    logger.info(f"ClickHouse count: {count:,}")
    logger.info(f"Duration: {elapsed/3600:.1f} hours")
    logger.info("=" * 60)

if __name__ == '__main__':
    main()
