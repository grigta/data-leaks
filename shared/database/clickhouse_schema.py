"""
ClickHouse Schema Module for SSN Data

This module defines the ClickHouse schema for the unified SSN data table.
It replaces the 3 SQLite tables (ssn_1, ssn_2, ssn_3) with a single optimized
ClickHouse table using MergeTree engine and Bloom filter indexes.

Features:
- Single unified table replacing 3 SQLite tables
- MergeTree engine with optimized ORDER BY
- Bloom filter indexes for fast multi-column filtering
- Hash-based partitioning for distributed queries
- Skip indexes for range queries

Usage:
    from database.clickhouse_schema import initialize_schema
    initialize_schema()  # Creates table and indexes if not exists
"""

import logging
from typing import Optional

from database.clickhouse_client import (
    get_connection,
    execute_command,
    table_exists,
    get_table_count,
    CLICKHOUSE_AVAILABLE,
)

# Module logger
logger = logging.getLogger(__name__)

# Table names for SSN data
SSN_TABLE = 'ssn_data'
SSN_MUTANTS_TABLE = 'ssn_mutants'
ALL_SSN_TABLES = [SSN_TABLE, SSN_MUTANTS_TABLE]

# Lookup tables (optimized for point queries with ORDER BY bloom_key)
SSN_BLOOM_PHONE_LOOKUP = 'ssn_bloom_phone_lookup'
SSN_MUTANTS_BLOOM_PHONE_LOOKUP = 'ssn_mutants_bloom_phone_lookup'
SSN_BLOOM_ADDRESS_LOOKUP = 'ssn_bloom_address_lookup'
SSN_MUTANTS_BLOOM_ADDRESS_LOOKUP = 'ssn_mutants_bloom_address_lookup'

# Table schema
CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SSN_TABLE}
(
    -- Primary identification
    id UInt64,

    -- Personal information
    firstname String,
    lastname String,
    middlename Nullable(String),

    -- Address information
    address Nullable(String),
    city Nullable(String),
    state Nullable(String),
    zip Nullable(String),

    -- Contact information
    phone Nullable(String),
    email Nullable(String),

    -- Bloom composite keys for fast SearchBug matching
    bloom_key_phone Nullable(String),
    bloom_key_address Nullable(String),

    -- Identity data
    ssn String,
    dob Nullable(String),

    -- Metadata
    source_table LowCardinality(String) DEFAULT 'ssn_1',
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now(),

    -- Bloom filter indexes for fast existence checks
    INDEX bloom_ssn ssn TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX bloom_lastname lastname TYPE bloom_filter(0.01) GRANULARITY 4,
    INDEX bloom_firstname firstname TYPE bloom_filter(0.01) GRANULARITY 4,
    INDEX bloom_zip zip TYPE bloom_filter(0.01) GRANULARITY 4,
    INDEX bloom_phone phone TYPE bloom_filter(0.01) GRANULARITY 4,
    INDEX bloom_email email TYPE bloom_filter(0.01) GRANULARITY 4,

    -- Bloom filter indexes for composite keys (fast SearchBug matching - Level 1)
    INDEX bloom_idx_key_phone bloom_key_phone TYPE bloom_filter(0.001) GRANULARITY 1,
    INDEX bloom_idx_key_address bloom_key_address TYPE bloom_filter(0.001) GRANULARITY 1,

    -- Search keys for exact matching (Level 2: 8 methods)
    -- Key 1: FN:MN:LN:DOB_YEAR:PHONE
    search_key_1 Nullable(String),
    -- Key 2: FN:MN:LN:DOB_YEAR:ADDR#:STREET:STATE
    search_key_2 Nullable(String),
    -- Key 3: FN:LN:DOB_YEAR:PHONE
    search_key_3 Nullable(String),
    -- Key 4: FN:LN:DOB_YEAR:ADDR#:STREET:STATE
    search_key_4 Nullable(String),
    -- Key 5: FN:MN:LN:PHONE
    search_key_5 Nullable(String),
    -- Key 6: FN:MN:LN:ADDR#:STREET:STATE
    search_key_6 Nullable(String),
    -- Key 7: FN:LN:ADDR#:STREET:STATE
    search_key_7 Nullable(String),
    -- Key 8: FN:LN:PHONE
    search_key_8 Nullable(String),

    -- Bloom filter indexes for Level 2 search keys
    INDEX idx_search_key_1 search_key_1 TYPE bloom_filter(0.001) GRANULARITY 1,
    INDEX idx_search_key_2 search_key_2 TYPE bloom_filter(0.001) GRANULARITY 1,
    INDEX idx_search_key_3 search_key_3 TYPE bloom_filter(0.001) GRANULARITY 1,
    INDEX idx_search_key_4 search_key_4 TYPE bloom_filter(0.001) GRANULARITY 1,
    INDEX idx_search_key_5 search_key_5 TYPE bloom_filter(0.001) GRANULARITY 1,
    INDEX idx_search_key_6 search_key_6 TYPE bloom_filter(0.001) GRANULARITY 1,
    INDEX idx_search_key_7 search_key_7 TYPE bloom_filter(0.001) GRANULARITY 1,
    INDEX idx_search_key_8 search_key_8 TYPE bloom_filter(0.001) GRANULARITY 1,

    -- Token bloom filter for partial name matching
    INDEX token_lastname lastname TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 4,
    INDEX token_firstname firstname TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 4,

    -- Skip index for state filtering
    INDEX skip_state state TYPE set(50) GRANULARITY 4
)
ENGINE = MergeTree()
ORDER BY (ssn, lastname, firstname)
SETTINGS index_granularity = 8192
"""

# Materialized view for duplicate detection
CREATE_DUPLICATE_VIEW_SQL = f"""
CREATE MATERIALIZED VIEW IF NOT EXISTS {SSN_TABLE}_duplicates
ENGINE = AggregatingMergeTree()
ORDER BY ssn
AS SELECT
    ssn,
    count() as duplicate_count,
    groupArray(id) as record_ids
