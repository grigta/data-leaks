# ClickHouse Migration Guide

This document describes the migration from SQLite to ClickHouse for the SSN search database.

## Overview

ClickHouse replaces SQLite as the backend for SSN data searches. The migration consolidates 3 SQLite tables (ssn_1, ssn_2, ssn_3) into a single ClickHouse table with optimized column storage and Bloom filter indexes.

### Architecture Comparison

| Aspect | SQLite (Current) | ClickHouse (New) |
|--------|------------------|------------------|
| Tables | 3 tables (ssn_1, ssn_2, ssn_3) | 1 table (ssn_data) |
| Query Pattern | UNION ALL across 3 tables | Single table query |
| Indexes | B-tree composite indexes | Bloom filters + skip indexes |
| Storage | Row-oriented | Column-oriented |
| Compression | Minimal | Excellent (LZ4/ZSTD) |
| Partitioning | Manual (3 tables) | Automatic (hash-based) |
| Scalability | Limited (single file) | Horizontal (sharding ready) |

## Quick Start

### 1. Start ClickHouse

```bash
# Start all services including ClickHouse
docker-compose up -d

# Verify ClickHouse is running
docker-compose logs clickhouse
```

### 2. Initialize Schema

```bash
# Connect to public_api container
docker-compose exec public_api bash

# Initialize ClickHouse schema
python -c "from database.clickhouse_schema import initialize_schema; initialize_schema()"
```

### 3. Run Migration

```bash
# Dry run first to verify
python scripts/migrate_sqlite_to_clickhouse.py --dry-run

# Full migration
python scripts/migrate_sqlite_to_clickhouse.py

# With custom batch size for large databases
python scripts/migrate_sqlite_to_clickhouse.py --batch-size 50000
```

### 4. Enable ClickHouse Search

```bash
# Update .env to use ClickHouse
SEARCH_ENGINE_TYPE=clickhouse

# Restart services
docker-compose up -d public_api admin_api
```

## Configuration

### Environment Variables

```bash
# ClickHouse Connection
CLICKHOUSE_HOST=clickhouse
CLICKHOUSE_PORT=9000
CLICKHOUSE_HTTP_PORT=8123
CLICKHOUSE_DB=ssn_database
CLICKHOUSE_USER=ssn_user
CLICKHOUSE_PASSWORD=your_strong_password

# Connection Pool
CLICKHOUSE_MAX_CONNECTIONS=10

# Search Engine Mode
# Options: sqlite, clickhouse, hybrid
SEARCH_ENGINE_TYPE=sqlite

# Dual Writes (during migration)
ENABLE_CLICKHOUSE_WRITES=false
```

### Search Engine Modes

- **sqlite**: Use SQLite only (default, backwards compatible)
- **clickhouse**: Use ClickHouse only (recommended after migration)
- **hybrid**: Query both and compare results (for validation)

## Migration Phases

### Phase 1: Infrastructure Setup

1. Deploy ClickHouse container
2. Configure environment variables
3. Initialize schema

```bash
docker-compose up -d clickhouse
docker-compose exec public_api python -c "from database.clickhouse_schema import initialize_schema; initialize_schema()"
```

### Phase 2: Data Migration

1. Run migration script
2. Verify data integrity

```bash
# Run migration
python scripts/migrate_sqlite_to_clickhouse.py

# Verify counts match
python -c "
from database.sync_manager import SyncManager
m = SyncManager()
print(m.get_sync_status())
"
```

### Phase 3: Dual-Write Mode

1. Enable ClickHouse writes
2. Monitor for errors

```bash
# Enable dual writes
ENABLE_CLICKHOUSE_WRITES=true

# Check logs for sync errors
docker-compose logs -f public_api | grep -i clickhouse
```

### Phase 4: Hybrid Validation

1. Enable hybrid mode
2. Compare results

```bash
SEARCH_ENGINE_TYPE=hybrid

# Check logs for discrepancies
docker-compose logs public_api | grep "Hybrid search"
```

### Phase 5: Full Migration

1. Switch to ClickHouse only
2. Keep SQLite as backup

```bash
SEARCH_ENGINE_TYPE=clickhouse
```

## Schema Details

### SSN Data Table

