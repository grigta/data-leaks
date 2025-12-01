"""
Records router for Enrichment API (integration with DataManager).
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Header
from typing import List, Optional
from pydantic import BaseModel
from api.common.security import get_api_key
from api.common.models_sqlite import SSNRecordCreate, SSNRecordUpdate
from api.enrichment.dependencies import get_data_manager, get_webhook_secret
from database.data_manager import DataManager
import logging
import hmac
import hashlib
import json
import secrets
from datetime import datetime


logger = logging.getLogger(__name__)
router = APIRouter()


# Request models
class AddRecordRequest(BaseModel):
    """Request model for adding a record."""
    table_name: str
    record: SSNRecordCreate


class UpdateRecordRequest(BaseModel):
    """Request model for updating a record."""
    table_name: str
    ssn: str
    update_data: SSNRecordUpdate


class BulkAddRequest(BaseModel):
    """Request model for bulk adding records."""
    table_name: str
    records: List[SSNRecordCreate]


class EnrichRecordRequest(BaseModel):
    """Request model for enriching a record."""
    ssn: str
    table_name: str


# Endpoints
@router.post("/enrich-record")
async def enrich_record(
    request: EnrichRecordRequest,
    api_key: str = Depends(get_api_key),
    data_manager: DataManager = Depends(get_data_manager)
):
    """
    Enrich an SSN record by fetching additional data from the opposite table.

    Args:
        request: Enrichment request with SSN and source table
        api_key: Valid API key
        data_manager: DataManager instance

    Returns:
        Enriched record with updated fields and cost information

    Raises:
        HTTPException: If table_name is invalid or record not found
    """
    # Validate table name
    if request.table_name not in ['ssn_1', 'ssn_2']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="table_name must be either 'ssn_1' or 'ssn_2'"
        )

    # Determine opposite table for enrichment
    opposite_table = 'ssn_2' if request.table_name == 'ssn_1' else 'ssn_1'

    # Fetch current record
    current_record = data_manager.get_record(request.table_name, request.ssn)
    if not current_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Record with SSN {request.ssn} not found in {request.table_name}"
        )

    # Fetch enrichment data from opposite table
    enrichment_data = data_manager.get_record(opposite_table, request.ssn)
    if not enrichment_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No enrichment data found in {opposite_table} for SSN {request.ssn}"
        )

    # Determine which fields were updated (only non-empty fields that differ)
    updated_fields = []
    changes = {}

    for field, new_value in enrichment_data.items():
        # Skip SSN and metadata fields
        if field in ['ssn', 'id', 'created_at', 'updated_at']:
            continue

        # Only update if new value is not empty and different from current
        if new_value and (field not in current_record or current_record[field] != new_value):
            current_value = current_record.get(field)
            # Only add to changes if it's actually different
            if current_value != new_value:
                updated_fields.append(field)
                changes[field] = new_value

    # If there are changes, update the record
    if changes:
        data_manager.update_record(request.table_name, request.ssn, changes)
        # Fetch updated record
        updated_record = data_manager.get_record(request.table_name, request.ssn)
    else:
        updated_record = current_record

    # Calculate enrichment cost (fixed price from constants)
    enrichment_cost = 2.0  # $2.00 per enrichment

    # Log operation
    logger.info(
        f"Record enrichment - API Key: {api_key[:8]}***, "
        f"Table: {request.table_name}, SSN: {request.ssn[:3]}**, "
        f"Updated fields: {len(updated_fields)}, Cost: ${enrichment_cost}"
    )

    return {
        "record": updated_record,
        "updated_fields": updated_fields,
        "enrichment_cost": enrichment_cost,
        "changes": changes
    }



@router.post("/records/add")
async def add_record(
    request: AddRecordRequest,
    api_key: str = Depends(get_api_key),
    data_manager: DataManager = Depends(get_data_manager)
):
    """
    Add or update a single SSN record.

    Args:
        request: Record data
        api_key: Valid API key
        data_manager: DataManager instance

    Returns:
        Operation result

    Raises:
        HTTPException: If table_name is invalid
    """
    # Validate table name
    if request.table_name not in ['ssn_1', 'ssn_2']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="table_name must be either 'ssn_1' or 'ssn_2'"
        )

    # Convert Pydantic model to dict
    record_dict = request.record.model_dump()

    # Perform upsert
    result = data_manager.upsert_record(request.table_name, record_dict)

    # Log operation
    logger.info(
        f"Record upsert - API Key: {api_key[:8]}***, "
        f"Table: {request.table_name}, SSN: {record_dict['ssn'][:3]}**, "
        f"Success: {result.get('success')}"
    )

    return result


@router.put("/records/update")
async def update_record(
    request: UpdateRecordRequest,
    api_key: str = Depends(get_api_key),
    data_manager: DataManager = Depends(get_data_manager)
):
    """
    Update an existing SSN record.

    Args:
        request: Update data
        api_key: Valid API key
        data_manager: DataManager instance

    Returns:
        Operation result

    Raises:
        HTTPException: If table_name is invalid
    """
    # Validate table name
    if request.table_name not in ['ssn_1', 'ssn_2']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="table_name must be either 'ssn_1' or 'ssn_2'"
        )

    # Convert Pydantic model to dict (exclude unset fields)
    update_dict = request.update_data.model_dump(exclude_unset=True)

    # Perform update
    result = data_manager.update_record(request.table_name, request.ssn, update_dict)

    # Log operation
    logger.info(
        f"Record update - API Key: {api_key[:8]}***, "
        f"Table: {request.table_name}, SSN: {request.ssn[:3]}**, "
        f"Success: {result.get('success')}"
    )

    return result


@router.post("/records/bulk")
async def bulk_add_records(
    request: BulkAddRequest,
    api_key: str = Depends(get_api_key),
    data_manager: DataManager = Depends(get_data_manager)
):
    """
    Bulk add or update SSN records.

    Args:
        request: Bulk records data
        api_key: Valid API key
        data_manager: DataManager instance

    Returns:
        Operation statistics

    Raises:
        HTTPException: If table_name is invalid
    """
    # Validate table name
    if request.table_name not in ['ssn_1', 'ssn_2']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="table_name must be either 'ssn_1' or 'ssn_2'"
        )

    # Convert Pydantic models to dicts
    records_list = [record.model_dump() for record in request.records]

    # Perform bulk upsert
    result = data_manager.bulk_upsert(request.table_name, records_list)

    # Log operation
    logger.info(
        f"Bulk upsert - API Key: {api_key[:8]}***, "
        f"Table: {request.table_name}, Total: {result.get('total')}, "
        f"Successful: {result.get('successful')}, Failed: {result.get('failed')}"
    )

    return result


@router.delete("/records/{ssn}")
async def delete_record(
    ssn: str,
    table_name: str = Query(..., description="Table name (ssn_1 or ssn_2)"),
    api_key: str = Depends(get_api_key),
    data_manager: DataManager = Depends(get_data_manager)
):
    """
    Delete an SSN record.

    Args:
        ssn: SSN to delete
        table_name: Table name
        api_key: Valid API key
        data_manager: DataManager instance

    Returns:
        Operation result

    Raises:
        HTTPException: If table_name is invalid
    """
    # Validate table name
    if table_name not in ['ssn_1', 'ssn_2']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="table_name must be either 'ssn_1' or 'ssn_2'"
        )

    # Perform delete
    result = data_manager.delete_record(table_name, ssn)

    # Log operation
    logger.info(
        f"Record delete - API Key: {api_key[:8]}***, "
        f"Table: {table_name}, SSN: {ssn[:3]}**, "
        f"Success: {result.get('success')}"
    )

    return result


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify webhook signature using HMAC-SHA256.

    Args:
        payload: Raw request body bytes
        signature: Provided signature (hex string)
        secret: Webhook secret

    Returns:
        True if signature is valid, False otherwise
    """
    if not signature or not secret:
        return False

    try:
        # Compute expected signature
        expected_signature = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Use constant-time comparison to prevent timing attacks
        return secrets.compare_digest(signature, expected_signature)
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False