FROM {SSN_TABLE}
GROUP BY ssn
HAVING duplicate_count > 1
"""

# Metadata table for sync tracking
CREATE_METADATA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sync_metadata
(
    key String,
    value String,
    updated_at DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY key
"""


def create_table(drop_existing: bool = False) -> bool:
    """
    Create the SSN data table with all indexes.

    Args:
        drop_existing: If True, drop existing table first (DANGEROUS!)

    Returns:
        bool: True if table was created, False if already existed

    Raises:
        Exception: If table creation fails
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    with get_connection() as client:
        # Check if table exists
        exists = table_exists(SSN_TABLE, client=client)

        if exists and drop_existing:
            logger.warning(f"Dropping existing table {SSN_TABLE}")
            execute_command(f"DROP TABLE IF EXISTS {SSN_TABLE}", client=client)
            exists = False

        if not exists:
            logger.info(f"Creating table {SSN_TABLE}")
            execute_command(CREATE_TABLE_SQL, client=client)
            logger.info(f"Table {SSN_TABLE} created successfully")
            return True

        logger.info(f"Table {SSN_TABLE} already exists")
        return False


def create_metadata_table() -> bool:
    """
    Create the sync metadata table.

    Returns:
        bool: True if table was created, False if already existed
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    with get_connection() as client:
        exists = table_exists('sync_metadata', client=client)

        if not exists:
            logger.info("Creating sync_metadata table")
            execute_command(CREATE_METADATA_TABLE_SQL, client=client)
            logger.info("sync_metadata table created successfully")
            return True

        logger.info("sync_metadata table already exists")
        return False


