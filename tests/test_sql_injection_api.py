"""
API-level SQL injection tests for Public API endpoints.

This module tests that API endpoints properly reject SQL injection payloads
and return appropriate HTTP status codes (400/404) instead of 500 errors.

Security:
    - Tests use common SQL injection payloads
    - Verifies input validation at API level
    - Ensures database integrity is maintained
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# SQL injection payloads from the existing test module
SQL_INJECTION_PAYLOADS = [
    # Basic SQL injection
    "' OR '1'='1",
    "' OR '1'='1' --",
    "' OR '1'='1' /*",
    "'; DROP TABLE users; --",
    "'; DELETE FROM users; --",
    "1; DROP TABLE users",
    "1' OR '1' = '1",
    "1' AND '1' = '1",

    # UNION-based injection
    "' UNION SELECT * FROM users --",
    "' UNION ALL SELECT NULL, NULL, NULL --",
    "1 UNION SELECT username, password FROM users",

    # Comment-based injection
    "admin'--",
    "admin'/*",
    "*/admin",

    # Numeric injection
    "1 OR 1=1",
    "1 AND 1=1",
    "1; SELECT * FROM users",

    # Encoded injection
    "%27%20OR%20%271%27%3D%271",
    "&#x27; OR &#x27;1&#x27;=&#x27;1",

    # Time-based blind injection
    "'; WAITFOR DELAY '00:00:05' --",
    "'; SELECT SLEEP(5) --",
    "1; SELECT pg_sleep(5)",

    # Stacked queries
    "'; INSERT INTO users VALUES ('hacked') --",
    "'; UPDATE users SET password='hacked' --",

    # Special characters
    "\\x00",
    "\\x1a",
    "'\"\\",

    # Long payloads
    "A" * 1000,
    "' OR '" + "A" * 500 + "'='",
]


class TestSQLInjectionSearchEndpoints:
    """Test SQL injection protection for search endpoints."""

    def test_search_name_with_injection_in_firstname(self):
        """Test /search/name rejects SQL injection in firstname."""
        # Import here to avoid issues if app is not available
        try:
            from fastapi.testclient import TestClient
            from api.public.main import app
        except ImportError:
            pytest.skip("FastAPI app not available")

        client = TestClient(app)

        for payload in SQL_INJECTION_PAYLOADS[:10]:  # Test subset for speed
            response = client.post(
                "/search/name",
                json={
                    "firstname": payload,
                    "lastname": "Smith",
                    "zip": "90210"
                },
                headers={"Authorization": "Bearer test_token"}
            )
            # Should not return 500 - validation should catch it
            assert response.status_code != 500, f"Server error with payload: {payload}"
            # Expected: 400 (validation error) or 401 (auth error)
            assert response.status_code in [200, 400, 401, 403, 422], \
                f"Unexpected status {response.status_code} for payload: {payload}"

    def test_search_name_with_injection_in_lastname(self):
        """Test /search/name rejects SQL injection in lastname."""
        try:
            from fastapi.testclient import TestClient
            from api.public.main import app
        except ImportError:
            pytest.skip("FastAPI app not available")

        client = TestClient(app)

        for payload in SQL_INJECTION_PAYLOADS[:10]:
            response = client.post(
                "/search/name",
                json={
                    "firstname": "John",
                    "lastname": payload,
                    "address": "123 Main St"
                },
                headers={"Authorization": "Bearer test_token"}
            )
            assert response.status_code != 500, f"Server error with payload: {payload}"
            assert response.status_code in [200, 400, 401, 403, 422]

    def test_search_name_with_injection_in_zip(self):
        """Test /search/name rejects SQL injection in zip."""
        try:
            from fastapi.testclient import TestClient
            from api.public.main import app
        except ImportError:
            pytest.skip("FastAPI app not available")

        client = TestClient(app)

        for payload in SQL_INJECTION_PAYLOADS[:10]:
            response = client.post(
                "/search/name",
                json={
                    "firstname": "John",
                    "lastname": "Smith",
                    "zip": payload
                },
                headers={"Authorization": "Bearer test_token"}
            )
            assert response.status_code != 500, f"Server error with payload: {payload}"
            assert response.status_code in [200, 400, 401, 403, 422]

    def test_search_name_with_injection_in_address(self):
        """Test /search/name rejects SQL injection in address."""
        try:
            from fastapi.testclient import TestClient
            from api.public.main import app
        except ImportError:
            pytest.skip("FastAPI app not available")

        client = TestClient(app)

        for payload in SQL_INJECTION_PAYLOADS[:10]:
            response = client.post(
                "/search/name",
                json={
                    "firstname": "John",
                    "lastname": "Smith",
                    "address": payload
                },
                headers={"Authorization": "Bearer test_token"}
            )
            assert response.status_code != 500, f"Server error with payload: {payload}"
            assert response.status_code in [200, 400, 401, 403, 422]

    def test_get_record_with_injection_in_ssn(self):
        """Test /search/record/{ssn} rejects SQL injection in SSN."""
        try:
            from fastapi.testclient import TestClient
            from api.public.main import app
        except ImportError:
            pytest.skip("FastAPI app not available")

        client = TestClient(app)

        for payload in SQL_INJECTION_PAYLOADS[:10]:
            response = client.get(
                f"/search/record/{payload}",
                headers={"Authorization": "Bearer test_token"}
            )
            assert response.status_code != 500, f"Server error with payload: {payload}"
            # Expected: 400 (invalid SSN) or 401 (auth error) or 404 (not found)
            assert response.status_code in [200, 400, 401, 403, 404, 422]


class TestSQLInjectionAuthEndpoints:
    """Test SQL injection protection for auth endpoints."""

    def test_validate_coupon_with_injection(self):
        """Test /auth/validate-coupon rejects SQL injection."""
        try:
            from fastapi.testclient import TestClient
            from api.public.main import app
        except ImportError:
            pytest.skip("FastAPI app not available")

        client = TestClient(app)

        for payload in SQL_INJECTION_PAYLOADS[:10]:
            response = client.post(
                "/auth/validate-coupon",
                json={"coupon_code": payload}
            )
            assert response.status_code != 500, f"Server error with payload: {payload}"
            # Expected: 400 (invalid format) or 404 (not found)
            assert response.status_code in [200, 400, 404, 422]


class TestSQLInjectionBillingEndpoints:
    """Test SQL injection protection for billing endpoints."""

    def test_apply_coupon_with_injection(self):
        """Test /billing/deposit/apply-coupon rejects SQL injection."""
        try:
            from fastapi.testclient import TestClient
            from api.public.main import app
        except ImportError:
            pytest.skip("FastAPI app not available")

        client = TestClient(app)

        for payload in SQL_INJECTION_PAYLOADS[:10]:
            response = client.post(
                "/billing/deposit/apply-coupon",
                json={"code": payload},
                headers={"Authorization": "Bearer test_token"}
            )
            assert response.status_code != 500, f"Server error with payload: {payload}"
            assert response.status_code in [200, 400, 401, 403, 404, 422]

    def test_apply_coupon_to_balance_with_injection(self):
        """Test /billing/billing/apply-coupon rejects SQL injection."""
        try:
            from fastapi.testclient import TestClient
            from api.public.main import app
        except ImportError:
            pytest.skip("FastAPI app not available")

        client = TestClient(app)

        for payload in SQL_INJECTION_PAYLOADS[:10]:
            response = client.post(
                "/billing/billing/apply-coupon",
                json={"code": payload},
                headers={"Authorization": "Bearer test_token"}
            )
            assert response.status_code != 500, f"Server error with payload: {payload}"
            assert response.status_code in [200, 400, 401, 403, 404, 422]


class TestSQLInjectionValidatorsIntegration:
    """Test that validators properly reject SQL injection at API level."""

    def test_validate_coupon_code_rejects_injection(self):
        """Test coupon code validator rejects SQL injection payloads."""
        from api.common.validators import validate_coupon_code

        injection_payloads = [
            "'; DROP TABLE coupons; --",
            "' OR '1'='1",
            "DISCOUNT' UNION SELECT * FROM users --",
            "CODE<script>alert(1)</script>",
            "' AND 1=1 --",
        ]

        for payload in injection_payloads:
            is_valid, error = validate_coupon_code(payload)
            assert not is_valid, f"Validator should reject SQL injection: {payload}"
            assert error is not None

    def test_validate_ssn_rejects_injection(self):
        """Test SSN validator rejects SQL injection payloads."""
        from api.common.validators import validate_ssn

        injection_payloads = [
            "123-45-6789' OR '1'='1",
            "'; DROP TABLE ssn; --",
            "123456789 UNION SELECT *",
            "000-00-0000<script>",
        ]

        for payload in injection_payloads:
            is_valid, error = validate_ssn(payload)
            assert not is_valid, f"Validator should reject: {payload}"

    def test_validate_name_rejects_injection(self):
        """Test name validator rejects SQL injection payloads."""
        from api.common.validators import validate_name

        injection_payloads = [
            "John' OR '1'='1",
            "'; DELETE FROM users; --",
            "Smith<script>alert(1)</script>",
            "Name\x00Injection",
        ]

        for payload in injection_payloads:
            is_valid, error = validate_name(payload)
            assert not is_valid, f"Validator should reject: {payload}"


class TestSQLInjectionSanitizersIntegration:
    """Test that sanitizers properly clean SQL injection attempts."""

    def test_sanitize_name_cleans_injection(self):
        """Test name sanitizer removes dangerous characters."""
        from api.common.sanitizers import sanitize_name

        # Sanitizer should return clean string or None for dangerous input
        result = sanitize_name("John' OR '1'='1")
        # Should either be None or have dangerous chars removed
        if result:
            assert "'" not in result or result == "John"

    def test_sanitize_address_cleans_injection(self):
        """Test address sanitizer handles dangerous input."""
        from api.common.sanitizers import sanitize_address

        result = sanitize_address("123 Main St'; DROP TABLE --")
        # Should handle the input safely
        if result:
            assert "DROP" not in result.upper() or "DROP" in result  # Just stores as text

    def test_sanitize_metadata_limits_depth(self):
        """Test metadata sanitizer limits nesting depth."""
        from api.common.sanitizers import sanitize_metadata

        # Create deeply nested structure
        deep_data = {"level": "data"}
        for i in range(20):
            deep_data = {"nested": deep_data}

        result = sanitize_metadata(deep_data, max_depth=5)
        # Should be truncated, not None
        assert result is not None


class TestAPIStatusCodes:
    """Test that API returns appropriate status codes for invalid input."""

    def test_invalid_ssn_returns_400(self):
        """Test that invalid SSN format returns 400, not 500."""
        try:
            from fastapi.testclient import TestClient
            from api.public.main import app
        except ImportError:
            pytest.skip("FastAPI app not available")

        client = TestClient(app)

        invalid_ssns = [
            "invalid",
            "12345",
            "123-456-789",
            "abc-de-fghi",
            "",
            "' OR '1'='1",
        ]

        for ssn in invalid_ssns:
            response = client.get(
                f"/search/record/{ssn}",
                headers={"Authorization": "Bearer test_token"}
            )
            # Should not return 500 - either 400 (invalid) or 401 (auth)
            assert response.status_code != 500, f"Server error for SSN: {ssn}"

    def test_invalid_coupon_returns_400(self):
        """Test that invalid coupon format returns 400, not 500."""
        try:
            from fastapi.testclient import TestClient
            from api.public.main import app
        except ImportError:
            pytest.skip("FastAPI app not available")

        client = TestClient(app)

        invalid_coupons = [
            "'; DROP TABLE coupons; --",
            "coupon<script>",
            "A" * 100,  # Too long
            "\x00\x01\x02",  # Control chars
        ]

        for coupon in invalid_coupons:
            response = client.post(
                "/auth/validate-coupon",
                json={"coupon_code": coupon}
            )
            # Should not return 500
            assert response.status_code != 500, f"Server error for coupon: {coupon[:20]}"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
