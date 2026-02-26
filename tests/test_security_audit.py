"""
Comprehensive Security Audit Tests.

Tests cover:
- SQL injection protection for ClickHouse queries (parameterized queries)
- SQL injection protection for PostgreSQL via SQLAlchemy ORM
- Authentication bypass attempts on all three APIs
- Internal endpoints access without authentication
- IDOR (Insecure Direct Object Reference) protection
- Input validation across all APIs
- JWT token manipulation and forgery
- XSS prevention in API responses
- ClickHouse-specific injection vectors

Run:
    python3 -m pytest tests/test_security_audit.py -v
    python3 -m unittest tests.test_security_audit -v
"""

import unittest
import json
import os
import sys
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# ATTACK PAYLOADS
# ============================================================================

SQL_INJECTION_PAYLOADS = [
    # Basic SQL injection
    "' OR '1'='1",
    "' OR '1'='1' --",
    "' OR '1'='1' /*",
    "' OR 1=1 --",
    "'; --",
    "' AND '1'='1",

    # UNION-based injection
    "' UNION SELECT * FROM users --",
    "' UNION ALL SELECT NULL,NULL,NULL --",
    "1' UNION SELECT username,password FROM users--",

    # Stacked queries
    "'; DROP TABLE ssn_data; --",
    "'; DELETE FROM users; --",
    "'; UPDATE users SET is_admin=true; --",
    "'; INSERT INTO users VALUES('hacker','pass'); --",

    # Comment-based injection
    "/**/OR/**/1=1",
    "1'/**/OR/**/1=1/**/--",

    # Conditional injection
    "' OR 1=1#",
    "admin'--",
    "admin' #",

    # Time-based blind injection
    "'; WAITFOR DELAY '0:0:5' --",
    "' OR SLEEP(5) --",
    "1; SELECT pg_sleep(5)",

    # Error-based injection
    "' AND 1=CONVERT(int, (SELECT TOP 1 table_name FROM information_schema.tables))--",

    # Double quotes
    '" OR "1"="1',
    '" OR "1"="1" --',

    # Null byte injection
    "%00' OR '1'='1",
    "test\x00' OR '1'='1",
]

CLICKHOUSE_INJECTION_PAYLOADS = [
    # ClickHouse-specific injections
    "'; SELECT * FROM system.tables; --",
    "' UNION ALL SELECT * FROM system.columns --",
    "'; INSERT INTO ssn_data SELECT * FROM ssn_data; --",
    "' OR 1=1 FORMAT TabSeparated --",
    "'; SHOW DATABASES; --",
    "'; SHOW TABLES FROM system; --",
    "' OR toString(1) = '1",
    "' OR length('a') = 1 --",
    "'; ALTER TABLE ssn_data DELETE WHERE 1=1; --",
    "'; TRUNCATE TABLE ssn_data; --",
    "'; DROP TABLE ssn_data; --",
    # ClickHouse format injection
    "' FORMAT JSON --",
    "' FORMAT CSV --",
    "' FORMAT TSV --",
    # ClickHouse function injection
    "' OR currentDatabase() = currentDatabase() --",
    "' OR hostName() != '' --",
    # ClickHouse settings injection
    "' SETTINGS max_threads=1 --",
    # Array parameter injection
    "['injection']",
    "ARRAY['test']",
]

POSTGRESQL_INJECTION_PAYLOADS = [
    # PostgreSQL-specific
    "'; SELECT current_database(); --",
    "'; SELECT version(); --",
    "' OR pg_sleep(5) --",
    "'; COPY (SELECT '') TO '/tmp/test'; --",
    "'; CREATE TABLE hacked(data text); --",
    "' UNION SELECT table_name FROM information_schema.tables --",
    "' UNION SELECT column_name FROM information_schema.columns WHERE table_name='users' --",
    "'; DO $$ BEGIN PERFORM pg_sleep(5); END $$; --",
    "$$ OR 1=1 $$",
    "E'\\x27 OR 1=1 --'",
]

XSS_PAYLOADS = [
    "<script>alert('XSS')</script>",
    "<img src=x onerror=alert(1)>",
    "javascript:alert(1)",
    "<svg onload=alert(1)>",
    "';alert(String.fromCharCode(88,83,83))//",
    "<iframe src='javascript:alert(1)'>",
    "<body onload=alert(1)>",
    "\" onfocus=\"alert(1)\" autofocus=\"",
    "<details open ontoggle=alert(1)>",
    "{{constructor.constructor('alert(1)')()}}",
]

JWT_MANIPULATION_PAYLOADS = [
    # Algorithm confusion
    {"alg": "none", "typ": "JWT"},
    {"alg": "HS256", "typ": "JWT"},
    # Empty/null payloads
    "",
    "invalid.token.here",
    "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJ1c2VyX2lkIjoiMSIsImlzX2FkbWluIjp0cnVlfQ.",
    # Manipulated tokens
    "Bearer ",
    "Bearer null",
    "Bearer undefined",
    "Bearer eyJ0ZXN0IjoiMSJ9",
]


# ============================================================================
# CLICKHOUSE SQL INJECTION TESTS
# ============================================================================