def create_duplicate_view() -> bool:
    """
    Create materialized view for duplicate SSN detection.

    Returns:
        bool: True if view was created, False if already existed
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    with get_connection() as client:
        exists = table_exists(f'{SSN_TABLE}_duplicates', client=client)

        if not exists:
            logger.info(f"Creating materialized view {SSN_TABLE}_duplicates")
            execute_command(CREATE_DUPLICATE_VIEW_SQL, client=client)
            logger.info(f"Materialized view {SSN_TABLE}_duplicates created successfully")
            return True

        logger.info(f"Materialized view {SSN_TABLE}_duplicates already exists")
        return False


def initialize_schema(include_duplicate_view: bool = False) -> dict:
    """
    Initialize complete ClickHouse schema for SSN data.

    Creates:
    1. Main ssn_data table with Bloom filter indexes
    2. sync_metadata table for tracking sync state
    3. Optionally, duplicate detection materialized view

    Args:
        include_duplicate_view: Whether to create duplicate detection view

    Returns:
        dict: Summary of created objects
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    results = {
        'ssn_table_created': False,
        'metadata_table_created': False,
        'duplicate_view_created': False,
    }

    try:
        # Create main table
        results['ssn_table_created'] = create_table()

        # Create metadata table
        results['metadata_table_created'] = create_metadata_table()

        # Optionally create duplicate view
        if include_duplicate_view:
            results['duplicate_view_created'] = create_duplicate_view()

        logger.info(f"Schema initialization complete: {results}")
        return results

    except Exception as e:
        logger.error(f"Schema initialization failed: {e}")
        raise


def get_schema_info() -> dict:
    """
    Get information about the current schema.

    Returns:
        dict: Schema information including tables and row counts
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    info = {
        'ssn_table_exists': False,
        'ssn_table_count': 0,
        'metadata_table_exists': False,
        'duplicate_view_exists': False,
    }

    with get_connection() as client:
        info['ssn_table_exists'] = table_exists(SSN_TABLE, client=client)
        if info['ssn_table_exists']:
            info['ssn_table_count'] = get_table_count(SSN_TABLE, client=client)

        info['metadata_table_exists'] = table_exists('sync_metadata', client=client)
        info['duplicate_view_exists'] = table_exists(f'{SSN_TABLE}_duplicates', client=client)

    return info


def drop_all_tables() -> None:
    """
    Drop all SSN-related tables (DANGEROUS - use with caution!).

    This is primarily for development/testing purposes.
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    tables_to_drop = [
        f'{SSN_TABLE}_duplicates',
        'sync_metadata',
        SSN_TABLE,
    ]

    with get_connection() as client:
        for table in tables_to_drop:
            if table_exists(table, client=client):
                logger.warning(f"Dropping table {table}")
                execute_command(f"DROP TABLE IF EXISTS {table}", client=client)
                logger.info(f"Table {table} dropped")


def optimize_table() -> None:
    """
    Optimize the SSN data table by merging parts.

    This should be run periodically or after large bulk inserts
    to improve query performance.
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    logger.info(f"Optimizing table {SSN_TABLE}")
    execute_command(f"OPTIMIZE TABLE {SSN_TABLE} FINAL")
    logger.info(f"Table {SSN_TABLE} optimized")


def get_table_stats() -> dict:
    """
    Get detailed statistics about the SSN data table.

    Returns:
        dict: Table statistics including parts, rows, bytes, etc.
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    from database.clickhouse_client import execute_query

    stats = execute_query(f"""
        SELECT
            count() as parts_count,
            sum(rows) as total_rows,
            sum(bytes) as total_bytes,
            formatReadableSize(sum(bytes)) as readable_size,
            min(min_date) as min_date,
            max(max_date) as max_date
        FROM system.parts
        WHERE table = '{SSN_TABLE}' AND active = 1
    """)

    if stats:
        return stats[0]
    return {}