def transform_webhook_payload(payload: dict, source: str) -> dict:
    """
    Transform webhook payload based on source identifier.

    Args:
        payload: Raw webhook payload
        source: Source identifier (e.g., 'generic', 'service_a')

    Returns:
        Transformed payload in internal format

    Raises:
        ValueError: If transformation fails or required fields missing
    """
    if source == "generic":
        # Generic format already matches internal structure
        return payload

    elif source == "service_a":
        # Example transformation for external service format
        try:
            transformed = {}

            # Map field names
            field_mapping = {
                'social_security_number': 'ssn',
                'first_name': 'firstname',
                'last_name': 'lastname',
                'middle_name': 'middlename',
                'email_address': 'email',
                'phone_number': 'phone',
                'date_of_birth': 'dob',
                'street_address': 'address',
                'zip_code': 'zip'
            }

            for external_field, internal_field in field_mapping.items():
                if external_field in payload:
                    transformed[internal_field] = payload[external_field]

            # Also include any fields that already match internal format
            for field in ['ssn', 'firstname', 'lastname', 'middlename', 'email',
                         'phone', 'dob', 'address', 'city', 'state', 'zip']:
                if field in payload and field not in transformed:
                    transformed[field] = payload[field]

            # Validate required field
            if 'ssn' not in transformed:
                raise ValueError("Required field 'ssn' or 'social_security_number' missing")

            return transformed

        except Exception as e:
            raise ValueError(f"Transformation failed for source '{source}': {str(e)}")

    else:
        # Unknown source - try to use generic format
        logger.warning(f"Unknown webhook source: {source}, using generic format")
        return payload


