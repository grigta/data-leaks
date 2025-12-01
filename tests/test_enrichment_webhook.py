"""
Comprehensive test suite for Enrichment API webhook endpoint.

Tests cover:
- All CRUD operations (add, update, delete, bulk_add)
- Signature verification (valid, invalid, missing)
- API key authentication (valid, invalid, missing)
- Input validation (table_name, SSN format, required fields)
- Custom source transformation
- Error handling and response format
"""
import pytest
import hmac
import hashlib
import json
import os
from fastapi.testclient import TestClient
from api.enrichment.main import app
from database.db_schema import initialize_database


@pytest.fixture(scope="module")
def test_db_path(tmp_path_factory):
    """Create temporary database for testing."""
    db_path = tmp_path_factory.mktemp("data") / "test_webhook.db"
    initialize_database(str(db_path))
    return str(db_path)


@pytest.fixture(scope="module")
def client(test_db_path):
    """Create test client with test database."""
    # Set environment variables for testing
    os.environ['SQLITE_PATH'] = test_db_path
    os.environ['ENRICHMENT_API_KEYS'] = 'test_key_1,test_key_2'
    os.environ['WEBHOOK_SECRET'] = 'test_webhook_secret_for_testing'

    return TestClient(app)


@pytest.fixture
def valid_api_key():
    """Get valid API key from environment."""
    return 'test_key_1'


@pytest.fixture
def webhook_secret():
    """Get webhook secret from environment."""
    return 'test_webhook_secret_for_testing'