def check_bloom_filter_usage(query: str) -> dict:
    """
    Check if a query would use Bloom filter indexes.

    Args:
        query: SQL query to analyze

    Returns:
        dict: Information about index usage
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    from database.clickhouse_client import execute_query

    # Use EXPLAIN to check index usage
    explain_result = execute_query(f"EXPLAIN indexes = 1 {query}")
    return {'explain': explain_result}


def add_bloom_key_columns(table_name: str = None) -> dict:
    """
    Add bloom_key_phone and bloom_key_address columns to existing table(s).

    This is a migration function for existing tables that don't have
    the bloom key columns yet.

    Args:
        table_name: Specific table to migrate, or None for all SSN tables

    Returns:
        dict: Summary of migration results per table
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    from database.clickhouse_client import execute_query

    tables_to_migrate = [table_name] if table_name else ALL_SSN_TABLES
    results = {}

    with get_connection() as client:
        for table in tables_to_migrate:
            # Check if table exists
            if not table_exists(table, client=client):
                logger.warning(f"Table {table} does not exist, skipping")
                continue

            table_results = {
                'bloom_key_phone_added': False,
                'bloom_key_address_added': False,
                'index_phone_added': False,
                'index_address_added': False,
            }

            # Check existing columns
            columns = execute_query(
                f"DESCRIBE TABLE {table}",
                client=client
            )
            existing_columns = {row['name'] for row in columns}

            # Add bloom_key_phone column if not exists
            if 'bloom_key_phone' not in existing_columns:
                logger.info(f"[{table}] Adding bloom_key_phone column")
                execute_command(
                    f"ALTER TABLE {table} ADD COLUMN bloom_key_phone Nullable(String)",
                    client=client
                )
                table_results['bloom_key_phone_added'] = True
                logger.info(f"[{table}] bloom_key_phone column added")
            else:
                logger.info(f"[{table}] bloom_key_phone column already exists")

            # Add bloom_key_address column if not exists
            if 'bloom_key_address' not in existing_columns:
                logger.info(f"[{table}] Adding bloom_key_address column")
                execute_command(
                    f"ALTER TABLE {table} ADD COLUMN bloom_key_address Nullable(String)",
                    client=client
                )
                table_results['bloom_key_address_added'] = True
                logger.info(f"[{table}] bloom_key_address column added")
            else:
                logger.info(f"[{table}] bloom_key_address column already exists")

            # Check existing indexes
            indexes = execute_query(
                f"SELECT name FROM system.data_skipping_indices WHERE table = '{table}'",
                client=client
            )
            existing_indexes = {row['name'] for row in indexes}

            # Add bloom index for phone key
            if 'bloom_idx_key_phone' not in existing_indexes:
                logger.info(f"[{table}] Adding bloom_idx_key_phone index")
                execute_command(
                    f"ALTER TABLE {table} ADD INDEX bloom_idx_key_phone bloom_key_phone "
                    f"TYPE bloom_filter(0.001) GRANULARITY 1",
                    client=client
                )
                table_results['index_phone_added'] = True
                logger.info(f"[{table}] bloom_idx_key_phone index added")
            else:
                logger.info(f"[{table}] bloom_idx_key_phone index already exists")

            # Add bloom index for address key
            if 'bloom_idx_key_address' not in existing_indexes:
                logger.info(f"[{table}] Adding bloom_idx_key_address index")
                execute_command(
                    f"ALTER TABLE {table} ADD INDEX bloom_idx_key_address bloom_key_address "
                    f"TYPE bloom_filter(0.001) GRANULARITY 1",
                    client=client
                )
                table_results['index_address_added'] = True
                logger.info(f"[{table}] bloom_idx_key_address index added")
            else:
                logger.info(f"[{table}] bloom_idx_key_address index already exists")

            results[table] = table_results

    return results


