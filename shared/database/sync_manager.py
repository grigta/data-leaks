"""
Sync Manager Module for SQLite to ClickHouse Synchronization

This module provides functionality for ongoing synchronization between SQLite and
ClickHouse databases. It tracks the last sync timestamp and incrementally syncs
new or modified records.

Features:
- Timestamp-based change tracking
- Incremental synchronization
- Configurable sync intervals
- Sync status monitoring
- Error handling with retry logic

Usage:
    from database.sync_manager import SyncManager
    manager = SyncManager()
    manager.run_sync()  # Sync all changes since last sync

Environment Variables:
    SQLITE_PATH: Path to SQLite database
    SYNC_BATCH_SIZE: Number of records per batch (default: 10000)
"""

import os
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from database.db_schema import get_connection, close_connection, DEFAULT_DB_PATH

# Module logger
logger = logging.getLogger(__name__)

# Configuration
DEFAULT_BATCH_SIZE = 10000
SYNC_TABLES = ['ssn_1', 'ssn_2', 'ssn_3']


class SyncManager:
    """
    Manages incremental synchronization from SQLite to ClickHouse.

    Uses a metadata table in ClickHouse to track the last sync timestamp.
    Only syncs records that have been modified since the last successful sync.
    """

    def __init__(
        self,
        sqlite_path: Optional[str] = None,
        batch_size: int = DEFAULT_BATCH_SIZE
    ):
        """
        Initialize SyncManager.

        Args:
            sqlite_path: Path to SQLite database
            batch_size: Number of records per batch
        """
        self.sqlite_path = sqlite_path or os.getenv('SQLITE_PATH', DEFAULT_DB_PATH)
        self.batch_size = int(os.getenv('SYNC_BATCH_SIZE', batch_size))
        self.logger = logging.getLogger(self.__class__.__name__)

        # Lazy load ClickHouse modules
        self._ch_client = None
        self._ch_schema = None

    @property
    def ch_client(self):
        """Lazy load ClickHouse client."""
        if self._ch_client is None:
            from database import clickhouse_client
            self._ch_client = clickhouse_client
        return self._ch_client

    @property
    def ch_schema(self):
        """Lazy load ClickHouse schema."""
        if self._ch_schema is None:
            from database import clickhouse_schema
            self._ch_schema = clickhouse_schema
        return self._ch_schema

    def get_last_sync_time(self) -> Optional[datetime]:
        """
        Get the last successful sync timestamp from ClickHouse.

        Returns:
            datetime or None if no previous sync
        """
        try:
            result = self.ch_client.execute_query(
                "SELECT value FROM sync_metadata WHERE key = 'last_sync_time' LIMIT 1"
            )
            if result and result[0].get('value'):
                return datetime.fromisoformat(result[0]['value'])
            return None
        except Exception as e:
            self.logger.warning(f"Could not get last sync time: {e}")
            return None

    def set_last_sync_time(self, sync_time: datetime) -> bool:
        """
        Update the last sync timestamp in ClickHouse.

        Args:
            sync_time: The sync timestamp to set

        Returns:
            bool: True if update succeeded
        """
        try:
            self.ch_client.execute_command(
                "INSERT INTO sync_metadata (key, value, updated_at) VALUES "
                "({key:String}, {value:String}, now())",
                parameters={
                    "key": "last_sync_time",
                    "value": sync_time.isoformat()
                }
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to set last sync time: {e}")
            return False

    def get_modified_records(
        self,
        table_name: str,
        since: Optional[datetime] = None,
        limit: int = None
    ) -> List[Dict]:
        """
        Get records modified since a given timestamp from SQLite.

        Note: SQLite tables need a last_modified column for this to work.
        If the column doesn't exist, returns all records.

        Args:
            table_name: SQLite table name
            since: Only return records modified after this time
            limit: Maximum number of records to return

        Returns:
            List of record dictionaries
        """
        connection = None
        try:
            connection = get_connection(self.sqlite_path)
            cursor = connection.cursor()

            # Check if last_modified column exists
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            has_last_modified = 'last_modified' in columns

            # Build query
            if has_last_modified and since:
                query = f"""
                    SELECT id, firstname, lastname, middlename, address, city, state, zip,
                           phone, ssn, dob, email
                    FROM {table_name}
                    WHERE last_modified > ?
                    ORDER BY last_modified
                """
                if limit:
                    query += f" LIMIT {limit}"
                cursor.execute(query, (since.isoformat(),))
            else:
                query = f"""
                    SELECT id, firstname, lastname, middlename, address, city, state, zip,
                           phone, ssn, dob, email
                    FROM {table_name}
                """
                if limit:
                    query += f" LIMIT {limit}"
                cursor.execute(query)

            column_names = ['id', 'firstname', 'lastname', 'middlename', 'address',
                           'city', 'state', 'zip', 'phone', 'ssn', 'dob', 'email']

            records = []
            for row in cursor.fetchall():
                record = dict(zip(column_names, row))
                record['source_table'] = table_name
                records.append(record)

            return records

        finally:
            if connection:
                close_connection(connection)

    def sync_records(self, records: List[Dict]) -> Tuple[int, int]:
        """
        Sync records to ClickHouse.

        Args:
            records: List of record dictionaries

        Returns:
            Tuple of (successful_count, failed_count)
        """
        if not records:
            return 0, 0

        # Transform records for ClickHouse
        ch_records = []
        for record in records:
            ch_records.append({
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
            })

        column_names = ['id', 'firstname', 'lastname', 'middlename', 'address',
                       'city', 'state', 'zip', 'phone', 'ssn', 'dob', 'email', 'source_table']

        try:
            written = self.ch_client.execute_batch(
                self.ch_schema.SSN_TABLE,
                ch_records,
                column_names=column_names
            )
            return written, len(ch_records) - written
        except Exception as e:
            self.logger.error(f"Failed to sync records to ClickHouse: {e}")
            return 0, len(ch_records)

    def run_sync(self, full_sync: bool = False) -> Dict:
        """
        Run synchronization from SQLite to ClickHouse.

        Args:
            full_sync: If True, sync all records regardless of timestamp

        Returns:
            Dictionary with sync statistics
        """
        self.logger.info("Starting sync...")
        start_time = datetime.now()

        # Ensure schema exists
        self.ch_schema.initialize_schema()

        # Get last sync time
        last_sync = None if full_sync else self.get_last_sync_time()
        if last_sync:
            self.logger.info(f"Last sync: {last_sync.isoformat()}")
        else:
            self.logger.info("No previous sync found, syncing all records")

        stats = {
            'tables_synced': [],
            'total_read': 0,
            'total_written': 0,
            'total_failed': 0,
            'start_time': start_time.isoformat(),
            'end_time': None,
            'duration_seconds': 0,
        }

        # Sync each table
        for table_name in SYNC_TABLES:
            self.logger.info(f"Syncing table: {table_name}")

            table_read = 0
            table_written = 0
            table_failed = 0
            offset = 0

            while True:
                # Get batch of records
                records = self.get_modified_records(
                    table_name,
                    since=last_sync,
                    limit=self.batch_size
                )

                if not records:
                    break

                # If we got fewer records than batch_size, we're done with this table
                is_last_batch = len(records) < self.batch_size

                table_read += len(records)
                written, failed = self.sync_records(records)
                table_written += written
                table_failed += failed

                if is_last_batch:
                    break

                offset += self.batch_size

            self.logger.info(
                f"Table {table_name}: read={table_read}, written={table_written}, failed={table_failed}"
            )

            stats['tables_synced'].append(table_name)
            stats['total_read'] += table_read
            stats['total_written'] += table_written
            stats['total_failed'] += table_failed

        # Update last sync time
        end_time = datetime.now()
        if stats['total_written'] > 0:
            self.set_last_sync_time(end_time)

        stats['end_time'] = end_time.isoformat()
        stats['duration_seconds'] = (end_time - start_time).total_seconds()

        self.logger.info(
            f"Sync complete: read={stats['total_read']}, written={stats['total_written']}, "
            f"failed={stats['total_failed']}, duration={stats['duration_seconds']:.1f}s"
        )

        return stats

    def get_sync_status(self) -> Dict:
        """
        Get current sync status and statistics.

        Returns:
            Dictionary with sync status
        """
        last_sync = self.get_last_sync_time()

        # Get counts from both databases
        sqlite_counts = {}
        connection = None
        try:
            connection = get_connection(self.sqlite_path)
            cursor = connection.cursor()
            for table in SYNC_TABLES:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                sqlite_counts[table] = cursor.fetchone()[0]
        except Exception as e:
            self.logger.error(f"Error getting SQLite counts: {e}")
        finally:
            if connection:
                close_connection(connection)

        # Get ClickHouse count
        clickhouse_count = 0
        try:
            clickhouse_count = self.ch_client.get_table_count(self.ch_schema.SSN_TABLE)
        except Exception as e:
            self.logger.error(f"Error getting ClickHouse count: {e}")

        total_sqlite = sum(sqlite_counts.values())

        return {
            'last_sync_time': last_sync.isoformat() if last_sync else None,
            'sqlite_counts': sqlite_counts,
            'sqlite_total': total_sqlite,
            'clickhouse_count': clickhouse_count,
            'sync_delta': total_sqlite - clickhouse_count,
            'is_synced': total_sqlite == clickhouse_count,
        }


def run_scheduled_sync(interval_minutes: int = 15):
    """
    Run sync on a schedule.

    Args:
        interval_minutes: Minutes between syncs
    """
    import time

    manager = SyncManager()
    logger.info(f"Starting scheduled sync every {interval_minutes} minutes")

    while True:
        try:
            stats = manager.run_sync()
            logger.info(f"Scheduled sync complete: {stats['total_written']} records synced")
        except Exception as e:
            logger.error(f"Scheduled sync failed: {e}")

        time.sleep(interval_minutes * 60)


if __name__ == '__main__':
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description='SQLite to ClickHouse Sync Manager')
    parser.add_argument('--full', action='store_true', help='Force full sync')
    parser.add_argument('--status', action='store_true', help='Show sync status')
    parser.add_argument('--scheduled', type=int, metavar='MINUTES', help='Run scheduled sync')

    args = parser.parse_args()

    manager = SyncManager()

    if args.status:
        status = manager.get_sync_status()
        print("Sync Status:")
        print(f"  Last sync: {status['last_sync_time'] or 'Never'}")
        print(f"  SQLite total: {status['sqlite_total']:,}")
        print(f"  ClickHouse count: {status['clickhouse_count']:,}")
        print(f"  Delta: {status['sync_delta']:,}")
        print(f"  Is synced: {status['is_synced']}")
    elif args.scheduled:
        run_scheduled_sync(args.scheduled)
    else:
        stats = manager.run_sync(full_sync=args.full)
        print(f"Sync complete: {stats['total_written']} records synced in {stats['duration_seconds']:.1f}s")