@router.post("/webhook")
async def webhook_endpoint(
    request: Request,
    x_webhook_signature: Optional[str] = Header(None, alias="X-Webhook-Signature"),
    x_webhook_source: str = Header("generic", alias="X-Webhook-Source"),
    api_key: str = Depends(get_api_key),
    data_manager: DataManager = Depends(get_data_manager)
):
    """
    Webhook endpoint for external service integration.

    Supports operations: add, update, delete, bulk_add

    Args:
        request: FastAPI Request object
        x_webhook_signature: Optional HMAC-SHA256 signature (hex string)
        x_webhook_source: Source identifier for payload transformation
        api_key: Valid API key
        data_manager: DataManager instance

    Returns:
        Always returns 200 OK with operation result

    Example payload (generic format):
        {
            "operation": "add",
            "table_name": "ssn_1",
            "data": {
                "ssn": "123-45-6789",
                "firstname": "John",
                "lastname": "Doe",
                "email": "john@example.com"
            }
        }
    """
    try:
        # Read raw body for signature verification
        body = await request.body()

        # Parse JSON payload
        try:
            payload = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Webhook JSON decode error: {e}")
            return {
                "status": "error",
                "message": f"Invalid JSON payload: {str(e)}",
                "details": {}
            }

        # Verify signature if provided
        webhook_secret = get_webhook_secret()
        if x_webhook_signature and webhook_secret:
            if not verify_webhook_signature(body, x_webhook_signature, webhook_secret):
                logger.warning(
                    f"Webhook signature verification failed - "
                    f"API Key: {api_key[:8]}***, Source: {x_webhook_source}"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature"
                )
            logger.info(f"Webhook signature verified successfully")
        elif x_webhook_signature and not webhook_secret:
            logger.warning("Webhook signature provided but WEBHOOK_SECRET not configured")

        # Extract operation type
        operation = payload.get('operation') or payload.get('action', 'add')
        operation = operation.lower()

        # Extract and validate table_name
        table_name = payload.get('table_name') or payload.get('table', 'ssn_1')
        if table_name not in ['ssn_1', 'ssn_2']:
            logger.error(f"Invalid table_name: {table_name}")
            return {
                "status": "error",
                "message": f"Invalid table_name: {table_name}. Must be 'ssn_1' or 'ssn_2'",
                "details": {"table_name": table_name}
            }

        # Extract data
        data = payload.get('data')
        if data is None:
            logger.error("Missing 'data' field in webhook payload")
            return {
                "status": "error",
                "message": "Missing 'data' field in payload",
                "details": {}
            }

        # Log webhook receipt
        logger.info(
            f"Webhook received - API Key: {api_key[:8]}***, "
            f"Source: {x_webhook_source}, Operation: {operation}, "
            f"Table: {table_name}, Signature verified: {bool(x_webhook_signature and webhook_secret)}"
        )

        # Execute operation based on type
        result = None

        if operation == "add":
            # Transform payload
            try:
                transformed_data = transform_webhook_payload(data, x_webhook_source)
                logger.debug(f"Payload transformed for source: {x_webhook_source}")
            except ValueError as e:
                logger.error(f"Payload transformation error: {e}")
                return {
                    "status": "error",
                    "message": f"Payload transformation failed: {str(e)}",
                    "details": {"source": x_webhook_source}
                }

            # Perform upsert
            try:
                result = data_manager.upsert_record(table_name, transformed_data)
                ssn_masked = transformed_data.get('ssn', 'unknown')[:3] + "**"
                logger.info(
                    f"Webhook add operation completed - Table: {table_name}, "
                    f"SSN: {ssn_masked}, Success: {result.get('success')}"
                )
            except Exception as e:
                logger.error(f"Webhook add operation failed: {e}", exc_info=True)
                return {
                    "status": "error",
                    "message": f"Add operation failed: {str(e)}",
                    "details": {"operation": "add"}
                }

        elif operation == "update":
            # Transform payload
            try:
                transformed_data = transform_webhook_payload(data, x_webhook_source)
            except ValueError as e:
                logger.error(f"Payload transformation error: {e}")
                return {
                    "status": "error",
                    "message": f"Payload transformation failed: {str(e)}",
                    "details": {"source": x_webhook_source}
                }

            # Extract SSN
            ssn = transformed_data.get('ssn')
            if not ssn:
                logger.error("Missing SSN in update operation")
                return {
                    "status": "error",
                    "message": "Missing SSN for update operation",
                    "details": {"operation": "update"}
                }

            # Perform update
            try:
                result = data_manager.update_record(table_name, ssn, transformed_data)
                ssn_masked = ssn[:3] + "**"
                logger.info(
                    f"Webhook update operation completed - Table: {table_name}, "
                    f"SSN: {ssn_masked}, Success: {result.get('success')}"
                )
            except Exception as e:
                logger.error(f"Webhook update operation failed: {e}", exc_info=True)
                return {
                    "status": "error",
                    "message": f"Update operation failed: {str(e)}",
                    "details": {"operation": "update"}
                }

        elif operation == "delete":
            # Transform payload to get SSN
            try:
                transformed_data = transform_webhook_payload(data, x_webhook_source)
            except ValueError as e:
                logger.error(f"Payload transformation error: {e}")
                return {
                    "status": "error",
                    "message": f"Payload transformation failed: {str(e)}",
                    "details": {"source": x_webhook_source}
                }

            # Extract SSN
            ssn = transformed_data.get('ssn')
            if not ssn:
                logger.error("Missing SSN in delete operation")
                return {
                    "status": "error",
                    "message": "Missing SSN for delete operation",
                    "details": {"operation": "delete"}
                }

            # Perform delete
            try:
                result = data_manager.delete_record(table_name, ssn)
                ssn_masked = ssn[:3] + "**"
                logger.info(
                    f"Webhook delete operation completed - Table: {table_name}, "
                    f"SSN: {ssn_masked}, Success: {result.get('success')}"
                )
            except Exception as e:
                logger.error(f"Webhook delete operation failed: {e}", exc_info=True)
                return {
                    "status": "error",
                    "message": f"Delete operation failed: {str(e)}",
                    "details": {"operation": "delete"}
                }

        elif operation == "bulk_add":
            # Data should be a list
            if not isinstance(data, list):
                logger.error("bulk_add operation requires data to be a list")
                return {
                    "status": "error",
                    "message": "bulk_add operation requires 'data' to be a list of records",
                    "details": {"operation": "bulk_add"}
                }

            # Transform each record
            try:
                transformed_records = [
                    transform_webhook_payload(record, x_webhook_source)
                    for record in data
                ]
                logger.debug(f"Transformed {len(transformed_records)} records")
            except ValueError as e:
                logger.error(f"Payload transformation error: {e}")
                return {
                    "status": "error",
                    "message": f"Payload transformation failed: {str(e)}",
                    "details": {"source": x_webhook_source}
                }

            # Perform bulk upsert
            try:
                result = data_manager.bulk_upsert(table_name, transformed_records)
                logger.info(
                    f"Webhook bulk_add operation completed - Table: {table_name}, "
                    f"Total: {result.get('total')}, Successful: {result.get('successful')}, "
                    f"Failed: {result.get('failed')}"
                )
            except Exception as e:
                logger.error(f"Webhook bulk_add operation failed: {e}", exc_info=True)
                return {
                    "status": "error",
                    "message": f"Bulk add operation failed: {str(e)}",
                    "details": {"operation": "bulk_add"}
                }

        else:
            logger.error(f"Unknown operation: {operation}")
            return {
                "status": "error",
                "message": f"Unknown operation: {operation}. Supported: add, update, delete, bulk_add",
                "details": {"operation": operation}
            }

        # Return success response
        return {
            "status": "success",
            "message": f"Operation '{operation}' completed successfully",
            "details": result or {}
        }

    except HTTPException:
        # Re-raise HTTP exceptions (like 401 for invalid signature)
        raise
    except Exception as e:
        # Catch all other exceptions and return 200 OK with error details
        logger.error(f"Webhook unexpected error: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Internal error: {str(e)}",
            "details": {}
        }