def populate_bloom_keys(
    table_name: str = None,
    batch_size: int = 10000,
    update_chunk_size: int = 500,
    offset: int = 0,
    max_records: int = None
) -> dict:
    """
    Populate bloom_key_phone and bloom_key_address for existing records.

    This function reads records in batches, generates bloom keys using
    bloom_key_generator, and updates the records in small chunks to avoid
    query size limits.

    Args:
        table_name: Specific table to populate, or None for all SSN tables
        batch_size: Number of records to read per batch
        update_chunk_size: Number of records per UPDATE query (default 500 to avoid query size limits)
        offset: Starting offset (for resuming migration)
        max_records: Maximum number of records to process per table (None for all)

    Returns:
        dict: Summary of migration results per table
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    from database.clickhouse_client import execute_query
    from database.bloom_key_generator import generate_bloom_key_phone, generate_bloom_key_address

    tables_to_process = [table_name] if table_name else ALL_SSN_TABLES
    all_results = {}

    for table in tables_to_process:
        # Check if table exists
        if not table_exists(table):
            logger.warning(f"Table {table} does not exist, skipping")
            continue

        logger.info(f"Processing table: {table}")

        results = {
            'total_processed': 0,
            'phone_keys_generated': 0,
            'address_keys_generated': 0,
            'batches_processed': 0,
            'errors': []
        }

        # Get total count
        count_result = execute_query(f"SELECT count() as cnt FROM {table}")
        total_records = count_result[0]['cnt'] if count_result else 0
        logger.info(f"[{table}] Total records: {total_records:,}")

        if max_records:
            total_records = min(total_records, max_records + offset)

        current_offset = offset

        while current_offset < total_records:
            try:
                # Fetch batch
                batch_query = f"""
                SELECT id, firstname, lastname, phone, address, state
                FROM {table}
                ORDER BY id
                LIMIT {batch_size}
                OFFSET {current_offset}
                """
                records = execute_query(batch_query)

                if not records:
                    break

                # Generate bloom keys for batch
                updates_phone = []
                updates_address = []

                for record in records:
                    record_id = record['id']
                    firstname = record.get('firstname', '')
                    lastname = record.get('lastname', '')
                    phone = record.get('phone')
                    address = record.get('address')
                    state = record.get('state')

                    # Generate phone key
                    if phone:
                        phone_key = generate_bloom_key_phone(firstname, lastname, phone)
                        if phone_key:
                            # Escape single quotes in key
                            phone_key_escaped = phone_key.replace("'", "\\'")
                            updates_phone.append((record_id, phone_key_escaped))
                            results['phone_keys_generated'] += 1

                    # Generate address key
                    if address and state:
                        address_key = generate_bloom_key_address(firstname, lastname, address, state)
                        if address_key:
                            # Escape single quotes in key
                            address_key_escaped = address_key.replace("'", "\\'")
                            updates_address.append((record_id, address_key_escaped))
                            results['address_keys_generated'] += 1

                # Update phone keys in chunks
                for i in range(0, len(updates_phone), update_chunk_size):
                    chunk = updates_phone[i:i + update_chunk_size]
                    if chunk:
                        case_parts = [f"WHEN id = {rid} THEN '{key}'" for rid, key in chunk]
                        ids = [str(rid) for rid, _ in chunk]
                        update_query = f"""
                        ALTER TABLE {table}
                        UPDATE bloom_key_phone = CASE {' '.join(case_parts)} ELSE bloom_key_phone END
                        WHERE id IN ({','.join(ids)})
                        """
                        execute_command(update_query)

                # Update address keys in chunks
                for i in range(0, len(updates_address), update_chunk_size):
                    chunk = updates_address[i:i + update_chunk_size]
                    if chunk:
                        case_parts = [f"WHEN id = {rid} THEN '{key}'" for rid, key in chunk]
                        ids = [str(rid) for rid, _ in chunk]
                        update_query = f"""
                        ALTER TABLE {table}
                        UPDATE bloom_key_address = CASE {' '.join(case_parts)} ELSE bloom_key_address END
                        WHERE id IN ({','.join(ids)})
                        """
                        execute_command(update_query)

                results['total_processed'] += len(records)
                results['batches_processed'] += 1
                current_offset += batch_size

                logger.info(
                    f"[{table}] Batch {results['batches_processed']}: processed {len(records)} records, "
                    f"total: {results['total_processed']:,}/{total_records:,} "
                    f"({100*results['total_processed']/total_records:.1f}%)"
                )

            except Exception as e:
                error_msg = f"[{table}] Error at offset {current_offset}: {str(e)}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
                current_offset += batch_size  # Skip problematic batch

        all_results[table] = results

    return all_results


def get_bloom_key_stats(table_name: str = None) -> dict:
    """
    Get statistics about bloom key coverage in the table(s).

    Args:
        table_name: Specific table to check, or None for all SSN tables

    Returns:
        dict: Statistics about bloom key population per table
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    from database.clickhouse_client import execute_query

    tables_to_check = [table_name] if table_name else ALL_SSN_TABLES
    all_stats = {}
    totals = {
        'total': 0,
        'with_phone_key': 0,
        'with_address_key': 0,
        'with_both_keys': 0,
        'with_no_keys': 0
    }

    for table in tables_to_check:
        if not table_exists(table):
            continue

        # Check if bloom_key columns exist
        columns = execute_query(f"DESCRIBE TABLE {table}")
        existing_columns = {row['name'] for row in columns}

        if 'bloom_key_phone' not in existing_columns:
            # Columns not added yet
            count_result = execute_query(f"SELECT count() as total FROM {table}")
            total = count_result[0]['total'] if count_result else 0
            all_stats[table] = {
                'total': total,
                'with_phone_key': 0,
                'with_address_key': 0,
                'with_both_keys': 0,
                'with_no_keys': total,
                'columns_exist': False
            }
            totals['total'] += total
            totals['with_no_keys'] += total
            continue

        stats_query = f"""
        SELECT
            count() as total,
            countIf(bloom_key_phone IS NOT NULL) as with_phone_key,
            countIf(bloom_key_address IS NOT NULL) as with_address_key,
            countIf(bloom_key_phone IS NOT NULL AND bloom_key_address IS NOT NULL) as with_both_keys,
            countIf(bloom_key_phone IS NULL AND bloom_key_address IS NULL) as with_no_keys
        FROM {table}
        """

        result = execute_query(stats_query)
        if result:
            stats = result[0]
            stats['columns_exist'] = True
            all_stats[table] = stats

            # Accumulate totals
            for key in totals:
                totals[key] += stats.get(key, 0)

    all_stats['_totals'] = totals
    return all_stats