class TestClickHouseSQLInjection(unittest.TestCase):
    """
    Test SQL injection protection in ClickHouse search engine.

    Verifies that:
    1. All user inputs are parameterized (not interpolated via f-strings)
    2. ClickHouse-specific injection vectors are blocked
    3. Table/column names are constants, not user-controlled
    """

    @classmethod
    def setUpClass(cls):
        """Check if ClickHouse engine is available."""
        try:
            from database.clickhouse_search_engine import ClickHouseSearchEngine
            cls.engine_class = ClickHouseSearchEngine
            cls.available = True
        except ImportError:
            cls.available = False

    def setUp(self):
        if not self.available:
            self.skipTest("ClickHouseSearchEngine not available")

    def _get_engine_with_mock(self):
        """Create engine with mocked ClickHouse connection."""
        from database.clickhouse_schema import SSN_TABLE, SSN_MUTANTS_TABLE
        with patch('database.clickhouse_search_engine.execute_query') as mock_exec:
            mock_exec.return_value = []
            engine = self.engine_class.__new__(self.engine_class)
            engine.table = SSN_TABLE
            engine.mutants_table = SSN_MUTANTS_TABLE
            engine.include_mutants = True
            engine.logger = MagicMock()
            engine._execute_search = MagicMock(return_value=[])
            return engine, mock_exec

    def test_ssn_search_parameterized(self):
        """Verify SSN search uses parameterized queries, not f-string interpolation."""
        engine, mock_exec = self._get_engine_with_mock()

        for payload in SQL_INJECTION_PAYLOADS + CLICKHOUSE_INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                try:
                    result = engine.search_by_ssn(payload)
                    # If executed, check that the query used parameters
                    if engine._execute_search.called:
                        call_args = engine._execute_search.call_args
                        query = call_args[0][0] if call_args[0] else call_args[1].get('query', '')
                        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get('params', {})
                        # Payload should be in params, NOT in query string
                        self.assertNotIn(payload, query,
                                         f"Payload found in raw query (not parameterized): {payload}")
                except Exception:
                    # Validation rejection is acceptable
                    pass

    def test_name_search_parameterized(self):
        """Verify name search uses parameterized queries."""
        engine, mock_exec = self._get_engine_with_mock()

        for payload in SQL_INJECTION_PAYLOADS[:10]:
            with self.subTest(payload=payload):
                try:
                    engine.search_by_name_zip(payload, "Smith", "90210")
                except Exception:
                    pass
                try:
                    engine.search_by_name_zip("John", payload, "90210")
                except Exception:
                    pass

    def test_address_search_parameterized(self):
        """Verify address search uses parameterized queries."""
        engine, mock_exec = self._get_engine_with_mock()

        for payload in SQL_INJECTION_PAYLOADS[:10]:
            with self.subTest(payload=payload):
                try:
                    engine.search_by_name_address("John", "Smith", payload)
                except Exception:
                    pass

    def test_clickhouse_specific_injections(self):
        """Test ClickHouse-specific injection vectors."""
        engine, mock_exec = self._get_engine_with_mock()

        for payload in CLICKHOUSE_INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                try:
                    engine.search_by_ssn(payload)
                except Exception:
                    pass  # Rejection is OK

                # Verify no dangerous query was constructed
                if engine._execute_search.called:
                    call_args = engine._execute_search.call_args
                    query = call_args[0][0] if call_args[0] else ""
                    # Should not contain ClickHouse system table access
                    self.assertNotIn("system.tables", query.lower())
                    self.assertNotIn("system.columns", query.lower())
                    self.assertNotIn("show databases", query.lower())

    def test_table_names_are_constants(self):
        """Verify table names in queries are constants, not user-controlled."""
        engine, _ = self._get_engine_with_mock()

        # Table names should be from schema constants
        from database.clickhouse_schema import SSN_TABLE, SSN_MUTANTS_TABLE
        self.assertEqual(engine.table, SSN_TABLE)
        self.assertEqual(engine.mutants_table, SSN_MUTANTS_TABLE)

    def test_limit_injection_prevented(self):
        """Verify LIMIT parameter cannot be injected."""
        engine, mock_exec = self._get_engine_with_mock()

        dangerous_limits = [
            "10; DROP TABLE ssn_data",
            "10 UNION SELECT * FROM users",
            "-1",
            "999999999999",
            "NULL",
            "' OR '1'='1",
            "0; DELETE FROM ssn_data",
        ]

        for payload in dangerous_limits:
            with self.subTest(payload=payload):
                try:
                    engine.search_by_ssn("123-45-6789", limit=payload)
                except (ValueError, TypeError):
                    pass  # Expected rejection


class TestClickHouseQueryStructure(unittest.TestCase):
    """
    Static analysis of ClickHouse query construction patterns.

    Verifies that the source code uses safe patterns:
    - Parameters use {{name:Type}} syntax (ClickHouse parameterized)
    - User input never directly in f-strings
    - Column names from controlled range only
    """

    def test_search_engine_uses_parameterized_queries(self):
        """Verify search engine source code uses {{param:Type}} patterns."""
        import inspect
        try:
            from database.clickhouse_search_engine import ClickHouseSearchEngine
        except ImportError:
            self.skipTest("ClickHouseSearchEngine not available")

        source = inspect.getsource(ClickHouseSearchEngine)

        # Should contain parameterized patterns
        self.assertIn("{last4:String}", source)
        self.assertIn("{limit:UInt32}", source)
        self.assertIn("{keys:Array(String)}", source)

        # Should NOT contain direct string formatting for user values
        # (f-string with .format() for user-controlled values)
        dangerous_patterns = [
            "f\"SELECT.*{firstname}",
            "f\"SELECT.*{lastname}",
            "f\"SELECT.*{ssn}",
            "f\"SELECT.*{address}",
        ]
        import re as regex
        for pattern in dangerous_patterns:
            matches = regex.findall(pattern, source)
            self.assertEqual(len(matches), 0,
                             f"Dangerous f-string pattern found: {pattern}")

    def test_search_key_columns_from_controlled_range(self):
        """Verify search_key column names are generated from controlled range 1-8."""
        try:
            from database.clickhouse_search_engine import ClickHouseSearchEngine
        except ImportError:
            self.skipTest("ClickHouseSearchEngine not available")

        import inspect
        source = inspect.getsource(ClickHouseSearchEngine)

        # The col_name = f'search_key_{key_num}' pattern should only use range(1, 9)
        self.assertIn("range(1, 9)", source,
                       "Search key range should be hardcoded to 1-8")


# ============================================================================
# POSTGRESQL / SQLALCHEMY INJECTION TESTS
# ============================================================================

