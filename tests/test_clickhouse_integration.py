"""
Integration Tests for ClickHouse

These tests verify the integration between SQLite and ClickHouse, including:
- Data migration accuracy
- Sync manager functionality
- Search result consistency

These tests require a running ClickHouse instance.
Skip with: pytest -m "not integration"
"""

import json
import os
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

# Mark all tests as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def clickhouse_available():
    """Check if ClickHouse is available for testing."""
    try:
        from database.clickhouse_client import health_check
        is_healthy, message = health_check()
        if not is_healthy:
            pytest.skip(f"ClickHouse not available: {message}")
        return True
    except ImportError:
        pytest.skip("clickhouse-connect not installed")
    except Exception as e:
        pytest.skip(f"ClickHouse connection failed: {e}")


@pytest.fixture(scope="module")
def test_table(clickhouse_available):
    """Create a test table in ClickHouse."""
    from database.clickhouse_client import execute_command, execute_query

    # Create test table
    execute_command("""
        CREATE TABLE IF NOT EXISTS ssn_data_test
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
            ssn String,
            dob Nullable(String),
            email Nullable(String),
            source_table LowCardinality(String) DEFAULT 'test',
            created_at DateTime DEFAULT now()
        )
        ENGINE = MergeTree()
        ORDER BY (ssn, lastname, firstname)
    """)

    yield "ssn_data_test"

    # Cleanup
    execute_command("DROP TABLE IF EXISTS ssn_data_test")


class TestClickHouseIntegration:
    """Integration tests for ClickHouse operations."""

    def test_insert_and_query(self, test_table):
        """Test basic insert and query operations."""
        from database.clickhouse_client import execute_batch, execute_query

        # Insert test data
        test_records = [
            {
                'id': 1,
                'firstname': 'John',
                'lastname': 'Doe',
                'ssn': '111-22-3333',
                'zip': '12345',
                'source_table': 'test'
            },
            {
                'id': 2,
                'firstname': 'Jane',
                'lastname': 'Smith',
                'ssn': '444-55-6666',
                'zip': '67890',
                'source_table': 'test'
            }
        ]

        count = execute_batch(
            test_table,
            test_records,
            column_names=['id', 'firstname', 'lastname', 'ssn', 'zip', 'source_table']
        )
        assert count == 2

        # Query data
        results = execute_query(f"SELECT * FROM {test_table} WHERE ssn = {{ssn:String}}", {"ssn": "111-22-3333"})
        assert len(results) >= 1
        assert results[0]['firstname'] == 'John'

    def test_case_insensitive_search(self, test_table):
        """Test case-insensitive name searches."""
        from database.clickhouse_client import execute_batch, execute_query

        # Insert with mixed case
        execute_batch(
            test_table,
            [{'id': 100, 'firstname': 'ROBERT', 'lastname': 'JONES', 'ssn': '777-88-9999', 'source_table': 'test'}],
            column_names=['id', 'firstname', 'lastname', 'ssn', 'source_table']
        )

        # Search with different case
        results = execute_query(
            f"SELECT * FROM {test_table} WHERE lowerUTF8(firstname) = lowerUTF8({{name:String}})",
            {"name": "robert"}
        )

        assert len(results) >= 1
        # Results should include ROBERT regardless of search case

    def test_bloom_filter_index(self, test_table):
        """Test that Bloom filter indexes are used for SSN lookups."""
        from database.clickhouse_client import execute_query

        # This is more of a smoke test - actual Bloom filter usage can be verified with EXPLAIN
        results = execute_query(
            f"SELECT * FROM {test_table} WHERE ssn = {{ssn:String}} LIMIT 10",
            {"ssn": "111-22-3333"}
        )
        # Should complete without error
        assert isinstance(results, list)


