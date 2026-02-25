#!/usr/bin/env python3
"""
Bloom Keys Migration Script

This script migrates existing ClickHouse records to add bloom_key_phone and
bloom_key_address columns. It performs the following steps:

1. ALTER TABLE - adds bloom_key_phone and bloom_key_address columns
2. CREATE INDEX - creates Bloom filter indexes
3. Batch UPDATE - populates bloom keys for existing records

Usage:
    # Run full migration
    python scripts/migrate_bloom_keys.py

    # Add columns and indexes only (no data population)
    python scripts/migrate_bloom_keys.py --schema-only

    # Populate data only (assumes columns exist)
    python scripts/migrate_bloom_keys.py --data-only

    # Resume from specific offset
    python scripts/migrate_bloom_keys.py --offset 1000000

    # Limit number of records to process
    python scripts/migrate_bloom_keys.py --max-records 1000000

    # Custom batch size
    python scripts/migrate_bloom_keys.py --batch-size 50000

    # Check current status
    python scripts/migrate_bloom_keys.py --status
"""

import argparse
import logging
import sys
import os
import time

# Add shared directory to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
shared_dir = os.path.join(project_root, 'shared')
sys.path.insert(0, shared_dir)

from database.clickhouse_client import CLICKHOUSE_AVAILABLE
from database.clickhouse_schema import (
    add_bloom_key_columns,
    populate_bloom_keys,
    get_bloom_key_stats,
    get_schema_info,
    SSN_TABLE,
    SSN_MUTANTS_TABLE,
    ALL_SSN_TABLES,
)


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def print_status(table_name: str = None):
    """Print current bloom key statistics."""
    print("\n" + "=" * 70)
    print("BLOOM KEY MIGRATION STATUS")
    print("=" * 70)

    # Bloom key stats for all tables
    stats = get_bloom_key_stats(table_name)

    if not stats:
        print("\nNo tables found")
        print("=" * 70)
        return

    for table, table_stats in stats.items():
        if table == '_totals':
            continue

        total = table_stats.get('total', 0)
        phone_keys = table_stats.get('with_phone_key', 0)
        address_keys = table_stats.get('with_address_key', 0)
        both_keys = table_stats.get('with_both_keys', 0)
        no_keys = table_stats.get('with_no_keys', 0)
        columns_exist = table_stats.get('columns_exist', False)

        print(f"\n[{table}]")
        print(f"  Total records: {total:,}")
        print(f"  Bloom columns exist: {columns_exist}")

        if total > 0:
            print(f"  Coverage:")
            print(f"    - With phone key:    {phone_keys:>15,} ({100*phone_keys/total:>5.1f}%)")
            print(f"    - With address key:  {address_keys:>15,} ({100*address_keys/total:>5.1f}%)")
            print(f"    - With both keys:    {both_keys:>15,} ({100*both_keys/total:>5.1f}%)")
            print(f"    - With no keys:      {no_keys:>15,} ({100*no_keys/total:>5.1f}%)")

    # Print totals
    totals = stats.get('_totals', {})
    if totals:
        total = totals.get('total', 0)
        phone_keys = totals.get('with_phone_key', 0)
        address_keys = totals.get('with_address_key', 0)
        both_keys = totals.get('with_both_keys', 0)
        no_keys = totals.get('with_no_keys', 0)

        print(f"\n{'='*70}")
        print(f"TOTALS (all tables)")
        print(f"  Total records: {total:,}")
        if total > 0:
            print(f"  Coverage:")
            print(f"    - With phone key:    {phone_keys:>15,} ({100*phone_keys/total:>5.1f}%)")
            print(f"    - With address key:  {address_keys:>15,} ({100*address_keys/total:>5.1f}%)")
            print(f"    - With both keys:    {both_keys:>15,} ({100*both_keys/total:>5.1f}%)")
            print(f"    - With no keys:      {no_keys:>15,} ({100*no_keys/total:>5.1f}%)")

    print("\n" + "=" * 70)