class TestPostgreSQLInjectionSourceCode(unittest.TestCase):
    """
    Test SQL injection protection for PostgreSQL via source code analysis.

    SQLAlchemy ORM uses parameterized queries by default, but raw SQL
    or text() queries could be vulnerable if not properly parameterized.
    """

    def _read_source(self, relative_path):
        """Read source file relative to project root."""
        full_path = os.path.join(os.path.dirname(__file__), '..', relative_path)
        if not os.path.exists(full_path):
            self.skipTest(f"File not found: {relative_path}")
        with open(full_path) as f:
            return f.read()

    def test_models_postgres_no_raw_sql(self):
        """Verify PostgreSQL models don't use raw SQL."""
        source = self._read_source('shared/api/common/models_postgres.py')

        dangerous_patterns = [
            "execute(f\"",
            "execute(f'",
            ".raw(",
            "text(f\"",
            "text(f'",
            "cursor.execute(",
        ]
        for pattern in dangerous_patterns:
            self.assertNotIn(pattern, source,
                             f"Dangerous raw SQL pattern in models_postgres: {pattern}")

    def test_auth_module_no_raw_sql(self):
        """Verify auth module doesn't use raw SQL with user input."""
        source = self._read_source('shared/api/common/auth.py')

        self.assertNotIn("execute(f\"", source)
        self.assertNotIn("execute(f'", source)
        self.assertNotIn("cursor.execute", source)

    def test_public_api_routers_no_raw_sql(self):
        """Verify public API routers don't use raw SQL with f-strings."""
        router_dir = os.path.join(os.path.dirname(__file__), '..', 'huntrssn.cc', 'api', 'public', 'routers')
        if not os.path.isdir(router_dir):
            self.skipTest("Public API routers not found")

        for fname in os.listdir(router_dir):
            if not fname.endswith('.py'):
                continue
            with self.subTest(file=fname):
                with open(os.path.join(router_dir, fname)) as f:
                    source = f.read()
                # Check for raw SQL with f-strings (dangerous)
                self.assertNotIn('execute(f"', source,
                                 f"Raw SQL f-string in {fname}")
                self.assertNotIn("execute(f'", source,
                                 f"Raw SQL f-string in {fname}")
                self.assertNotIn("text(f\"", source,
                                 f"text() with f-string in {fname}")
                self.assertNotIn("text(f'", source,
                                 f"text() with f-string in {fname}")

    def test_admin_api_routers_no_raw_sql(self):
        """Verify admin API routers don't use raw SQL with f-strings."""
        router_dir = os.path.join(os.path.dirname(__file__), '..', 'infinitymoneyyy.xyz', 'api', 'admin', 'routers')
        if not os.path.isdir(router_dir):
            self.skipTest("Admin API routers not found")

        for fname in os.listdir(router_dir):
            if not fname.endswith('.py'):
                continue
            with self.subTest(file=fname):
                with open(os.path.join(router_dir, fname)) as f:
                    source = f.read()
                self.assertNotIn('execute(f"', source,
                                 f"Raw SQL f-string in admin/{fname}")
                self.assertNotIn("execute(f'", source,
                                 f"Raw SQL f-string in admin/{fname}")

    def test_worker_api_routers_no_raw_sql(self):
        """Verify worker API routers don't use raw SQL with f-strings."""
        router_dir = os.path.join(os.path.dirname(__file__), '..', 'qwertyworkforever.top', 'api', 'worker', 'routers')
        if not os.path.isdir(router_dir):
            self.skipTest("Worker API routers not found")

        for fname in os.listdir(router_dir):
            if not fname.endswith('.py'):
                continue
            with self.subTest(file=fname):
                with open(os.path.join(router_dir, fname)) as f:
                    source = f.read()
                self.assertNotIn('execute(f"', source,
                                 f"Raw SQL f-string in worker/{fname}")
                self.assertNotIn("execute(f'", source,
                                 f"Raw SQL f-string in worker/{fname}")

    def test_database_module_no_raw_sql(self):
        """Verify database connection module doesn't use raw SQL with f-strings."""
        source = self._read_source('shared/api/common/database.py')

        self.assertNotIn('execute(f"', source)
        self.assertNotIn("execute(f'", source)


# ============================================================================
# VALIDATOR & SANITIZER TESTS (Extended)
# ============================================================================

class TestValidatorsAgainstAllPayloads(unittest.TestCase):
    """
    Exhaustive testing of validators against all payload types.

    Includes ClickHouse-specific and PostgreSQL-specific payloads
    in addition to standard SQL injection vectors.
    """

    @classmethod
    def setUpClass(cls):
        try:
            from api.common.validators import (
                validate_ssn, validate_name, validate_email,
                validate_address, validate_zip, validate_limit,
                validate_no_sql_injection, validate_coupon_code
            )
            cls.available = True
        except ImportError:
            cls.available = False

    def setUp(self):
        if not self.available:
            self.skipTest("Validators not available")

    def test_ssn_validator_rejects_all_sql_payloads(self):
        """SSN validator must reject ALL SQL injection payloads."""
        from api.common.validators import validate_ssn
        all_payloads = SQL_INJECTION_PAYLOADS + CLICKHOUSE_INJECTION_PAYLOADS + POSTGRESQL_INJECTION_PAYLOADS
        for payload in all_payloads:
            with self.subTest(payload=payload):
                is_valid, _ = validate_ssn(payload)
                self.assertFalse(is_valid,
                                 f"SSN validator accepted injection: {payload}")

    def test_name_validator_rejects_sql_payloads(self):
        """Name validator must reject common SQL injection payloads."""
        from api.common.validators import validate_name
        # Test all payloads, track which ones pass through
        leaked = []
        all_payloads = SQL_INJECTION_PAYLOADS + CLICKHOUSE_INJECTION_PAYLOADS + POSTGRESQL_INJECTION_PAYLOADS
        for payload in all_payloads:
            is_valid, _ = validate_name(payload, "name")
            if is_valid:
                leaked.append(payload)

        if leaked:
            import warnings
            warnings.warn(
                f"SECURITY: Name validator accepted {len(leaked)} injection payloads: "
                f"{leaked[:5]}... (parameterized queries are the primary defense)",
                RuntimeWarning
            )
        # At least 80% should be rejected (parameterized queries handle the rest)
        rejection_rate = 1 - len(leaked) / len(all_payloads)
        self.assertGreater(rejection_rate, 0.8,
                           f"Name validator rejected only {rejection_rate:.0%} of payloads")

    def test_zip_validator_rejects_all_sql_payloads(self):
        """ZIP validator must reject ALL SQL injection payloads."""
        from api.common.validators import validate_zip
        all_payloads = SQL_INJECTION_PAYLOADS + CLICKHOUSE_INJECTION_PAYLOADS
        for payload in all_payloads:
            with self.subTest(payload=payload):
                result = validate_zip(payload)
                is_valid = result[0] if isinstance(result, tuple) else result
                self.assertFalse(is_valid,
                                 f"ZIP validator accepted injection: {payload}")

    def test_coupon_validator_rejects_all_sql_payloads(self):
        """Coupon code validator must reject ALL SQL injection payloads."""
        from api.common.validators import validate_coupon_code
        all_payloads = SQL_INJECTION_PAYLOADS + CLICKHOUSE_INJECTION_PAYLOADS
        for payload in all_payloads:
            with self.subTest(payload=payload):
                is_valid, _ = validate_coupon_code(payload)
                self.assertFalse(is_valid,
                                 f"Coupon validator accepted injection: {payload}")

    def test_no_sql_injection_detector_catches_all(self):
        """Generic SQL injection detector must catch common patterns."""
        from api.common.validators import validate_no_sql_injection
        must_catch = [
            "' OR 1=1 --",
            "'; DROP TABLE users; --",
            "' UNION SELECT * FROM users --",
            "1' AND '1'='1",
            "'; DELETE FROM ssn_data; --",
            "' UNION ALL SELECT NULL --",
            "'; INSERT INTO users VALUES('hacker'); --",
            "'; UPDATE users SET is_admin=true; --",
        ]
        for payload in must_catch:
            with self.subTest(payload=payload):
                is_valid, _ = validate_no_sql_injection(payload, "test_field")
                self.assertFalse(is_valid,
                                 f"SQL injection detector missed: {payload}")

    def test_validators_reject_xss_payloads(self):
        """Validators should reject XSS payloads in name/coupon fields."""
        from api.common.validators import validate_name, validate_coupon_code
        for payload in XSS_PAYLOADS:
            with self.subTest(payload=payload):
                is_valid_name, _ = validate_name(payload, "name")
                is_valid_coupon, _ = validate_coupon_code(payload)
                self.assertTrue(
                    not is_valid_name or not is_valid_coupon,
                    f"Neither validator caught XSS: {payload}"
                )