def add_search_key_columns(table_name: str = None) -> dict:
    """
    Add search_key_1 through search_key_8 columns to existing table(s).

    This is a migration function for existing tables that don't have
    the search key columns yet (Level 2 exact matching).

    Args:
        table_name: Specific table to migrate, or None for all SSN tables

    Returns:
        dict: Summary of migration results per table
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    from database.clickhouse_client import execute_query

    tables_to_migrate = [table_name] if table_name else ALL_SSN_TABLES
    results = {}

    # Define all 8 search key columns
    search_key_columns = [
        'search_key_1',  # FN:MN:LN:DOB_YEAR:PHONE
        'search_key_2',  # FN:MN:LN:DOB_YEAR:ADDR#:STREET:STATE
        'search_key_3',  # FN:LN:DOB_YEAR:PHONE
        'search_key_4',  # FN:LN:DOB_YEAR:ADDR#:STREET:STATE
        'search_key_5',  # FN:MN:LN:PHONE
        'search_key_6',  # FN:MN:LN:ADDR#:STREET:STATE
        'search_key_7',  # FN:LN:ADDR#:STREET:STATE
        'search_key_8',  # FN:LN:PHONE
    ]

    with get_connection() as client:
        for table in tables_to_migrate:
            # Check if table exists
            if not table_exists(table, client=client):
                logger.warning(f"Table {table} does not exist, skipping")
                continue

            table_results = {col: {'added': False, 'index_added': False} for col in search_key_columns}

            # Check existing columns
            columns = execute_query(
                f"DESCRIBE TABLE {table}",
                client=client
            )
            existing_columns = {row['name'] for row in columns}

            # Check existing indexes
            indexes = execute_query(
                f"SELECT name FROM system.data_skipping_indices WHERE table = '{table}'",
                client=client
            )
            existing_indexes = {row['name'] for row in indexes}

            # Add each search key column and index
            for col in search_key_columns:
                # Add column if not exists
                if col not in existing_columns:
                    logger.info(f"[{table}] Adding {col} column")
                    execute_command(
                        f"ALTER TABLE {table} ADD COLUMN {col} Nullable(String)",
                        client=client
                    )
                    table_results[col]['added'] = True
                    logger.info(f"[{table}] {col} column added")
                else:
                    logger.info(f"[{table}] {col} column already exists")

                # Add bloom index if not exists
                index_name = f"idx_{col}"
                if index_name not in existing_indexes:
                    logger.info(f"[{table}] Adding {index_name} index")
                    execute_command(
                        f"ALTER TABLE {table} ADD INDEX {index_name} {col} "
                        f"TYPE bloom_filter(0.001) GRANULARITY 1",
                        client=client
                    )
                    table_results[col]['index_added'] = True
                    logger.info(f"[{table}] {index_name} index added")
                else:
                    logger.info(f"[{table}] {index_name} index already exists")

            results[table] = table_results

    return results


def populate_search_keys(
    table_name: str = None,
    batch_size: int = 10000,
    update_chunk_size: int = 500,
    offset: int = 0,
    max_records: int = None
) -> dict:
    """
    Populate search_key_1 through search_key_8 for existing records.

    This function reads records in batches, generates search keys using
    search_key_generator, and updates the records in small chunks to avoid
    query size limits.

    Args:
        table_name: Specific table to populate, or None for all SSN tables
        batch_size: Number of records to read per batch
        update_chunk_size: Number of records per UPDATE query (default 500 to avoid query size limits)
        offset: Starting offset (for resuming migration)
        max_records: Maximum number of records to process per table (None for all)

    Returns:
        dict: Summary of migration results per table
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    from database.clickhouse_client import execute_query
    from database.search_key_generator import generate_search_keys

    tables_to_process = [table_name] if table_name else ALL_SSN_TABLES
    all_results = {}

    for table in tables_to_process:
        # Check if table exists
        if not table_exists(table):
            logger.warning(f"Table {table} does not exist, skipping")
            continue

        logger.info(f"Processing table: {table}")

        results = {
            'total_processed': 0,
            'keys_generated': {f'search_key_{i}': 0 for i in range(1, 9)},
            'batches_processed': 0,
            'errors': []
        }

        # Get total count
        count_result = execute_query(f"SELECT count() as cnt FROM {table}")
        total_records = count_result[0]['cnt'] if count_result else 0
        logger.info(f"[{table}] Total records: {total_records:,}")

        if max_records:
            total_records = min(total_records, max_records + offset)

        current_offset = offset

        while current_offset < total_records:
            try:
                # Fetch batch
                batch_query = f"""
                SELECT id, firstname, middlename, lastname, dob, phone, address, state
                FROM {table}
                ORDER BY id
                LIMIT {batch_size}
                OFFSET {current_offset}
                """
                records = execute_query(batch_query)

                if not records:
                    break

                # Generate search keys for batch
                # Dict: key_name -> list of (record_id, key_value)
                updates = {f'search_key_{i}': [] for i in range(1, 9)}

                for record in records:
                    record_id = record['id']
                    firstname = record.get('firstname', '')
                    middlename = record.get('middlename')
                    lastname = record.get('lastname', '')
                    dob = record.get('dob')
                    phone = record.get('phone')
                    address = record.get('address')
                    state = record.get('state')

                    # Generate all 8 search keys
                    keys = generate_search_keys(
                        firstname=firstname,
                        middlename=middlename,
                        lastname=lastname,
                        dob=dob,
                        phone=phone,
                        address=address,
                        state=state
                    )

                    # Collect updates for each key
                    for i in range(1, 9):
                        key_name = f'search_key_{i}'
                        key_value = keys[key_name]
                        if key_value:
                            # Escape single quotes in key
                            key_escaped = key_value.replace("'", "\\'")
                            updates[key_name].append((record_id, key_escaped))
                            results['keys_generated'][key_name] += 1

                # Update each search key column in chunks
                for key_name, key_updates in updates.items():
                    for i in range(0, len(key_updates), update_chunk_size):
                        chunk = key_updates[i:i + update_chunk_size]
                        if chunk:
                            case_parts = [f"WHEN id = {rid} THEN '{key}'" for rid, key in chunk]
                            ids = [str(rid) for rid, _ in chunk]
                            update_query = f"""
                            ALTER TABLE {table}
                            UPDATE {key_name} = CASE {' '.join(case_parts)} ELSE {key_name} END
                            WHERE id IN ({','.join(ids)})
                            """
                            execute_command(update_query)

                results['total_processed'] += len(records)
                results['batches_processed'] += 1
                current_offset += batch_size

                logger.info(
                    f"[{table}] Batch {results['batches_processed']}: processed {len(records)} records, "
                    f"total: {results['total_processed']:,}/{total_records:,} "
                    f"({100*results['total_processed']/total_records:.1f}%)"
                )

            except Exception as e:
                error_msg = f"[{table}] Error at offset {current_offset}: {str(e)}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
                current_offset += batch_size  # Skip problematic batch

        all_results[table] = results

    return all_results