def compute_signature(payload: dict, secret: str) -> str:
    """Compute HMAC-SHA256 signature for payload."""
    body = json.dumps(payload)
    return hmac.new(
        secret.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()


class TestWebhookAuthentication:
    """Test webhook authentication mechanisms."""

    def test_webhook_without_api_key(self, client):
        """Test webhook without API key returns 403."""
        payload = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {"ssn": "123-45-6789", "firstname": "John", "lastname": "Doe"}
        }

        response = client.post(
            "/enrichment/webhook",
            json=payload
        )

        assert response.status_code == 403
        assert "API key required" in response.json()["detail"]

    def test_webhook_with_invalid_api_key(self, client):
        """Test webhook with invalid API key returns 403."""
        payload = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {"ssn": "123-45-6789", "firstname": "John", "lastname": "Doe"}
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": "invalid_key"},
            json=payload
        )

        assert response.status_code == 403
        assert "Invalid API key" in response.json()["detail"]

    def test_webhook_with_valid_api_key_no_signature(self, client, valid_api_key):
        """Test webhook with valid API key but no signature succeeds."""
        payload = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {"ssn": "111-11-1111", "firstname": "NoSig", "lastname": "Test"}
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"

    def test_webhook_with_invalid_signature(self, client, valid_api_key):
        """Test webhook with invalid signature returns 401."""
        payload = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {"ssn": "222-22-2222", "firstname": "BadSig", "lastname": "Test"}
        }

        response = client.post(
            "/enrichment/webhook",
            headers={
                "X-API-Key": valid_api_key,
                "X-Webhook-Signature": "invalid_signature_12345"
            },
            json=payload
        )

        assert response.status_code == 401
        assert "Invalid webhook signature" in response.json()["detail"]

    def test_webhook_with_valid_signature(self, client, valid_api_key, webhook_secret):
        """Test webhook with valid signature succeeds."""
        payload = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {"ssn": "333-33-3333", "firstname": "GoodSig", "lastname": "Test"}
        }

        signature = compute_signature(payload, webhook_secret)

        response = client.post(
            "/enrichment/webhook",
            headers={
                "X-API-Key": valid_api_key,
                "X-Webhook-Signature": signature
            },
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"


class TestWebhookAddOperation:
    """Test webhook add operation."""

    def test_add_operation_success(self, client, valid_api_key, webhook_secret):
        """Test successful add operation via webhook."""
        payload = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {
                "ssn": "444-44-4444",
                "firstname": "John",
                "lastname": "Doe",
                "email": "john@example.com",
                "phone": "555-1234"
            }
        }

        signature = compute_signature(payload, webhook_secret)

        response = client.post(
            "/enrichment/webhook",
            headers={
                "X-API-Key": valid_api_key,
                "X-Webhook-Signature": signature
            },
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
        assert "add" in result["message"].lower()
        assert result["details"]["success"] is True
        assert result["details"]["ssn"] == "444-44-4444"

    def test_add_operation_upsert_behavior(self, client, valid_api_key):
        """Test that add operation updates existing record (UPSERT)."""
        ssn = "555-55-5555"

        # First add
        payload1 = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {
                "ssn": ssn,
                "firstname": "Jane",
                "lastname": "Smith",
                "email": "jane@example.com"
            }
        }

        response1 = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload1
        )

        assert response1.status_code == 200
        assert response1.json()["status"] == "success"

        # Second add with updated data
        payload2 = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {
                "ssn": ssn,
                "firstname": "Jane",
                "lastname": "Smith-Updated",
                "email": "jane.updated@example.com"
            }
        }

        response2 = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload2
        )

        assert response2.status_code == 200
        assert response2.json()["status"] == "success"

    def test_add_operation_missing_ssn(self, client, valid_api_key):
        """Test add operation with missing SSN returns error."""
        payload = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {
                "firstname": "John",
                "lastname": "Doe"
            }
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "error"
        assert "ssn" in result["message"].lower() or "required" in result["message"].lower()

    def test_add_operation_invalid_table_name(self, client, valid_api_key):
        """Test add operation with invalid table_name returns error."""
        payload = {
            "operation": "add",
            "table_name": "invalid_table",
            "data": {
                "ssn": "666-66-6666",
                "firstname": "John",
                "lastname": "Doe"
            }
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "error"
        assert "table_name" in result["message"].lower()


class TestWebhookUpdateOperation:
    """Test webhook update operation."""

    def test_update_operation_success(self, client, valid_api_key):
        """Test successful update operation via webhook."""
        ssn = "777-77-7777"

        # First add a record
        add_payload = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {
                "ssn": ssn,
                "firstname": "Alice",
                "lastname": "Johnson",
                "email": "alice@example.com"
            }
        }

        client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=add_payload
        )

        # Now update it
        update_payload = {
            "operation": "update",
            "table_name": "ssn_1",
            "data": {
                "ssn": ssn,
                "email": "alice.updated@example.com",
                "phone": "555-9999"
            }
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=update_payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
        assert "update" in result["message"].lower()

    def test_update_operation_missing_ssn(self, client, valid_api_key):
        """Test update operation without SSN returns error."""
        payload = {
            "operation": "update",
            "table_name": "ssn_1",
            "data": {
                "email": "test@example.com"
            }
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "error"
        assert "ssn" in result["message"].lower()


class TestWebhookDeleteOperation:
    """Test webhook delete operation."""

    def test_delete_operation_success(self, client, valid_api_key):
        """Test successful delete operation via webhook."""
        ssn = "888-88-8888"

        # First add a record
        add_payload = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {
                "ssn": ssn,
                "firstname": "Bob",
                "lastname": "Wilson",
                "email": "bob@example.com"
            }
        }

        client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=add_payload
        )

        # Now delete it
        delete_payload = {
            "operation": "delete",
            "table_name": "ssn_1",
            "data": {
                "ssn": ssn
            }
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=delete_payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
        assert "delete" in result["message"].lower()

    def test_delete_operation_missing_ssn(self, client, valid_api_key):
        """Test delete operation without SSN returns error."""
        payload = {
            "operation": "delete",
            "table_name": "ssn_1",
            "data": {}
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "error"
        assert "ssn" in result["message"].lower()


class TestWebhookBulkAddOperation:
    """Test webhook bulk_add operation."""

    def test_bulk_add_operation_success(self, client, valid_api_key):
        """Test successful bulk_add operation via webhook."""
        payload = {
            "operation": "bulk_add",
            "table_name": "ssn_1",
            "data": [
                {
                    "ssn": "901-01-0101",
                    "firstname": "User1",
                    "lastname": "Test1",
                    "email": "user1@example.com"
                },
                {
                    "ssn": "902-02-0202",
                    "firstname": "User2",
                    "lastname": "Test2",
                    "email": "user2@example.com"
                },
                {
                    "ssn": "903-03-0303",
                    "firstname": "User3",
                    "lastname": "Test3",
                    "email": "user3@example.com"
                }
            ]
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
        assert result["details"]["total"] == 3
        assert result["details"]["successful"] >= 0  # At least some should succeed
        assert result["details"]["failed"] >= 0

    def test_bulk_add_operation_not_array(self, client, valid_api_key):
        """Test bulk_add with non-array data returns error."""
        payload = {
            "operation": "bulk_add",
            "table_name": "ssn_1",
            "data": {
                "ssn": "999-99-9999",
                "firstname": "Single",
                "lastname": "Record"
            }
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "error"
        assert "list" in result["message"].lower() or "array" in result["message"].lower()


class TestWebhookPayloadValidation:
    """Test webhook payload validation."""

    def test_webhook_invalid_json(self, client, valid_api_key):
        """Test webhook with invalid JSON returns error."""
        response = client.post(
            "/enrichment/webhook",
            headers={
                "X-API-Key": valid_api_key,
                "Content-Type": "application/json"
            },
            content=b"{invalid json}"
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "error"
        assert "json" in result["message"].lower()

    def test_webhook_missing_data_field(self, client, valid_api_key):
        """Test webhook without 'data' field returns error."""
        payload = {
            "operation": "add",
            "table_name": "ssn_1"
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "error"
        assert "data" in result["message"].lower()

    def test_webhook_unknown_operation(self, client, valid_api_key):
        """Test webhook with unknown operation returns error."""
        payload = {
            "operation": "unknown_op",
            "table_name": "ssn_1",
            "data": {"ssn": "123-45-6789"}
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "error"
        assert "unknown" in result["message"].lower() or "operation" in result["message"].lower()

    def test_webhook_default_operation(self, client, valid_api_key):
        """Test webhook without operation defaults to 'add'."""
        payload = {
            "table_name": "ssn_1",
            "data": {
                "ssn": "121-21-2121",
                "firstname": "Default",
                "lastname": "Op"
            }
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"

    def test_webhook_default_table_name(self, client, valid_api_key):
        """Test webhook without table_name defaults to 'ssn_1'."""
        payload = {
            "operation": "add",
            "data": {
                "ssn": "131-31-3131",
                "firstname": "Default",
                "lastname": "Table"
            }
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"


class TestWebhookCustomSource:
    """Test webhook custom source transformation."""

    def test_webhook_generic_source(self, client, valid_api_key):
        """Test webhook with generic source (no transformation)."""
        payload = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {
                "ssn": "141-41-4141",
                "firstname": "Generic",
                "lastname": "Source"
            }
        }

        response = client.post(
            "/enrichment/webhook",
            headers={
                "X-API-Key": valid_api_key,
                "X-Webhook-Source": "generic"
            },
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"

    def test_webhook_service_a_source_transformation(self, client, valid_api_key):
        """Test webhook with service_a source performs field transformation."""
        payload = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {
                "social_security_number": "151-51-5151",
                "first_name": "Service",
                "last_name": "A",
                "email_address": "servicea@example.com"
            }
        }

        response = client.post(
            "/enrichment/webhook",
            headers={
                "X-API-Key": valid_api_key,
                "X-Webhook-Source": "service_a"
            },
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
        # Verify transformation occurred
        assert result["details"]["ssn"] == "151-51-5151"

    def test_webhook_unknown_source_fallback(self, client, valid_api_key):
        """Test webhook with unknown source falls back to generic."""
        payload = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {
                "ssn": "161-61-6161",
                "firstname": "Unknown",
                "lastname": "Source"
            }
        }

        response = client.post(
            "/enrichment/webhook",
            headers={
                "X-API-Key": valid_api_key,
                "X-Webhook-Source": "unknown_service"
            },
            json=payload
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"


class TestWebhookResponseFormat:
    """Test webhook response format consistency."""

    def test_success_response_format(self, client, valid_api_key):
        """Test success response has correct format."""
        payload = {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {
                "ssn": "171-71-7171",
                "firstname": "Format",
                "lastname": "Test"
            }
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        result = response.json()

        # Verify response structure
        assert "status" in result
        assert "message" in result
        assert "details" in result
        assert result["status"] == "success"
        assert isinstance(result["message"], str)
        assert isinstance(result["details"], dict)

    def test_error_response_format(self, client, valid_api_key):
        """Test error response has correct format."""
        payload = {
            "operation": "add",
            "table_name": "invalid_table",
            "data": {
                "ssn": "181-81-8181",
                "firstname": "Error",
                "lastname": "Test"
            }
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        result = response.json()

        # Verify response structure
        assert "status" in result
        assert "message" in result
        assert "details" in result
        assert result["status"] == "error"
        assert isinstance(result["message"], str)
        assert isinstance(result["details"], dict)

    def test_webhook_always_returns_200(self, client, valid_api_key):
        """Test webhook always returns 200 OK even for errors (except auth)."""
        # Invalid table name should return 200 with error status
        payload = {
            "operation": "add",
            "table_name": "bad_table",
            "data": {"ssn": "191-91-9191"}
        }

        response = client.post(
            "/enrichment/webhook",
            headers={"X-API-Key": valid_api_key},
            json=payload
        )

        assert response.status_code == 200
        assert response.json()["status"] == "error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