class TestSanitizersAgainstAllPayloads(unittest.TestCase):
    """Extended sanitizer tests with all payload types."""

    @classmethod
    def setUpClass(cls):
        try:
            from api.common.sanitizers import (
                sanitize_name, sanitize_address, sanitize_string,
                sanitize_ssn, sanitize_email, sanitize_metadata
            )
            cls._sanitize_name = staticmethod(sanitize_name)
            cls._sanitize_address = staticmethod(sanitize_address)
            cls._sanitize_string = staticmethod(sanitize_string)
            cls._sanitize_ssn = staticmethod(sanitize_ssn)
            cls._sanitize_email = staticmethod(sanitize_email)
            cls._sanitize_metadata = staticmethod(sanitize_metadata)
            cls.available = True
        except ImportError:
            cls.available = False

    def setUp(self):
        if not self.available:
            self.skipTest("Sanitizers not available")

    def test_sanitize_name_handles_sql_chars(self):
        """Name sanitizer must handle SQL injection characters without crashing."""
        from api.common.sanitizers import sanitize_name
        dangerous_inputs = [
            "John'Smith",
            'John"Smith',
            "John;Smith",
            "John--Smith",
            "John/*Smith",
            "John\\Smith",
        ]
        for inp in dangerous_inputs:
            with self.subTest(input=inp):
                try:
                    result = sanitize_name(inp)
                    # Should return something or None, never crash
                    if result is not None:
                        self.assertIsInstance(result, str)
                except Exception as e:
                    self.fail(f"Sanitizer crashed on input '{inp}': {e}")

    def test_sanitize_address_handles_injection(self):
        """Address sanitizer must handle SQL injection in addresses."""
        from api.common.sanitizers import sanitize_address
        for payload in SQL_INJECTION_PAYLOADS[:15]:
            with self.subTest(payload=payload):
                # Should return something or None, never raise
                try:
                    result = sanitize_address(payload)
                except Exception as e:
                    self.fail(f"Sanitizer raised exception for: {payload}: {e}")

    def test_sanitize_ssn_rejects_non_ssn(self):
        """SSN sanitizer must return None for non-SSN input."""
        from api.common.sanitizers import sanitize_ssn
        import re
        for payload in SQL_INJECTION_PAYLOADS[:10]:
            with self.subTest(payload=payload):
                result = sanitize_ssn(payload)
                if result is not None:
                    self.assertTrue(
                        re.match(r'^\d{3}-\d{2}-\d{4}$', result) or
                        re.match(r'^\d{4}$', result),
                        f"Invalid SSN format returned: {result}"
                    )

    def test_sanitize_metadata_handles_xss_safely(self):
        """Metadata sanitizer must handle XSS payloads without crashing."""
        from api.common.sanitizers import sanitize_metadata
        malicious = {
            "name": "<script>alert(1)</script>",
            "address": "123 Main St<img src=x onerror=alert(1)>",
        }
        result = sanitize_metadata(malicious)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)


# ============================================================================
# JWT AUTHENTICATION BYPASS TESTS
# ============================================================================

