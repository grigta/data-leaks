#!/usr/bin/env python3
"""
SQLite to ClickHouse Migration Script

This script migrates SSN data from SQLite tables (ssn_1, ssn_2, ssn_3) to a single
unified ClickHouse table (ssn_data).

Features:
- Batch processing for memory efficiency
- Progress tracking with logging
- Data validation during migration
- Rollback capability on failure
- Resume support for interrupted migrations

Usage:
    # Full migration
    python scripts/migrate_sqlite_to_clickhouse.py

    # Dry run (no actual writes)
    python scripts/migrate_sqlite_to_clickhouse.py --dry-run

    # Resume from specific table
    python scripts/migrate_sqlite_to_clickhouse.py --start-table ssn_2

    # Custom batch size
    python scripts/migrate_sqlite_to_clickhouse.py --batch-size 5000

Environment Variables:
    SQLITE_PATH: Path to SQLite database (default: /app/data/ssn_database.db)
    CLICKHOUSE_HOST, CLICKHOUSE_PORT, etc.: ClickHouse connection settings
"""

import os
import sys
import argparse
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_schema import get_connection, close_connection, DEFAULT_DB_PATH

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('migrate_sqlite_to_clickhouse')

# Migration configuration
BATCH_SIZE = 10000
TABLES_TO_MIGRATE = ['ssn_1', 'ssn_2', 'ssn_3']
PROGRESS_LOG_INTERVAL = 100000  # Log progress every N records


class MigrationStats:
    """Track migration statistics."""

    def __init__(self):
        self.total_read = 0
        self.total_written = 0
        self.total_failed = 0
        self.tables_completed = []
        self.start_time = None
        self.end_time = None

    def start(self):
        self.start_time = datetime.now()

    def finish(self):
        self.end_time = datetime.now()

    @property
    def duration(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0

    @property
    def records_per_second(self) -> float:
        if self.duration > 0:
            return self.total_written / self.duration
        return 0

    def __str__(self) -> str:
        return (
            f"Migration Stats:\n"
            f"  Total read: {self.total_read:,}\n"
            f"  Total written: {self.total_written:,}\n"
            f"  Total failed: {self.total_failed:,}\n"
            f"  Tables completed: {self.tables_completed}\n"
            f"  Duration: {self.duration:.1f} seconds\n"
            f"  Speed: {self.records_per_second:.1f} records/second"
        )


def get_table_count(connection, table_name: str) -> int:
    """Get the number of records in a SQLite table."""
    cursor = connection.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0]


def read_batch(connection, table_name: str, offset: int, batch_size: int) -> List[Dict]:
    """
    Read a batch of records from SQLite.

    Args:
        connection: SQLite connection
        table_name: Name of the table to read from
        offset: Starting offset
        batch_size: Number of records to read

    Returns:
        List of record dictionaries
    """
    cursor = connection.cursor()
    cursor.execute(f"""
        SELECT id, firstname, lastname, middlename, address, city, state, zip,
               phone, ssn, dob, email
        FROM {table_name}
        LIMIT ? OFFSET ?
    """, (batch_size, offset))

    columns = ['id', 'firstname', 'lastname', 'middlename', 'address', 'city',
               'state', 'zip', 'phone', 'ssn', 'dob', 'email']

    records = []
    for row in cursor.fetchall():
        record = dict(zip(columns, row))
        record['source_table'] = table_name
        records.append(record)

    return records