```sql
CREATE TABLE ssn_data
(
    id UInt64,
    firstname String,
    lastname String,
    middlename Nullable(String),
    address Nullable(String),
    city Nullable(String),
    state Nullable(String),
    zip Nullable(String),
    phone Nullable(String),
    email Nullable(String),
    ssn String,
    dob Nullable(String),
    source_table LowCardinality(String),
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now(),

    -- Bloom filter indexes
    INDEX bloom_ssn ssn TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX bloom_lastname lastname TYPE bloom_filter(0.01) GRANULARITY 4,
    INDEX bloom_firstname firstname TYPE bloom_filter(0.01) GRANULARITY 4,
    INDEX bloom_zip zip TYPE bloom_filter(0.01) GRANULARITY 4,
    INDEX bloom_phone phone TYPE bloom_filter(0.01) GRANULARITY 4,
    INDEX bloom_email email TYPE bloom_filter(0.01) GRANULARITY 4,

    -- N-gram index for fuzzy matching
    INDEX ngram_address address TYPE ngrambf_v1(4, 256, 2, 0) GRANULARITY 4
)
ENGINE = MergeTree()
PARTITION BY cityHash64(ssn) % 256
ORDER BY (ssn, lastname, firstname)
```

### Bloom Filter Configuration

| Column | False Positive Rate | Granularity | Purpose |
|--------|---------------------|-------------|---------|
| ssn | 0.01 (1%) | 1 | Exact SSN lookups |
| lastname | 0.01 (1%) | 4 | Name searches |
| firstname | 0.01 (1%) | 4 | Name searches |
| zip | 0.01 (1%) | 4 | Location filtering |
| phone | 0.01 (1%) | 4 | Phone lookups |
| email | 0.01 (1%) | 4 | Email lookups |

## Monitoring

### Query Performance

```sql
-- Check slow queries
SELECT
    query,
    query_duration_ms,
    read_rows,
    read_bytes
FROM system.query_log
WHERE type = 'QueryFinish'
    AND query_duration_ms > 100
ORDER BY query_duration_ms DESC
LIMIT 10;
```

### Bloom Filter Usage

```sql
-- Check index usage
SELECT
    table,
    name,
    type,
    expr,
    granularity
FROM system.data_skipping_indices
WHERE database = 'ssn_database';
```

### Table Statistics

```sql
-- Table size and parts
SELECT
    table,
    sum(rows) as rows,
    formatReadableSize(sum(bytes)) as size,
    count() as parts
FROM system.parts
WHERE database = 'ssn_database' AND active
GROUP BY table;
```

## Troubleshooting

### Connection Issues

```bash
# Check ClickHouse status
docker-compose exec clickhouse clickhouse-client --query "SELECT 1"

# Check logs
docker-compose logs clickhouse
```

### Migration Errors

```bash
# Resume from specific table
python scripts/migrate_sqlite_to_clickhouse.py --start-table ssn_2

# Check for validation errors
python scripts/migrate_sqlite_to_clickhouse.py -v 2>&1 | grep "Validation"
```

### Performance Issues

```bash
# Optimize table after bulk insert
docker-compose exec clickhouse clickhouse-client --query "OPTIMIZE TABLE ssn_data FINAL"
```

## Rollback

If issues occur, rollback to SQLite:

```bash
# Switch back to SQLite
SEARCH_ENGINE_TYPE=sqlite
ENABLE_CLICKHOUSE_WRITES=false

# Restart services
docker-compose up -d public_api admin_api
```

## Best Practices

1. **Always backup SQLite before migration**
2. **Use dry-run mode first**
3. **Monitor during hybrid mode**
4. **Keep SQLite as backup after migration**
5. **Run OPTIMIZE TABLE after large bulk inserts**

## Files Reference

| File | Purpose |
|------|---------|
| `shared/database/clickhouse_client.py` | Connection pooling and query execution |
| `shared/database/clickhouse_schema.py` | Schema definition and initialization |
| `shared/database/clickhouse_search_engine.py` | Search engine implementation |
| `shared/database/search_engine_factory.py` | Factory for engine selection |
| `shared/database/sync_manager.py` | Incremental synchronization |
| `scripts/migrate_sqlite_to_clickhouse.py` | One-time migration script |