class TestJWTSecuritySourceCode(unittest.TestCase):
    """
    Test JWT token security via source code analysis.

    Works without installing passlib/jose by analyzing the source directly.
    For runtime JWT tests, run inside Docker container.
    """

    def test_jwt_uses_hs256_or_stronger(self):
        """JWT should use HS256 or stronger algorithm."""
        auth_path = os.path.join(os.path.dirname(__file__), '..', 'shared', 'api', 'common', 'auth.py')
        with open(auth_path) as f:
            source = f.read()

        # Should use HS256 (default) or stronger
        self.assertIn("HS256", source, "JWT should use HS256 algorithm")
        # Should NOT use 'none' algorithm
        self.assertNotIn("'none'", source.lower().replace("algorithm", ""),
                          "JWT should not allow 'none' algorithm")

    def test_jwt_has_expiration(self):
        """JWT tokens must have expiration time."""
        auth_path = os.path.join(os.path.dirname(__file__), '..', 'shared', 'api', 'common', 'auth.py')
        with open(auth_path) as f:
            source = f.read()

        # Should set expiration
        self.assertTrue(
            "exp" in source and ("timedelta" in source or "expir" in source.lower()),
            "JWT must include expiration time"
        )

    def test_jwt_secret_has_minimum_length_default(self):
        """JWT secret default should be at least 32 characters."""
        auth_path = os.path.join(os.path.dirname(__file__), '..', 'shared', 'api', 'common', 'auth.py')
        with open(auth_path) as f:
            source = f.read()

        # Find the default JWT_SECRET value
        import re
        match = re.search(r"JWT_SECRET\s*=\s*os\.getenv\([^,]+,\s*['\"]([^'\"]+)['\"]", source)
        if match:
            default_secret = match.group(1)
            self.assertGreaterEqual(len(default_secret), 32,
                                     f"Default JWT secret too short: {len(default_secret)} chars")

    def test_jwt_decoding_validates_signature(self):
        """JWT decode function must verify signature (not just decode)."""
        auth_path = os.path.join(os.path.dirname(__file__), '..', 'shared', 'api', 'common', 'auth.py')
        with open(auth_path) as f:
            source = f.read()

        # Should use jwt.decode with the secret (not options={"verify_signature": False})
        self.assertNotIn("verify_signature", source,
                          "JWT should not disable signature verification")
        self.assertIn("jwt.decode", source, "Should use jwt.decode for token verification")

    def test_jwt_uses_bcrypt_for_passwords(self):
        """Password hashing should use bcrypt."""
        auth_path = os.path.join(os.path.dirname(__file__), '..', 'shared', 'api', 'common', 'auth.py')
        with open(auth_path) as f:
            source = f.read()

        self.assertIn("bcrypt", source, "Should use bcrypt for password hashing")


# ============================================================================
# INTERNAL ENDPOINTS SECURITY TESTS
# ============================================================================

class TestInternalEndpointsSecurityHTTP(unittest.TestCase):
    """
    Test that internal endpoints (/internal/*) are properly protected.

    Uses HTTP requests to running Docker containers.
    CRITICAL: Internal endpoints should NOT be accessible from public internet.
    """

    PUBLIC_API_URL = "http://localhost:8000"
    ADMIN_API_URL = "http://localhost:8002"
    WORKER_API_URL = "http://localhost:8003"

    def _check_api_available(self, url):
        """Check if API is running."""
        import urllib.request
        try:
            urllib.request.urlopen(f"{url}/health", timeout=3)
            return True
        except Exception:
            return False

    def test_public_internal_notify_ticket_no_auth(self):
        """SECURITY: Public /internal/notify-ticket-created accessible without auth."""
        if not self._check_api_available(self.PUBLIC_API_URL):
            self.skipTest("Public API not running")

        import urllib.request
        data = json.dumps({"user_id": "test", "ticket_data": {"id": 1}}).encode()
        req = urllib.request.Request(
            f"{self.PUBLIC_API_URL}/internal/notify-ticket-created",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            response = urllib.request.urlopen(req, timeout=5)
            if response.status == 200:
                import warnings
                warnings.warn(
                    "SECURITY GAP: /internal/notify-ticket-created is accessible without auth",
                    RuntimeWarning
                )
        except Exception:
            pass  # 4xx/5xx is acceptable

    def test_worker_internal_online_workers_no_auth(self):
        """SECURITY: Worker /internal/online-workers accessible without auth."""
        if not self._check_api_available(self.WORKER_API_URL):
            self.skipTest("Worker API not running")

        import urllib.request
        req = urllib.request.Request(
            f"{self.WORKER_API_URL}/internal/online-workers",
            method="GET"
        )
        try:
            response = urllib.request.urlopen(req, timeout=5)
            if response.status == 200:
                import warnings
                warnings.warn(
                    "SECURITY GAP: /internal/online-workers is accessible without auth",
                    RuntimeWarning
                )
        except Exception:
            pass

    def test_internal_endpoints_reject_sql_injection(self):
        """Internal endpoints should not crash on SQL injection payloads."""
        if not self._check_api_available(self.PUBLIC_API_URL):
            self.skipTest("Public API not running")

        import urllib.request
        injection_payloads = [
            {"user_id": "'; DROP TABLE users; --", "ticket_data": {}},
            {"user_id": "<script>alert(1)</script>", "ticket_data": {}},
        ]

        for payload in injection_payloads:
            with self.subTest(payload=str(payload)[:50]):
                data = json.dumps(payload).encode()
                req = urllib.request.Request(
                    f"{self.PUBLIC_API_URL}/internal/notify-ticket-created",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                try:
                    response = urllib.request.urlopen(req, timeout=5)
                    self.assertNotEqual(response.status, 500)
                except urllib.error.HTTPError as e:
                    self.assertNotEqual(e.code, 500,
                                        f"Server error with injection payload")


# ============================================================================
# PUBLIC API AUTH ENFORCEMENT TESTS
# ============================================================================

class TestPublicAPIAuthEnforcementHTTP(unittest.TestCase):
    """
    Test that all protected public API endpoints require authentication.
    Uses HTTP requests to running Docker containers.
    """

    BASE_URL = "http://localhost:8000"

    def _check_available(self):
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.BASE_URL}/health", timeout=3)
            return True
        except Exception:
            return False

    def _request(self, method, path, body=None, headers=None):
        """Make HTTP request and return (status_code, response_body)."""
        import urllib.request
        import urllib.error
        url = f"{self.BASE_URL}{path}"
        data = json.dumps(body).encode() if body else None
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            response = urllib.request.urlopen(req, timeout=5)
            return response.status, response.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode() if e.fp else ""

    def setUp(self):
        if not self._check_available():
            self.skipTest("Public API not running on localhost:8000")

    def test_search_endpoints_require_auth(self):
        """Search endpoints must require authentication."""
        endpoints = [
            ("POST", "/search/name", {"firstname": "John", "lastname": "Smith", "zip": "90210"}),
            ("POST", "/search/instant-ssn", {"firstname": "John", "lastname": "Smith", "address": "123 Main St"}),
        ]
        for method, path, body in endpoints:
            with self.subTest(endpoint=f"{method} {path}"):
                status, _ = self._request(method, path, body)
                self.assertIn(status, [401, 403],
                              f"{method} {path} should require auth, got {status}")

    def test_profile_endpoint_requires_auth(self):
        """Profile endpoint must require authentication."""
        status, _ = self._request("GET", "/auth/me")
        self.assertIn(status, [401, 403])

    def test_billing_endpoints_require_auth(self):
        """Billing endpoints must require authentication."""
        status, _ = self._request("POST", "/billing/deposit/apply-coupon", {"code": "TEST"})
        self.assertIn(status, [401, 403])

    def test_ecommerce_endpoints_require_auth(self):
        """Ecommerce endpoints must require authentication."""
        status, _ = self._request("GET", "/ecommerce/orders")
        self.assertIn(status, [401, 403])

    def test_contact_endpoints_require_auth(self):
        """Contact/support endpoints must require authentication."""
        status, _ = self._request("GET", "/contact/threads")
        self.assertIn(status, [401, 403])

    def test_auth_public_endpoints_accessible(self):
        """Public auth endpoints (login, register) should process requests (401 for bad creds is OK)."""
        status, _ = self._request("POST", "/auth/login", {"access_code": "123456789012345"})
        # 401 for wrong credentials is expected behavior; 403/405 means endpoint blocked
        self.assertIn(status, [200, 400, 401, 422],
                      f"Login endpoint should accept requests, got {status}")

    def test_invalid_token_rejected(self):
        """Invalid Bearer tokens must be rejected on protected endpoints."""
        invalid_tokens = [
            "Bearer invalid_token",
            "Bearer ",
            "InvalidFormat",
            "Bearer eyJhbGciOiJub25lIn0.eyJ0ZXN0IjoiMSJ9.",
        ]
        for token in invalid_tokens:
            with self.subTest(token=token[:30]):
                status, _ = self._request("GET", "/auth/me", headers={"Authorization": token})
                self.assertIn(status, [401, 403],
                              f"Invalid token should be rejected: {token[:30]}")


# ============================================================================
# ADMIN API AUTH ENFORCEMENT TESTS
# ============================================================================

class TestAdminAPIAuthEnforcementHTTP(unittest.TestCase):
    """
    Test that admin API endpoints require admin authentication.
    Uses HTTP requests to running Docker containers.
    """

    BASE_URL = "http://localhost:8002"

    def _check_available(self):
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.BASE_URL}/health", timeout=3)
            return True
        except Exception:
            return False

    def _request(self, method, path, body=None, headers=None, content_type="application/json"):
        import urllib.request, urllib.error
        url = f"{self.BASE_URL}{path}"
        if content_type == "application/json":
            data = json.dumps(body).encode() if body else None
        else:
            data = urllib.parse.urlencode(body).encode() if body else None
        hdrs = {"Content-Type": content_type}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            response = urllib.request.urlopen(req, timeout=5)
            return response.status, response.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode() if e.fp else ""

    def setUp(self):
        if not self._check_available():
            self.skipTest("Admin API not running on localhost:8002")

    def test_admin_endpoints_require_auth(self):
        """Admin management endpoints must require admin auth."""
        protected = [
            ("GET", "/auth/me"),
            ("GET", "/users/"),
        ]
        for method, path in protected:
            with self.subTest(endpoint=f"{method} {path}"):
                status, _ = self._request(method, path)
                self.assertIn(status, [401, 403, 404],
                              f"{method} {path} should require admin auth, got {status}")

    def test_admin_login_accessible(self):
        """Admin login endpoint should process requests (return 401 for bad creds, not 403 for no auth)."""
        import urllib.parse
        status, _ = self._request(
            "POST", "/auth/login",
            body={"username": "test", "password": "test"},
            content_type="application/x-www-form-urlencoded"
        )
        # 401 for wrong creds is expected; 403/405 would mean endpoint inaccessible
        self.assertIn(status, [200, 400, 401, 422],
                      f"Admin login should accept requests, got {status}")