def run_schema_migration(table_name: str = None):
    """Add columns and indexes."""
    print("\n" + "-" * 70)
    print("STEP 1: Adding columns and indexes")
    print("-" * 70)

    result = add_bloom_key_columns(table_name)

    for table, table_result in result.items():
        print(f"\n[{table}]")
        print(f"  - bloom_key_phone column added: {table_result.get('bloom_key_phone_added', False)}")
        print(f"  - bloom_key_address column added: {table_result.get('bloom_key_address_added', False)}")
        print(f"  - bloom_idx_key_phone index added: {table_result.get('index_phone_added', False)}")
        print(f"  - bloom_idx_key_address index added: {table_result.get('index_address_added', False)}")

    return result


def run_data_migration(table_name: str, batch_size: int, offset: int, max_records: int = None):
    """Populate bloom keys for existing records."""
    print("\n" + "-" * 70)
    print("STEP 2: Populating bloom keys")
    print("-" * 70)
    print(f"\nTable(s): {table_name or 'all'}")
    print(f"Batch size: {batch_size:,}")
    print(f"Starting offset: {offset:,}")
    if max_records:
        print(f"Max records per table: {max_records:,}")

    start_time = time.time()

    results = populate_bloom_keys(
        table_name=table_name,
        batch_size=batch_size,
        offset=offset,
        max_records=max_records
    )

    elapsed = time.time() - start_time

    total_processed = 0
    total_phone_keys = 0
    total_address_keys = 0

    for table, result in results.items():
        total_processed += result['total_processed']
        total_phone_keys += result['phone_keys_generated']
        total_address_keys += result['address_keys_generated']

        print(f"\n[{table}]")
        print(f"  - Total processed: {result['total_processed']:,}")
        print(f"  - Phone keys generated: {result['phone_keys_generated']:,}")
        print(f"  - Address keys generated: {result['address_keys_generated']:,}")
        print(f"  - Batches processed: {result['batches_processed']}")

        if result['errors']:
            print(f"  - Errors: {len(result['errors'])}")
            for error in result['errors'][:5]:
                print(f"      {error}")
            if len(result['errors']) > 5:
                print(f"      ... and {len(result['errors']) - 5} more errors")

    records_per_sec = total_processed / elapsed if elapsed > 0 else 0

    print(f"\n{'='*70}")
    print(f"TOTALS:")
    print(f"  - Total processed: {total_processed:,}")
    print(f"  - Phone keys generated: {total_phone_keys:,}")
    print(f"  - Address keys generated: {total_address_keys:,}")
    print(f"  - Elapsed time: {elapsed:.1f}s")
    print(f"  - Processing rate: {records_per_sec:.0f} records/sec")

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Migrate ClickHouse records to add bloom key columns',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--table',
        type=str,
        choices=['ssn_data', 'ssn_mutants'],
        default=None,
        help='Specific table to migrate (default: all tables)'
    )
    parser.add_argument(
        '--schema-only',
        action='store_true',
        help='Only add columns and indexes, skip data population'
    )
    parser.add_argument(
        '--data-only',
        action='store_true',
        help='Only populate data, skip schema changes'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Show current migration status and exit'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100000,
        help='Number of records per batch (default: 100000)'
    )
    parser.add_argument(
        '--offset',
        type=int,
        default=0,
        help='Starting offset for data migration (default: 0)'
    )
    parser.add_argument(
        '--max-records',
        type=int,
        default=None,
        help='Maximum number of records to process per table (default: all)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Check ClickHouse availability
    if not CLICKHOUSE_AVAILABLE:
        print("ERROR: clickhouse-connect is not installed")
        print("Install with: pip install clickhouse-connect")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("BLOOM KEY MIGRATION")
    print("=" * 60)

    try:
        # Status check
        if args.status:
            print_status(args.table)
            sys.exit(0)

        # Schema migration
        if not args.data_only:
            run_schema_migration(args.table)

        # Data migration
        if not args.schema_only:
            run_data_migration(
                table_name=args.table,
                batch_size=args.batch_size,
                offset=args.offset,
                max_records=args.max_records
            )

        # Final status
        print_status(args.table)

        print("\nMigration completed successfully!")

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        print(f"\nERROR: Migration failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
