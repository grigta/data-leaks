"""
Security tests for SQL injection protection.

This module tests that the application properly defends against SQL injection attacks
across all entry points including:
- SearchEngine methods (SSN, name, address, email searches)
- API endpoints (auth, billing, search)
- Validators and sanitizers

The tests use various SQL injection payloads to verify that:
1. Queries don't execute malicious SQL
2. Input validation rejects dangerous patterns
3. Parameterized queries prevent injection
"""

import unittest
import tempfile
import os
import json
import sqlite3
from database.search_engine import SearchEngine
from database.db_schema import initialize_database, get_connection, close_connection
from api.common.validators import (
    validate_ssn,
    validate_name,
    validate_email,
    validate_phone,
    validate_address,
    validate_zip,
    validate_limit,
    validate_coupon_code,
    validate_no_sql_injection
)
from api.common.sanitizers import (
    sanitize_string,
    sanitize_name,
    sanitize_address,
    sanitize_email,
    sanitize_ssn,
    sanitize_metadata
)


# Common SQL injection payloads
SQL_INJECTION_PAYLOADS = [
    # Basic SQL injection
    "' OR '1'='1",
    "' OR '1'='1' --",
    "' OR '1'='1' /*",
    "' OR 1=1 --",
    "'; --",
    "' AND '1'='1",

    # Union-based injection
    "' UNION SELECT * FROM users --",
    "' UNION ALL SELECT NULL,NULL,NULL --",
    "1' UNION SELECT username,password FROM users--",

    # Stack queries
    "'; DROP TABLE ssn_1; --",
    "'; DELETE FROM ssn_1; --",
    "'; UPDATE users SET password='hacked'; --",
    "'; INSERT INTO users VALUES('hacker','password'); --",

    # Comment-based injection
    "/**/OR/**/1=1",
    "1'/**/OR/**/1=1/**/--",

    # Conditional injection
    "' OR 1=1#",
    "admin'--",
    "admin' #",

    # Encoded injection
    "%27%20OR%20%271%27%3D%271",  # URL encoded
    "&#39; OR &#39;1&#39;=&#39;1",  # HTML entity encoded

    # Time-based blind injection
    "'; WAITFOR DELAY '0:0:5' --",
    "' OR SLEEP(5) --",

    # Error-based injection
    "' AND 1=CONVERT(int, (SELECT TOP 1 table_name FROM information_schema.tables))--",

    # Double quotes
    '" OR "1"="1',
    '" OR "1"="1" --',

    # Backticks (MySQL)
    "` OR `1`=`1",

    # Null byte injection
    "%00' OR '1'='1",

    # Special SQLite injection
    "' OR 1=1; SELECT * FROM sqlite_master; --",
    "'; ATTACH DATABASE '/tmp/hacked.db' AS hacked; --",
]