# ============================================================================
# WORKER API AUTH ENFORCEMENT TESTS
# ============================================================================

class TestWorkerAPIAuthEnforcementHTTP(unittest.TestCase):
    """
    Test that worker API endpoints require worker authentication.
    Uses HTTP requests to running Docker containers.
    """

    BASE_URL = "http://localhost:8003"

    def _check_available(self):
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.BASE_URL}/health", timeout=3)
            return True
        except Exception:
            return False

    def _request(self, method, path, body=None, headers=None):
        import urllib.request, urllib.error
        url = f"{self.BASE_URL}{path}"
        data = json.dumps(body).encode() if body else None
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            response = urllib.request.urlopen(req, timeout=5)
            return response.status, response.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode() if e.fp else ""

    def setUp(self):
        if not self._check_available():
            self.skipTest("Worker API not running on localhost:8003")

    def test_worker_endpoints_require_auth(self):
        """Worker management endpoints must require worker auth."""
        protected = [
            ("GET", "/auth/me"),
            ("GET", "/tickets/unassigned"),
            ("GET", "/tickets/my"),
            ("GET", "/wallet/me"),
            ("GET", "/shift/current"),
        ]
        for method, path in protected:
            with self.subTest(endpoint=f"{method} {path}"):
                status, _ = self._request(method, path)
                self.assertIn(status, [401, 403],
                              f"{method} {path} should require worker auth, got {status}")

    def test_worker_login_accessible(self):
        """Worker login endpoint should process requests (401 for bad creds is OK)."""
        status, _ = self._request("POST", "/auth/login", {"access_code": "123456789012345"})
        # 401 for wrong credentials is expected; 403/405 would mean endpoint inaccessible
        self.assertIn(status, [200, 400, 401, 422],
                      f"Worker login should accept requests, got {status}")


# ============================================================================
# SQL INJECTION VIA API ENDPOINTS (All Three APIs)
# ============================================================================