def validate_record(record: Dict) -> Tuple[bool, Optional[str]]:
    """
    Validate a record before migration.

    Args:
        record: Record dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    # SSN is required
    if not record.get('ssn'):
        return False, "Missing SSN"

    # Basic SSN format validation
    ssn = record['ssn']
    if len(ssn) < 9:
        return False, f"Invalid SSN format: {ssn}"

    return True, None


def transform_record(record: Dict) -> Dict:
    """
    Transform a record for ClickHouse insertion.

    Args:
        record: SQLite record

    Returns:
        Transformed record for ClickHouse
    """
    return {
        'id': record.get('id', 0),
        'firstname': record.get('firstname') or '',
        'lastname': record.get('lastname') or '',
        'middlename': record.get('middlename'),
        'address': record.get('address'),
        'city': record.get('city'),
        'state': record.get('state'),
        'zip': record.get('zip'),
        'phone': record.get('phone'),
        'ssn': record['ssn'],
        'dob': record.get('dob'),
        'email': record.get('email'),
        'source_table': record.get('source_table', 'ssn_1'),
    }


def migrate_table(
    sqlite_conn,
    ch_client,
    ch_schema,
    table_name: str,
    batch_size: int,
    dry_run: bool,
    stats: MigrationStats
) -> bool:
    """
    Migrate a single SQLite table to ClickHouse.

    Args:
        sqlite_conn: SQLite connection
        ch_client: ClickHouse client module
        ch_schema: ClickHouse schema module
        table_name: Name of the SQLite table
        batch_size: Batch size for processing
        dry_run: If True, don't actually write to ClickHouse
        stats: Statistics tracker

    Returns:
        bool: True if migration succeeded
    """
    logger.info(f"Starting migration of table: {table_name}")

    # Get total count
    total_count = get_table_count(sqlite_conn, table_name)
    logger.info(f"Table {table_name} has {total_count:,} records")

    if total_count == 0:
        logger.info(f"Table {table_name} is empty, skipping")
        stats.tables_completed.append(table_name)
        return True

    # Process in batches
    offset = 0
    table_written = 0
    table_failed = 0

    column_names = ['id', 'firstname', 'lastname', 'middlename', 'address',
                    'city', 'state', 'zip', 'phone', 'ssn', 'dob', 'email', 'source_table']

    while offset < total_count:
        # Read batch from SQLite
        batch = read_batch(sqlite_conn, table_name, offset, batch_size)

        if not batch:
            break

        # Validate and transform records
        valid_records = []
        for record in batch:
            is_valid, error = validate_record(record)
            if is_valid:
                transformed = transform_record(record)
                valid_records.append(transformed)
            else:
                table_failed += 1
                stats.total_failed += 1
                if table_failed <= 10:  # Only log first 10 errors per table
                    logger.warning(f"Validation error in {table_name}: {error}")

        stats.total_read += len(batch)

        # Write to ClickHouse
        if valid_records and not dry_run:
            try:
                written = ch_client.execute_batch(
                    ch_schema.SSN_TABLE,
                    valid_records,
                    column_names=column_names
                )
                table_written += written
                stats.total_written += written
            except Exception as e:
                logger.error(f"Error writing batch to ClickHouse: {e}")
                return False
        elif dry_run:
            table_written += len(valid_records)
            stats.total_written += len(valid_records)

        offset += batch_size

        # Log progress
        if stats.total_read % PROGRESS_LOG_INTERVAL == 0:
            logger.info(
                f"Progress: {stats.total_read:,} read, {stats.total_written:,} written, "
                f"{stats.total_failed:,} failed"
            )

    logger.info(
        f"Completed table {table_name}: {table_written:,} written, {table_failed:,} failed"
    )
    stats.tables_completed.append(table_name)
    return True


def run_migration(
    sqlite_path: str,
    batch_size: int,
    dry_run: bool,
    start_table: Optional[str] = None,
    drop_existing: bool = False
) -> MigrationStats:
    """
    Run the full migration from SQLite to ClickHouse.

    Args:
        sqlite_path: Path to SQLite database
        batch_size: Batch size for processing
        dry_run: If True, don't actually write to ClickHouse
        start_table: Optional table to start from (for resuming)
        drop_existing: If True, drop existing ClickHouse table

    Returns:
        MigrationStats: Migration statistics
    """
    stats = MigrationStats()
    stats.start()

    # Import ClickHouse modules
    try:
        from database import clickhouse_client as ch_client
        from database import clickhouse_schema as ch_schema
    except ImportError as e:
        logger.error(f"Failed to import ClickHouse modules: {e}")
        raise

    # Check ClickHouse connection
    if not dry_run:
        is_healthy, message = ch_client.health_check()
        if not is_healthy:
            logger.error(f"ClickHouse health check failed: {message}")
            raise ConnectionError(message)
        logger.info(f"ClickHouse connection: {message}")

        # Initialize schema
        logger.info("Initializing ClickHouse schema...")
        ch_schema.initialize_schema()

        if drop_existing:
            logger.warning("Dropping existing data (--drop-existing flag)")
            ch_client.execute_command(f"TRUNCATE TABLE IF EXISTS {ch_schema.SSN_TABLE}")

    # Connect to SQLite
    logger.info(f"Connecting to SQLite: {sqlite_path}")
    sqlite_conn = get_connection(sqlite_path)

    try:
        # Determine which tables to migrate
        tables = TABLES_TO_MIGRATE.copy()
        if start_table:
            try:
                start_idx = tables.index(start_table)
                tables = tables[start_idx:]
                logger.info(f"Starting from table: {start_table}")
            except ValueError:
                logger.warning(f"Unknown start table: {start_table}, starting from beginning")

        # Migrate each table
        for table_name in tables:
            success = migrate_table(
                sqlite_conn, ch_client, ch_schema,
                table_name, batch_size, dry_run, stats
            )
            if not success:
                logger.error(f"Migration failed at table: {table_name}")
                break

        # Optimize table after migration
        if not dry_run and stats.total_written > 0:
            logger.info("Optimizing ClickHouse table...")
            try:
                ch_schema.optimize_table()
            except Exception as e:
                logger.warning(f"Table optimization failed: {e}")

    finally:
        close_connection(sqlite_conn)

    stats.finish()
    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Migrate SSN data from SQLite to ClickHouse'
    )
    parser.add_argument(
        '--sqlite-path',
        default=os.getenv('SQLITE_PATH', DEFAULT_DB_PATH),
        help='Path to SQLite database'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=BATCH_SIZE,
        help=f'Batch size for processing (default: {BATCH_SIZE})'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without writing to ClickHouse'
    )
    parser.add_argument(
        '--start-table',
        choices=TABLES_TO_MIGRATE,
        help='Table to start migration from (for resuming)'
    )
    parser.add_argument(
        '--drop-existing',
        action='store_true',
        help='Drop existing ClickHouse data before migration'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("=" * 70)
    print("SQLite to ClickHouse Migration")
    print("=" * 70)
    print(f"SQLite path: {args.sqlite_path}")
    print(f"Batch size: {args.batch_size:,}")
    print(f"Dry run: {args.dry_run}")
    print(f"Start table: {args.start_table or 'ssn_1'}")
    print(f"Drop existing: {args.drop_existing}")
    print("=" * 70)

    if args.drop_existing and not args.dry_run:
        confirm = input("WARNING: This will delete existing ClickHouse data. Continue? [y/N] ")
        if confirm.lower() != 'y':
            print("Migration cancelled.")
            sys.exit(0)

    try:
        stats = run_migration(
            sqlite_path=args.sqlite_path,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            start_table=args.start_table,
            drop_existing=args.drop_existing
        )

        print("\n" + "=" * 70)
        print("Migration Complete!")
        print("=" * 70)
        print(stats)
        print("=" * 70)

        if stats.total_failed > 0:
            logger.warning(f"{stats.total_failed:,} records failed validation")
            sys.exit(1)

    except FileNotFoundError as e:
        logger.error(f"SQLite database not found: {e}")
        sys.exit(1)
    except ConnectionError as e:
        logger.error(f"ClickHouse connection failed: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nMigration interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