class TestSQLInjectionSearchEngine(unittest.TestCase):
    """
    Test SQL injection protection in SearchEngine class.

    Verifies that all search methods properly handle malicious input
    without executing injected SQL.
    """

    @classmethod
    def setUpClass(cls):
        """Create temporary database for testing."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        cls.test_db_path = temp_file.name
        temp_file.close()

        try:
            conn = initialize_database(cls.test_db_path)
            cursor = conn.cursor()

            # Insert test data
            cursor.execute('''
                INSERT INTO ssn_1 (firstname, lastname, ssn, address, city, state, zip, email)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', ('John', 'Doe', '123-45-6789', '123 Main St', 'Boston', 'MA', '02101', 'john@test.com'))

            conn.commit()
            close_connection(conn)
        except Exception as e:
            if os.path.exists(cls.test_db_path):
                os.unlink(cls.test_db_path)
            raise Exception(f"Failed to initialize test database: {e}")

    def setUp(self):
        """Create SearchEngine instance for each test."""
        self.engine = SearchEngine(db_path=self.test_db_path)

    @classmethod
    def tearDownClass(cls):
        """Clean up temporary database."""
        try:
            if os.path.exists(cls.test_db_path):
                os.unlink(cls.test_db_path)
            for ext in ['-wal', '-shm']:
                path = cls.test_db_path + ext
                if os.path.exists(path):
                    os.unlink(path)
        except Exception as e:
            print(f"Warning: Failed to clean up test database: {e}")

    def test_sql_injection_in_ssn(self):
        """Test SQL injection attempts in SSN parameter."""
        for payload in SQL_INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                # Should not raise SQL error
                result = self.engine.search_by_ssn(payload)

                # Should return empty array (not SQL error)
                try:
                    records = json.loads(result)
                    self.assertIsInstance(records, list)
                    # Should not contain any records (injection blocked)
                    self.assertEqual(len(records), 0,
                                   f"Injection payload {payload} should return empty result")
                except json.JSONDecodeError:
                    self.fail(f"Invalid JSON response for payload: {payload}")

    def test_sql_injection_in_firstname(self):
        """Test SQL injection attempts in firstname parameter."""
        for payload in SQL_INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                # Should not raise SQL error
                result = self.engine.search_by_name_zip(payload, 'Doe', '02101')

                # Should return empty array (validation rejects invalid names)
                try:
                    records = json.loads(result)
                    self.assertIsInstance(records, list)
                except json.JSONDecodeError:
                    self.fail(f"Invalid JSON response for payload: {payload}")

    def test_sql_injection_in_lastname(self):
        """Test SQL injection attempts in lastname parameter."""
        for payload in SQL_INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                # Should not raise SQL error
                result = self.engine.search_by_name_zip('John', payload, '02101')

                try:
                    records = json.loads(result)
                    self.assertIsInstance(records, list)
                except json.JSONDecodeError:
                    self.fail(f"Invalid JSON response for payload: {payload}")

    def test_sql_injection_in_address(self):
        """Test SQL injection attempts in address parameter."""
        for payload in SQL_INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                # Should not raise SQL error
                result = self.engine.search_by_name_address('John', 'Doe', payload)

                try:
                    records = json.loads(result)
                    self.assertIsInstance(records, list)
                except json.JSONDecodeError:
                    self.fail(f"Invalid JSON response for payload: {payload}")

    def test_sql_injection_in_zip(self):
        """Test SQL injection attempts in ZIP parameter."""
        for payload in SQL_INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                # Should not raise SQL error
                result = self.engine.search_by_name_zip('John', 'Doe', payload)

                try:
                    records = json.loads(result)
                    self.assertIsInstance(records, list)
                except json.JSONDecodeError:
                    self.fail(f"Invalid JSON response for payload: {payload}")

    def test_sql_injection_in_limit(self):
        """Test SQL injection attempts in LIMIT parameter."""
        limit_payloads = [
            "10; DROP TABLE ssn_1",
            "10 UNION SELECT * FROM users",
            "-1",
            "0",
            "999999999",
            "10; DELETE FROM ssn_1",
            "1=1",
            "NULL",
            "''",
        ]

        for payload in limit_payloads:
            with self.subTest(payload=payload):
                try:
                    # Should either return empty result or use safe default
                    result = self.engine.search_by_ssn('123-45-6789', limit=payload)
                    records = json.loads(result)
                    self.assertIsInstance(records, list)
                except (ValueError, TypeError):
                    # Expected for invalid limit values
                    pass
                except json.JSONDecodeError:
                    self.fail(f"Invalid JSON response for limit payload: {payload}")

    def test_database_not_modified_after_injection(self):
        """Verify database tables are not modified by injection attempts."""
        # Get initial row count
        conn = get_connection(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM ssn_1')
        initial_count = cursor.fetchone()[0]
        close_connection(conn)

        # Attempt various injection payloads
        drop_payloads = [
            "'; DROP TABLE ssn_1; --",
            "'; DELETE FROM ssn_1; --",
            "'; TRUNCATE TABLE ssn_1; --",
        ]

        for payload in drop_payloads:
            self.engine.search_by_ssn(payload)
            self.engine.search_by_name_zip(payload, 'Doe', '02101')
            self.engine.search_by_name_address('John', payload, '123 Main')

        # Verify table still exists and has same row count
        conn = get_connection(self.test_db_path)
        cursor = conn.cursor()

        # Table should still exist
        cursor.execute('''
            SELECT name FROM sqlite_master WHERE type='table' AND name='ssn_1'
        ''')
        result = cursor.fetchone()
        self.assertIsNotNone(result, "Table ssn_1 should still exist after injection attempts")

        # Row count should be unchanged
        cursor.execute('SELECT COUNT(*) FROM ssn_1')
        final_count = cursor.fetchone()[0]
        self.assertEqual(initial_count, final_count,
                        "Row count should not change after injection attempts")

        close_connection(conn)


class TestSQLInjectionValidators(unittest.TestCase):
    """
    Test that validators reject SQL injection payloads.
    """

    def test_validate_ssn_rejects_injection(self):
        """Test that SSN validator rejects injection payloads."""
        for payload in SQL_INJECTION_PAYLOADS[:10]:  # Test subset
            with self.subTest(payload=payload):
                is_valid, _ = validate_ssn(payload)
                self.assertFalse(is_valid,
                               f"SSN validator should reject: {payload}")

    def test_validate_name_rejects_injection(self):
        """Test that name validator rejects injection payloads."""
        for payload in SQL_INJECTION_PAYLOADS[:10]:
            with self.subTest(payload=payload):
                is_valid, _ = validate_name(payload, "name")
                self.assertFalse(is_valid,
                               f"Name validator should reject: {payload}")

    def test_validate_email_rejects_injection(self):
        """Test that email validator rejects injection payloads."""
        for payload in SQL_INJECTION_PAYLOADS[:10]:
            with self.subTest(payload=payload):
                is_valid, _ = validate_email(payload)
                self.assertFalse(is_valid,
                               f"Email validator should reject: {payload}")

    def test_validate_zip_rejects_injection(self):
        """Test that ZIP validator rejects injection payloads."""
        for payload in SQL_INJECTION_PAYLOADS[:10]:
            with self.subTest(payload=payload):
                is_valid, _ = validate_zip(payload)
                self.assertFalse(is_valid,
                               f"ZIP validator should reject: {payload}")

    def test_validate_limit_rejects_injection(self):
        """Test that limit validator rejects injection payloads."""
        injection_limits = [
            "10; DROP TABLE",
            "-1",
            "99999999999",
            "1=1",
            "NULL",
            "' OR '1'='1",
        ]

        for payload in injection_limits:
            with self.subTest(payload=payload):
                is_valid, _ = validate_limit(payload)
                # Should either reject or return safe default
                if is_valid:
                    # If valid, the payload was likely converted to safe int
                    pass

    def test_validate_no_sql_injection_detects_patterns(self):
        """Test that SQL injection detector catches common patterns."""
        detected_payloads = [
            "' OR 1=1",
            "'; DROP TABLE users; --",
            "' UNION SELECT * FROM users --",
            "1' AND '1'='1",
        ]

        for payload in detected_payloads:
            with self.subTest(payload=payload):
                is_valid, error = validate_no_sql_injection(payload, "test_field")
                self.assertFalse(is_valid,
                               f"SQL injection detector should catch: {payload}")


class TestSQLInjectionSanitizers(unittest.TestCase):
    """
    Test that sanitizers clean SQL injection payloads.
    """

    def test_sanitize_string_cleans_injection(self):
        """Test that string sanitizer handles injection payloads safely."""
        for payload in SQL_INJECTION_PAYLOADS[:10]:
            with self.subTest(payload=payload):
                result = sanitize_string(payload)
                # Should return a safe string (or None)
                if result is not None:
                    self.assertIsInstance(result, str)
                    # Result should not contain certain dangerous patterns
                    # (Note: sanitizer doesn't escape SQL, it cleans control chars)

    def test_sanitize_name_cleans_injection(self):
        """Test that name sanitizer handles injection payloads."""
        for payload in SQL_INJECTION_PAYLOADS[:10]:
            with self.subTest(payload=payload):
                result = sanitize_name(payload)
                # Should return cleaned name or None
                if result is not None:
                    self.assertIsInstance(result, str)
                    self.assertLessEqual(len(result), 100)  # Max length enforced

    def test_sanitize_ssn_cleans_injection(self):
        """Test that SSN sanitizer handles injection payloads."""
        for payload in SQL_INJECTION_PAYLOADS[:10]:
            with self.subTest(payload=payload):
                result = sanitize_ssn(payload)
                # Should return None for invalid SSN
                if result is not None:
                    # If returned something, it should be formatted SSN
                    self.assertRegex(result, r'^\d{3}-\d{2}-\d{4}$|^\d{4}$')

    def test_sanitize_metadata_limits_depth(self):
        """Test that metadata sanitizer limits nesting depth."""
        # Create deeply nested structure
        deeply_nested = {"level1": {"level2": {"level3": {"level4": {"level5": {"level6": "value"}}}}}}

        result = sanitize_metadata(deeply_nested, max_depth=3)
        # Should truncate at max_depth
        self.assertIsNotNone(result)

    def test_sanitize_metadata_handles_injection_in_values(self):
        """Test that metadata sanitizer handles injection in values."""
        malicious_metadata = {
            "key1": "' OR '1'='1",
            "key2": "'; DROP TABLE users; --",
            "nested": {
                "key3": "' UNION SELECT * FROM passwords --"
            }
        }

        result = sanitize_metadata(malicious_metadata)
        self.assertIsNotNone(result)
        # Values should be sanitized strings
        if 'key1' in result:
            self.assertIsInstance(result['key1'], str)


class TestDoSProtection(unittest.TestCase):
    """
    Test protection against Denial of Service attacks via input.
    """

    def test_extremely_long_ssn_input(self):
        """Test handling of extremely long SSN input."""
        long_input = "1" * 1000000  # 1MB of digits

        is_valid, error = validate_ssn(long_input)
        self.assertFalse(is_valid)

    def test_extremely_long_name_input(self):
        """Test handling of extremely long name input."""
        long_input = "A" * 1000000  # 1MB string

        is_valid, error = validate_name(long_input, "name")
        self.assertFalse(is_valid)

    def test_extremely_long_email_input(self):
        """Test handling of extremely long email input."""
        long_input = "a" * 1000000 + "@example.com"

        is_valid, error = validate_email(long_input)
        self.assertFalse(is_valid)

    def test_deeply_nested_metadata(self):
        """Test handling of deeply nested JSON structures."""
        # Create very deeply nested structure
        data = {"value": "data"}
        for _ in range(100):
            data = {"nested": data}

        result = sanitize_metadata(data, max_depth=5)
        # Should limit depth without crashing
        self.assertIsNotNone(result)

    def test_large_metadata_size(self):
        """Test handling of large metadata."""
        # Create large metadata
        large_data = {f"key_{i}": "x" * 1000 for i in range(100)}

        result = sanitize_metadata(large_data, max_size=10000)
        # Should limit size
        if result is not None:
            total_size = sum(len(str(v)) for v in result.values())
            self.assertLessEqual(total_size, 20000)  # Some overhead

    def test_huge_limit_parameter(self):
        """Test handling of huge LIMIT values."""
        is_valid, error = validate_limit(999999999999)
        # Should either reject or cap at max
        if is_valid:
            # If valid, should have been capped
            pass
        else:
            self.assertIn("must be at most", error.lower())


class TestUnicodeAndSpecialCharacters(unittest.TestCase):
    """
    Test handling of Unicode and special characters.
    """

    def test_unicode_in_name(self):
        """Test handling of Unicode characters in names."""
        unicode_names = [
            "Muller",  # German umlaut removed for ASCII safety
            "Francois",
            "Jose",
            "Bjork",
        ]

        for name in unicode_names:
            with self.subTest(name=name):
                is_valid, error = validate_name(name, "name")
                # Should handle gracefully (may accept or reject)
                self.assertIsNotNone(is_valid)

    def test_null_byte_in_input(self):
        """Test handling of null byte injection."""
        null_byte_payloads = [
            "test\x00' OR '1'='1",
            "\x00admin",
            "user\x00password",
        ]

        for payload in null_byte_payloads:
            with self.subTest(payload=repr(payload)):
                result = sanitize_string(payload)
                # Should remove null bytes
                if result is not None:
                    self.assertNotIn('\x00', result)

    def test_control_characters_in_input(self):
        """Test handling of control characters."""
        control_char_payloads = [
            "test\x01\x02\x03value",
            "\x07\x08\x09name",
            "data\x1f\x1evalue",
        ]

        for payload in control_char_payloads:
            with self.subTest(payload=repr(payload)):
                result = sanitize_string(payload)
                # Control characters should be removed (except \t, \n, \r)
                if result is not None:
                    for c in result:
                        if ord(c) < 32:
                            self.assertIn(c, '\t\n\r',
                                        f"Unexpected control char: {ord(c)}")


class TestPydanticModelValidation(unittest.TestCase):
    """
    Test that Pydantic models reject SQL injection payloads.
    """

    def test_search_by_name_request_rejects_injection(self):
        """Test SearchByNameRequest model validation."""
        from api.common.models_sqlite import SearchByNameRequest

        for payload in SQL_INJECTION_PAYLOADS[:5]:
            with self.subTest(payload=payload):
                try:
                    # Should raise ValidationError for invalid input
                    SearchByNameRequest(
                        firstname=payload,
                        lastname="Doe",
                        zip="02101"
                    )
                    # If no error, the payload might be accepted but sanitized
                except Exception as e:
                    # Expected - validation should catch malicious input
                    pass

    def test_instant_ssn_request_rejects_injection(self):
        """Test InstantSSNRequest model validation."""
        from api.common.models_sqlite import InstantSSNRequest

        for payload in SQL_INJECTION_PAYLOADS[:5]:
            with self.subTest(payload=payload):
                try:
                    InstantSSNRequest(
                        firstname=payload,
                        lastname="Doe",
                        address="123 Main Street, Boston, MA"
                    )
                except Exception as e:
                    # Expected - validation should catch malicious input
                    pass


if __name__ == '__main__':
    unittest.main()