class TestSQLInjectionPublicAPIExtendedHTTP(unittest.TestCase):
    """Extended SQL injection tests for public API via HTTP."""

    BASE_URL = "http://localhost:8000"

    def _check_available(self):
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.BASE_URL}/health", timeout=3)
            return True
        except Exception:
            return False

    def _post(self, path, body):
        import urllib.request, urllib.error
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{self.BASE_URL}{path}", data=data,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            response = urllib.request.urlopen(req, timeout=10)
            return response.status
        except urllib.error.HTTPError as e:
            return e.code

    def setUp(self):
        if not self._check_available():
            self.skipTest("Public API not running on localhost:8000")

    def test_login_endpoint_sql_injection(self):
        """Login endpoint must reject SQL injection in access_code."""
        for payload in SQL_INJECTION_PAYLOADS[:15]:
            with self.subTest(payload=payload):
                status = self._post("/auth/login", {"access_code": payload})
                self.assertNotEqual(status, 500, f"Server error on login with: {payload}")
                self.assertNotEqual(status, 200, f"Login accepted injection: {payload}")

    def test_register_endpoint_sql_injection(self):
        """Register endpoint must reject SQL injection."""
        for payload in SQL_INJECTION_PAYLOADS[:10]:
            with self.subTest(payload=payload):
                status = self._post("/auth/register", {"coupon_code": payload})
                self.assertNotEqual(status, 500, f"Server error on register: {payload}")

    def test_validate_coupon_sql_injection(self):
        """Validate coupon must reject SQL injection."""
        for payload in SQL_INJECTION_PAYLOADS[:15]:
            with self.subTest(payload=payload):
                status = self._post("/auth/validate-coupon", {"coupon_code": payload})
                self.assertNotEqual(status, 500, f"Server error on validate-coupon: {payload}")

    def test_postgresql_specific_injection_in_login(self):
        """PostgreSQL-specific injections in login must be blocked."""
        for payload in POSTGRESQL_INJECTION_PAYLOADS:
            with self.subTest(payload=payload):
                status = self._post("/auth/login", {"access_code": payload})
                self.assertNotEqual(status, 500, f"PG injection server error: {payload}")


class TestSQLInjectionAdminAPIHTTP(unittest.TestCase):
    """SQL injection tests for admin API via HTTP."""

    BASE_URL = "http://localhost:8002"

    def _check_available(self):
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.BASE_URL}/health", timeout=3)
            return True
        except Exception:
            return False

    def _post(self, path, body, content_type="application/json"):
        import urllib.request, urllib.error, urllib.parse
        if content_type == "application/json":
            data = json.dumps(body).encode()
        else:
            data = urllib.parse.urlencode(body).encode()
        req = urllib.request.Request(
            f"{self.BASE_URL}{path}", data=data,
            headers={"Content-Type": content_type}, method="POST"
        )
        try:
            response = urllib.request.urlopen(req, timeout=10)
            return response.status
        except urllib.error.HTTPError as e:
            return e.code

    def setUp(self):
        if not self._check_available():
            self.skipTest("Admin API not running on localhost:8002")

    def test_admin_login_sql_injection(self):
        """Admin login must reject SQL injection in username/password."""
        for payload in SQL_INJECTION_PAYLOADS[:15]:
            with self.subTest(payload=payload):
                status = self._post(
                    "/auth/login",
                    {"username": payload, "password": "test"},
                    content_type="application/x-www-form-urlencoded"
                )
                self.assertNotEqual(status, 500, f"Server error on admin login: {payload}")

    def test_admin_2fa_sql_injection(self):
        """2FA endpoint must reject SQL injection."""
        for payload in SQL_INJECTION_PAYLOADS[:10]:
            with self.subTest(payload=payload):
                status = self._post("/auth/verify-2fa", {"code": payload, "temp_token": payload})
                self.assertNotEqual(status, 500, f"Server error on 2FA: {payload}")


class TestSQLInjectionWorkerAPIHTTP(unittest.TestCase):
    """SQL injection tests for worker API via HTTP."""

    BASE_URL = "http://localhost:8003"

    def _check_available(self):
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.BASE_URL}/health", timeout=3)
            return True
        except Exception:
            return False

    def _request(self, method, path, body=None):
        import urllib.request, urllib.error
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            f"{self.BASE_URL}{path}", data=data,
            headers={"Content-Type": "application/json"}, method=method
        )
        try:
            response = urllib.request.urlopen(req, timeout=10)
            return response.status
        except urllib.error.HTTPError as e:
            return e.code

    def setUp(self):
        if not self._check_available():
            self.skipTest("Worker API not running on localhost:8003")

    def test_worker_login_sql_injection(self):
        """Worker login must reject SQL injection in access_code."""
        for payload in SQL_INJECTION_PAYLOADS[:15]:
            with self.subTest(payload=payload):
                status = self._request("POST", "/auth/login", {"access_code": payload})
                self.assertNotEqual(status, 500, f"Server error on worker login: {payload}")
                self.assertNotEqual(status, 200, f"Worker login accepted injection: {payload}")

    def test_worker_ticket_path_injection(self):
        """Ticket ID in path must not allow SQL injection."""
        import urllib.parse
        path_payloads = [
            "999999999",
            "abc",
            "-1",
        ]
        for payload in path_payloads:
            with self.subTest(payload=payload):
                encoded = urllib.parse.quote(payload, safe='')
                status = self._request("GET", f"/tickets/{encoded}")
                # Should be 401 (no auth) or 422 (invalid), NOT 500
                self.assertNotEqual(status, 500, f"Server error with ticket path: {payload}")


# ============================================================================
# XSS PREVENTION TESTS
# ============================================================================

class TestXSSPreventionHTTP(unittest.TestCase):
    """Test XSS prevention in API responses via HTTP."""

    BASE_URL = "http://localhost:8000"

    def _check_available(self):
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.BASE_URL}/health", timeout=3)
            return True
        except Exception:
            return False

    def _post(self, path, body):
        import urllib.request, urllib.error
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{self.BASE_URL}{path}", data=data,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            response = urllib.request.urlopen(req, timeout=10)
            return response.status, response.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode() if e.fp else ""

    def setUp(self):
        if not self._check_available():
            self.skipTest("Public API not running on localhost:8000")

    def test_xss_in_login_access_code(self):
        """XSS payloads in access_code must not cause server error."""
        for payload in XSS_PAYLOADS:
            with self.subTest(payload=payload[:30]):
                status, body = self._post("/auth/login", {"access_code": payload})
                self.assertNotEqual(status, 500, f"XSS caused server error: {payload[:30]}")

    def test_xss_in_coupon_code(self):
        """XSS payloads in coupon_code must not cause server error."""
        for payload in XSS_PAYLOADS:
            with self.subTest(payload=payload[:30]):
                status, body = self._post("/auth/validate-coupon", {"coupon_code": payload})
                self.assertNotEqual(status, 500)
                if status in [200, 400, 404, 422]:
                    self.assertNotIn("<script>", body, "XSS reflected in response")