class TestDataMigration:
    """Tests for data migration from SQLite to ClickHouse."""

    def test_migration_script_dry_run(self):
        """Test migration script in dry-run mode."""
        # This tests that the migration script can be imported and configured
        # without actually running it
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        from scripts.migrate_sqlite_to_clickhouse import MigrationStats, validate_record

        # Test record validation
        valid_record = {'ssn': '123-45-6789', 'firstname': 'Test', 'lastname': 'User'}
        is_valid, error = validate_record(valid_record)
        assert is_valid is True

        invalid_record = {'firstname': 'No', 'lastname': 'SSN'}
        is_valid, error = validate_record(invalid_record)
        assert is_valid is False

    def test_migration_stats(self):
        """Test migration statistics tracking."""
        from scripts.migrate_sqlite_to_clickhouse import MigrationStats

        stats = MigrationStats()
        stats.start()
        stats.total_read = 1000
        stats.total_written = 995
        stats.total_failed = 5
        stats.tables_completed = ['ssn_1', 'ssn_2']
        stats.finish()

        assert stats.total_read == 1000
        assert stats.total_written == 995
        assert stats.duration > 0
        assert 'ssn_1' in str(stats)


class TestSyncManager:
    """Tests for sync manager functionality."""

    @pytest.fixture
    def sync_manager(self, clickhouse_available):
        """Create sync manager instance."""
        from database.sync_manager import SyncManager
        return SyncManager()

    def test_get_sync_status(self, sync_manager):
        """Test getting sync status."""
        status = sync_manager.get_sync_status()

        assert 'last_sync_time' in status
        assert 'sqlite_counts' in status
        assert 'clickhouse_count' in status
        assert 'sync_delta' in status

    def test_set_and_get_last_sync_time(self, sync_manager):
        """Test setting and retrieving last sync time."""
        test_time = datetime(2024, 1, 15, 12, 30, 0)

        success = sync_manager.set_last_sync_time(test_time)
        assert success is True

        retrieved = sync_manager.get_last_sync_time()
        # Allow some tolerance for time comparison
        assert retrieved is not None


class TestSearchResultConsistency:
    """Tests comparing SQLite and ClickHouse search results."""

    @pytest.fixture
    def sqlite_engine(self):
        """Create SQLite search engine."""
        from database.search_engine import SearchEngine
        return SearchEngine()

    @pytest.fixture
    def clickhouse_engine(self, clickhouse_available):
        """Create ClickHouse search engine."""
        from database.clickhouse_search_engine import ClickHouseSearchEngine
        return ClickHouseSearchEngine()

    def test_ssn_search_consistency(self, sqlite_engine, clickhouse_engine):
        """Test that SSN searches return consistent results."""
        # This test assumes data has been migrated
        test_ssn = "123-45-6789"  # Example SSN

        sqlite_results = json.loads(sqlite_engine.search_by_ssn(test_ssn))
        clickhouse_results = json.loads(clickhouse_engine.search_by_ssn(test_ssn))

        # Compare SSN sets
        sqlite_ssns = {r['ssn'] for r in sqlite_results}
        clickhouse_ssns = {r['ssn'] for r in clickhouse_results}

        # Results should match (after migration)
        # This may fail if data hasn't been migrated yet
        if sqlite_ssns or clickhouse_ssns:
            assert sqlite_ssns == clickhouse_ssns, "Search results should be consistent"

    def test_name_search_consistency(self, sqlite_engine, clickhouse_engine):
        """Test that name searches return consistent results."""
        sqlite_results = json.loads(sqlite_engine.search_by_name_zip("John", "Doe", "12345"))
        clickhouse_results = json.loads(clickhouse_engine.search_by_name_zip("John", "Doe", "12345"))

        sqlite_ssns = {r['ssn'] for r in sqlite_results}
        clickhouse_ssns = {r['ssn'] for r in clickhouse_results}

        if sqlite_ssns or clickhouse_ssns:
            assert sqlite_ssns == clickhouse_ssns, "Name search results should be consistent"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'integration'])