def get_search_key_stats(table_name: str = None) -> dict:
    """
    Get statistics about search key coverage in the table(s).

    Args:
        table_name: Specific table to check, or None for all SSN tables

    Returns:
        dict: Statistics about search key population per table
    """
    if not CLICKHOUSE_AVAILABLE:
        raise ImportError("clickhouse-connect is not installed")

    from database.clickhouse_client import execute_query

    tables_to_check = [table_name] if table_name else ALL_SSN_TABLES
    all_stats = {}
    totals = {
        'total': 0,
        **{f'with_key_{i}': 0 for i in range(1, 9)},
        'with_any_key': 0,
        'with_no_keys': 0
    }

    for table in tables_to_check:
        if not table_exists(table):
            continue

        # Check if search_key columns exist
        columns = execute_query(f"DESCRIBE TABLE {table}")
        existing_columns = {row['name'] for row in columns}

        if 'search_key_1' not in existing_columns:
            # Columns not added yet
            count_result = execute_query(f"SELECT count() as total FROM {table}")
            total = count_result[0]['total'] if count_result else 0
            all_stats[table] = {
                'total': total,
                **{f'with_key_{i}': 0 for i in range(1, 9)},
                'with_any_key': 0,
                'with_no_keys': total,
                'columns_exist': False
            }
            totals['total'] += total
            totals['with_no_keys'] += total
            continue

        # Build stats query
        key_counts = ', '.join([
            f"countIf(search_key_{i} IS NOT NULL) as with_key_{i}"
            for i in range(1, 9)
        ])
        any_key_condition = ' OR '.join([
            f"search_key_{i} IS NOT NULL"
            for i in range(1, 9)
        ])
        no_key_condition = ' AND '.join([
            f"search_key_{i} IS NULL"
            for i in range(1, 9)
        ])

        stats_query = f"""
        SELECT
            count() as total,
            {key_counts},
            countIf({any_key_condition}) as with_any_key,
            countIf({no_key_condition}) as with_no_keys
        FROM {table}
        """

        result = execute_query(stats_query)
        if result:
            stats = result[0]
            stats['columns_exist'] = True
            all_stats[table] = stats

            # Accumulate totals
            for key in totals:
                totals[key] += stats.get(key, 0)

    all_stats['_totals'] = totals
    return all_stats


if __name__ == '__main__':
    # Simple test/demo
    logging.basicConfig(level=logging.INFO)

    print("ClickHouse Schema Initialization")
    print("=" * 50)

    try:
        # Initialize schema
        result = initialize_schema(include_duplicate_view=True)
        print(f"Initialization result: {result}")

        # Get schema info
        info = get_schema_info()
        print(f"Schema info: {info}")

        # Get table stats if table has data
        if info['ssn_table_exists'] and info['ssn_table_count'] > 0:
            stats = get_table_stats()
            print(f"Table stats: {stats}")

        print("\nSchema initialization completed successfully!")

    except ImportError as e:
        print(f"ClickHouse not available: {e}")
    except Exception as e:
        print(f"Schema initialization failed: {e}")