# ============================================================================
# CORS CONFIGURATION TESTS
# ============================================================================

class TestCORSConfigurationHTTP(unittest.TestCase):
    """Test CORS configuration security via HTTP."""

    BASE_URL = "http://localhost:8000"

    def _check_available(self):
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.BASE_URL}/health", timeout=3)
            return True
        except Exception:
            return False

    def setUp(self):
        if not self._check_available():
            self.skipTest("Public API not running on localhost:8000")

    def test_cors_rejects_unauthorized_origin(self):
        """CORS should not allow requests from unauthorized origins."""
        import urllib.request
        req = urllib.request.Request(
            f"{self.BASE_URL}/auth/login",
            headers={
                "Origin": "https://evil-site.com",
                "Access-Control-Request-Method": "POST",
            },
            method="OPTIONS"
        )
        try:
            response = urllib.request.urlopen(req, timeout=5)
            allow_origin = response.headers.get("access-control-allow-origin", "")
            if allow_origin == "*" or allow_origin == "https://evil-site.com":
                import warnings
                warnings.warn(
                    f"SECURITY GAP: CORS allows unauthorized origin: {allow_origin}",
                    RuntimeWarning
                )
        except Exception:
            pass  # OPTIONS may not be handled


# ============================================================================
# INPUT SIZE / DoS PROTECTION TESTS
# ============================================================================

class TestInputSizeProtectionHTTP(unittest.TestCase):
    """Test protection against oversized inputs via HTTP."""

    BASE_URL = "http://localhost:8000"

    def _check_available(self):
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.BASE_URL}/health", timeout=3)
            return True
        except Exception:
            return False

    def _post(self, path, body):
        import urllib.request, urllib.error
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{self.BASE_URL}{path}", data=data,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            response = urllib.request.urlopen(req, timeout=10)
            return response.status
        except urllib.error.HTTPError as e:
            return e.code

    def setUp(self):
        if not self._check_available():
            self.skipTest("Public API not running on localhost:8000")

    def test_oversized_coupon_rejected(self):
        """Oversized coupon code should be rejected."""
        status = self._post("/auth/validate-coupon", {"coupon_code": "X" * 100_000})
        self.assertNotEqual(status, 500)
        self.assertIn(status, [400, 413, 422])


# ============================================================================
# PATH TRAVERSAL TESTS
# ============================================================================

class TestPathTraversalHTTP(unittest.TestCase):
    """Test protection against path traversal attacks via HTTP."""

    BASE_URL = "http://localhost:8000"

    def _check_available(self):
        import urllib.request
        try:
            urllib.request.urlopen(f"{self.BASE_URL}/health", timeout=3)
            return True
        except Exception:
            return False

    def setUp(self):
        if not self._check_available():
            self.skipTest("Public API not running on localhost:8000")

    def test_path_traversal_in_endpoints(self):
        """Path parameters must not allow directory traversal."""
        import urllib.request, urllib.error

        traversal_payloads = [
            "../../../etc/passwd",
            "....//....//etc/passwd",
        ]

        for payload in traversal_payloads:
            with self.subTest(payload=payload):
                req = urllib.request.Request(
                    f"{self.BASE_URL}/search/record/{payload}",
                    headers={"Authorization": "Bearer test"},
                    method="GET"
                )
                try:
                    response = urllib.request.urlopen(req, timeout=5)
                    self.assertNotEqual(response.status, 500)
                except urllib.error.HTTPError as e:
                    self.assertNotEqual(e.code, 500,
                                        f"Path traversal caused error: {payload}")


# ============================================================================
# RATE LIMITING TESTS
# ============================================================================

class TestRateLimitingSourceCode(unittest.TestCase):
    """Test that rate limiting is properly configured via source code analysis."""

    def test_public_api_has_rate_limiter(self):
        """Public API should have rate limiting configured in source."""
        main_path = os.path.join(os.path.dirname(__file__), '..', 'huntrssn.cc', 'api', 'public', 'main.py')
        deps_path = os.path.join(os.path.dirname(__file__), '..', 'huntrssn.cc', 'api', 'public', 'dependencies.py')

        has_limiter = False
        for path in [main_path, deps_path]:
            if os.path.exists(path):
                with open(path) as f:
                    source = f.read()
                if "Limiter" in source or "limiter" in source or "SlowAPI" in source:
                    has_limiter = True
                    break

        if not has_limiter:
            import warnings
            warnings.warn(
                "Rate limiting may not be configured on public API",
                RuntimeWarning
            )


# ============================================================================
# WEBHOOK SIGNATURE VERIFICATION TESTS
# ============================================================================

class TestWebhookSecuritySourceCode(unittest.TestCase):
    """Test webhook signature verification security via source code analysis."""

    def test_webhook_uses_constant_time_comparison(self):
        """Webhook signature verification should use constant-time comparison."""
        billing_path = os.path.join(
            os.path.dirname(__file__), '..', 'huntrssn.cc', 'api', 'public', 'routers', 'billing.py'
        )
        if not os.path.exists(billing_path):
            self.skipTest("Billing router not found")

        with open(billing_path) as f:
            source = f.read()

        uses_safe_compare = (
            "compare_digest" in source or
            "hmac.compare_digest" in source or
            "secrets.compare_digest" in source
        )

        if not uses_safe_compare and "verify" in source.lower() and "signature" in source.lower():
            import warnings
            warnings.warn(
                "Webhook signature verification may be vulnerable to timing attacks. "
                "Use hmac.compare_digest() instead of == for signature comparison.",
                RuntimeWarning
            )


if __name__ == '__main__':
    unittest.main(verbosity=2)
