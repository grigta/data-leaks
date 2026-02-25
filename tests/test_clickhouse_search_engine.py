"""
Tests for ClickHouse Search Engine

This module contains tests for the ClickHouse search engine, mirroring the
test cases from test_search_engine.py but adapted for ClickHouse.

Run tests:
    pytest tests/test_clickhouse_search_engine.py -v
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

# Mock clickhouse_connect before importing modules that use it
import sys
sys.modules['clickhouse_connect'] = MagicMock()
sys.modules['clickhouse_connect.driver'] = MagicMock()
sys.modules['clickhouse_connect.driver.client'] = MagicMock()


class TestClickHouseSearchEngine:
    """Tests for ClickHouseSearchEngine class."""

    @pytest.fixture
    def mock_clickhouse(self):
        """Create mock ClickHouse client."""
        with patch('database.clickhouse_client.CLICKHOUSE_AVAILABLE', True):
            with patch('database.clickhouse_client.get_pool') as mock_pool:
                mock_client = Mock()
                mock_pool.return_value.get_client.return_value = mock_client
                yield mock_client

    @pytest.fixture
    def search_engine(self, mock_clickhouse):
        """Create a ClickHouseSearchEngine instance with mocked ClickHouse."""
        with patch('database.clickhouse_client.CLICKHOUSE_AVAILABLE', True):
            from database.clickhouse_search_engine import ClickHouseSearchEngine
            return ClickHouseSearchEngine()

    def test_search_by_ssn_valid_full(self, search_engine, mock_clickhouse):
        """Test search by full SSN (9 digits)."""
        # Setup mock
        mock_result = Mock()
        mock_result.column_names = ['id', 'firstname', 'lastname', 'ssn', 'source_table']
        mock_result.result_rows = [(1, 'John', 'Doe', '123-45-6789', 'ssn_1')]
        mock_clickhouse.query.return_value = mock_result

        with patch('database.clickhouse_client.execute_query') as mock_query:
            mock_query.return_value = [
                {'id': 1, 'firstname': 'John', 'lastname': 'Doe', 'ssn': '123-45-6789', 'source_table': 'ssn_1'}
            ]

            result = search_engine.search_by_ssn("123-45-6789")
            data = json.loads(result)

            assert len(data) == 1
            assert data[0]['ssn'] == '123-45-6789'

    def test_search_by_ssn_valid_last4(self, search_engine, mock_clickhouse):
        """Test search by last 4 digits of SSN."""
        with patch('database.clickhouse_client.execute_query') as mock_query:
            mock_query.return_value = [
                {'id': 1, 'firstname': 'John', 'lastname': 'Doe', 'ssn': '123-45-6789', 'source_table': 'ssn_1'},
                {'id': 2, 'firstname': 'Jane', 'lastname': 'Smith', 'ssn': '987-65-6789', 'source_table': 'ssn_2'}
            ]

            result = search_engine.search_by_ssn("6789")
            data = json.loads(result)

            assert len(data) == 2

    def test_search_by_ssn_invalid_format(self, search_engine):
        """Test search with invalid SSN format returns empty results."""
        result = search_engine.search_by_ssn("123")  # Too short
        data = json.loads(result)
        assert len(data) == 0

    def test_search_by_name_zip(self, search_engine, mock_clickhouse):
        """Test search by name and ZIP code."""
        with patch('database.clickhouse_client.execute_query') as mock_query:
            mock_query.return_value = [
                {'id': 1, 'firstname': 'John', 'lastname': 'Doe', 'zip': '12345', 'ssn': '123-45-6789'}
            ]

            result = search_engine.search_by_name_zip("John", "Doe", "12345")
            data = json.loads(result)

            assert len(data) == 1
            assert data[0]['firstname'] == 'John'
            assert data[0]['zip'] == '12345'

    def test_search_by_name_zip_missing_params(self, search_engine):
        """Test search with missing required parameters."""
        result = search_engine.search_by_name_zip("", "Doe", "12345")
        data = json.loads(result)
        assert len(data) == 0

        result = search_engine.search_by_name_zip("John", "", "12345")
        data = json.loads(result)
        assert len(data) == 0

    def test_search_by_name_address(self, search_engine, mock_clickhouse):
        """Test search by name and address."""
        with patch('database.clickhouse_client.execute_query') as mock_query:
            mock_query.return_value = [
                {'id': 1, 'firstname': 'John', 'lastname': 'Doe', 'address': '123 Main St', 'ssn': '123-45-6789'}
            ]

            result = search_engine.search_by_name_address("John", "Doe", "123 Main St")
            data = json.loads(result)

            assert len(data) == 1
            assert '123 Main St' in data[0]['address']

    def test_search_by_fields_with_phone(self, search_engine, mock_clickhouse):
        """Test search_by_fields with phone number."""
        with patch.object(search_engine, '_search_by_phone_match') as mock_phone:
            mock_phone.return_value = [
                {'id': 1, 'firstname': 'John', 'lastname': 'Doe', 'phone': '555-123-4567', 'ssn': '123-45-6789'}
            ]

            result = search_engine.search_by_fields("John", "Doe", phone="555-123-4567")
            data = json.loads(result)

            assert len(data) == 1
            mock_phone.assert_called_once()

    def test_search_by_fields_priority(self, search_engine, mock_clickhouse):
        """Test that search_by_fields uses correct priority."""
        with patch.object(search_engine, '_search_by_phone_match') as mock_phone:
            with patch.object(search_engine, '_search_by_city_state_match') as mock_city:
                # Phone returns empty, should fall through to city+state
                mock_phone.return_value = []
                mock_city.return_value = [
                    {'id': 1, 'firstname': 'John', 'lastname': 'Doe', 'city': 'NYC', 'state': 'NY'}
                ]

                result = search_engine.search_by_fields(
                    "John", "Doe", phone="555-123-4567", city="NYC", state="NY"
                )
                data = json.loads(result)

                assert len(data) == 1
                mock_phone.assert_called_once()
                mock_city.assert_called_once()

    def test_search_by_searchbug_data(self, search_engine, mock_clickhouse):
        """Test search_by_searchbug_data with priority matching."""
        with patch.object(search_engine, '_search_by_phone_match') as mock_phone:
            mock_phone.return_value = [
                {'id': 1, 'firstname': 'John', 'lastname': 'Doe', 'ssn': '123-45-6789'}
            ]

            results = search_engine.search_by_searchbug_data(
                "John", "Doe",
                all_phones=["555-123-4567"],
                all_zips=["12345"]
            )

            assert len(results) == 1
            mock_phone.assert_called_once()

    def test_limit_validation(self, search_engine):
        """Test limit parameter validation."""
        assert search_engine._safe_limit(None) == 100
        assert search_engine._safe_limit(50) == 50
        assert search_engine._safe_limit(0) == 1  # Minimum 1
        assert search_engine._safe_limit(-1) == 100  # Invalid, use default
        assert search_engine._safe_limit("invalid") == 100  # Invalid string

    def test_ssn_masking(self, search_engine):
        """Test SSN masking function."""
        assert search_engine._mask_ssn("123-45-6789") == "***-**-6789"
        assert search_engine._mask_ssn("123456789") == "***-**-6789"
        assert search_engine._mask_ssn("") == "***"
        assert search_engine._mask_ssn(None) == "***"


class TestClickHouseClient:
    """Tests for ClickHouse client module."""

    def test_config_from_environment(self):
        """Test configuration from environment variables."""
        with patch.dict('os.environ', {
            'CLICKHOUSE_HOST': 'test-host',
            'CLICKHOUSE_PORT': '9001',
            'CLICKHOUSE_DB': 'test_db',
            'CLICKHOUSE_USER': 'test_user',
            'CLICKHOUSE_PASSWORD': 'test_pass'
        }):
            from database.clickhouse_client import ClickHouseConfig
            config = ClickHouseConfig()

            assert config.host == 'test-host'
            assert config.port == 9001
            assert config.database == 'test_db'
            assert config.user == 'test_user'
            assert config.password == 'test_pass'

    def test_config_defaults(self):
        """Test configuration defaults."""
        with patch.dict('os.environ', {}, clear=True):
            from database.clickhouse_client import ClickHouseConfig
            config = ClickHouseConfig()

            assert config.host == 'clickhouse'
            assert config.port == 9000
            assert config.database == 'ssn_database'


class TestSearchEngineFactory:
    """Tests for Search Engine Factory."""

    def test_get_engine_type_sqlite(self):
        """Test factory returns SQLite engine by default."""
        with patch.dict('os.environ', {'SEARCH_ENGINE_TYPE': 'sqlite'}):
            from database.search_engine_factory import get_engine_type, SearchEngineType
            assert get_engine_type() == SearchEngineType.SQLITE

    def test_get_engine_type_clickhouse(self):
        """Test factory returns ClickHouse engine when configured."""
        with patch.dict('os.environ', {'SEARCH_ENGINE_TYPE': 'clickhouse'}):
            from database.search_engine_factory import get_engine_type, SearchEngineType
            assert get_engine_type() == SearchEngineType.CLICKHOUSE

    def test_get_engine_type_hybrid(self):
        """Test factory returns Hybrid engine when configured."""
        with patch.dict('os.environ', {'SEARCH_ENGINE_TYPE': 'hybrid'}):
            from database.search_engine_factory import get_engine_type, SearchEngineType
            assert get_engine_type() == SearchEngineType.HYBRID

    def test_get_engine_type_unknown_defaults_to_sqlite(self):
        """Test factory defaults to SQLite for unknown types."""
        with patch.dict('os.environ', {'SEARCH_ENGINE_TYPE': 'unknown'}):
            from database.search_engine_factory import get_engine_type, SearchEngineType
            assert get_engine_type() == SearchEngineType.SQLITE


class TestSQLInjectionPrevention:
    """Tests for SQL injection prevention in ClickHouse queries."""

    @pytest.fixture
    def search_engine(self):
        """Create search engine with mocked ClickHouse."""
        with patch('database.clickhouse_client.CLICKHOUSE_AVAILABLE', True):
            with patch('database.clickhouse_client.get_pool'):
                from database.clickhouse_search_engine import ClickHouseSearchEngine
                return ClickHouseSearchEngine()

    def test_ssn_injection_attempt(self, search_engine):
        """Test that SSN injection attempts are handled safely."""
        # These should be rejected by validation
        malicious_inputs = [
            "'; DROP TABLE ssn_data; --",
            "1 OR 1=1",
            "1; SELECT * FROM users",
            "UNION SELECT * FROM ssn_data",
        ]

        for malicious_input in malicious_inputs:
            result = search_engine.search_by_ssn(malicious_input)
            data = json.loads(result)
            assert len(data) == 0, f"Should return empty for: {malicious_input}"

    def test_name_injection_attempt(self, search_engine):
        """Test that name injection attempts are sanitized."""
        with patch('database.clickhouse_client.execute_query') as mock_query:
            mock_query.return_value = []

            # These should be sanitized, not cause errors
            result = search_engine.search_by_name_zip(
                "John'; DROP TABLE--",
                "Doe",
                "12345"
            )
            data = json.loads(result)
            # Should complete without error, returning empty or sanitized results
            assert isinstance(data, list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
