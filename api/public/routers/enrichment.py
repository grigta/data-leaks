"""
Public API router for data enrichment functionality.
"""
import logging
import re
from decimal import Decimal
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from api.common.database import get_postgres_session, SQLITE_PATH
from api.common.models_postgres import User
from api.common.models_sqlite import SSNRecord
from api.public.dependencies import get_current_user, limiter
from database.data_manager import DataManager
from api.common.searchbug_client import (
    create_searchbug_client,
    SearchbugAPIError,
    SearchbugRateLimitError,
    SearchbugNotFoundError
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Enrichment costs (two-tier pricing)
ENRICHMENT_FAILURE_COST = Decimal('3.00')  # Base cost for failed enrichment
ENRICHMENT_SUCCESS_COST = Decimal('3.50')  # Total cost for successful enrichment
ENRICHMENT_SUCCESS_ADDITIONAL = Decimal('0.50')  # Additional charge for success

# Safe fields that can be updated during enrichment
SAFE_UPDATE_FIELDS = {'dob', 'address', 'city', 'state', 'zip', 'phone', 'email', 'middlename'}


class EnrichRecordRequest(BaseModel):
    """Request model for enriching a record."""
    ssn: str
    table_name: str

    @field_validator('ssn')
    @classmethod
    def validate_ssn(cls, v: str) -> str:
        """Validate SSN format (9 digits or with dashes)."""
        # Remove dashes for validation
        ssn_digits = v.replace('-', '')
        if not re.match(r'^\d{9}$', ssn_digits):
            raise ValueError('SSN must be 9 digits, optionally formatted as XXX-XX-XXXX')
        return v

    @field_validator('table_name')
    @classmethod
    def validate_table_name(cls, v):
        if v not in ['ssn_1', 'ssn_2']:
            raise ValueError('table_name must be either ssn_1 or ssn_2')
        return v


class EnrichRecordResponse(BaseModel):
    """Response model for enriching a record."""
    record: SSNRecord
    updated_fields: list[str]
    enrichment_cost: float
    enrichment_success: bool  # Whether enrichment was successful
    changes: dict[str, Any]  # Only changed key-value pairs


class EnrichByNameZipRequest(BaseModel):
    """Request model for enriching by name and ZIP code (third enrichment method)."""
    firstname: str
    lastname: str
    zip: str
    table_name: str

    @field_validator('firstname', 'lastname')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate name is not empty."""
        if not v or not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()

    @field_validator('zip')
    @classmethod
    def validate_zip(cls, v: str) -> str:
        """Validate ZIP code format (5 digits)."""
        zip_clean = v.strip()
        if not re.match(r'^\d{5}$', zip_clean):
            raise ValueError('ZIP code must be exactly 5 digits')
        return zip_clean

    @field_validator('table_name')
    @classmethod
    def validate_table_name(cls, v):
        if v not in ['ssn_1', 'ssn_2']:
            raise ValueError('table_name must be either ssn_1 or ssn_2')
        return v


@router.post("/enrich-record", response_model=EnrichRecordResponse)
# @limiter.limit("10/hour")  # Commented out for testing
async def enrich_record(
    request: Request,
    response: Response,
    enrich_request: EnrichRecordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Enrich a record with data from external API.

    Two-tier pricing:
    - $3.00 if enrichment fails (no changes found)
    - $3.50 if enrichment succeeds (data updated)

    Uses first candidate from external API with basic name verification.
    External API returns results ordered by relevance.

    Two-phase atomic approach:
    1. Charge: Atomically deduct base cost ($3.00) in Postgres with row lock, then commit
    2. Apply: Update SQLite record; if successful, charge additional $0.50
    3. If SQLite update fails, compensate by refunding the base charge

    This ensures cross-DB consistency: enrichment updates never persist without payment.
    """
    # Mask SSN for logging (show last 4 digits)
    masked_ssn = f"***-**-{enrich_request.ssn[-4:]}" if len(enrich_request.ssn) >= 4 else "***"
    logger.info(f"Enrichment request for SSN {masked_ssn} in {enrich_request.table_name} by user {current_user.id}")

    # Step 1: Validate SSN exists in SQLite
    data_manager = DataManager(db_path=SQLITE_PATH)
    current_record = data_manager.get_record(enrich_request.table_name, enrich_request.ssn)

    if current_record is None:
        logger.warning(f"SSN {masked_ssn} not found in {enrich_request.table_name}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSN record not found in {enrich_request.table_name}"
        )

    # Step 2: Fast-fail pre-check for insufficient balance (optional optimization)
    # Note: Final enforcement happens atomically in the UPDATE statement below
    if current_user.balance < ENRICHMENT_FAILURE_COST:
        logger.warning(
            f"Insufficient balance for user {current_user.id}: "
            f"required ${ENRICHMENT_FAILURE_COST}, available ${current_user.balance}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Required: ${ENRICHMENT_FAILURE_COST}, Available: ${current_user.balance}"
        )

    # Step 3: Call external API for enrichment
    try:
        async with create_searchbug_client() as sb_client:
            # Map our DB fields to external API format (address->street, zip->zipcode)
            # SECURITY: SSN is never sent to external API
            searchbug_record = {
                'firstname': current_record.get('firstname'),
                'lastname': current_record.get('lastname'),
                'middlename': current_record.get('middlename'),
                'city': current_record.get('city'),
                'state': current_record.get('state'),
                'phone': current_record.get('phone'),
                'dob': current_record.get('dob'),
                'email': current_record.get('email'),
                'street': current_record.get('address'),  # Map address -> street
                'zipcode': current_record.get('zip')  # Map zip -> zipcode
            }

            logger.info(f"Calling external API for SSN {masked_ssn}")
            enriched_data = await sb_client.enrich_person_data(searchbug_record)
            logger.info(f"External API returned data for SSN {masked_ssn}: {len(enriched_data)} fields")

    except HTTPException:
        # Re-raise HTTPException as-is
        raise
    except SearchbugRateLimitError as e:
        logger.error(f"External API rate limit exceeded for SSN {masked_ssn}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
    except SearchbugAPIError as e:
        logger.error(f"External API error for SSN {masked_ssn}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to enrich data: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during enrichment for SSN {masked_ssn}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during enrichment"
        )

    # Step 4: Map enriched data back to our DB format
    if not enriched_data:
        logger.warning(f"No matching data found for SSN {masked_ssn}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching data found"
        )

    # Map enriched fields back to our DB fields (street->address, zipcode->zip)
    update_data = {}
    if 'street' in enriched_data and enriched_data['street']:
        update_data['address'] = enriched_data['street']
    if 'zipcode' in enriched_data and enriched_data['zipcode']:
        update_data['zip'] = enriched_data['zipcode']

    # Copy other fields directly
    for field in ['firstname', 'lastname', 'middlename', 'city', 'state', 'phone', 'dob', 'email']:
        if field in enriched_data and enriched_data[field]:
            update_data[field] = enriched_data[field]

    # SECURITY: Filter to only safe fields - never update firstname, lastname
    update_data = {k: v for k, v in update_data.items() if k in SAFE_UPDATE_FIELDS}

    if not update_data:
        logger.warning(f"Enriched data contained no usable fields for SSN {masked_ssn}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching data found"
        )

    # Step 5: Check if there are actual changes before charging
    # Compare update_data with current_record to see if anything actually differs
    has_changes = False
    for key, new_value in update_data.items():
        current_value = current_record.get(key)
        # Normalize values for comparison (handle None, empty strings, whitespace)
        normalized_current = str(current_value).strip() if current_value else ""
        normalized_new = str(new_value).strip() if new_value else ""
        if normalized_current != normalized_new:
            has_changes = True
            break

    if not has_changes:
        logger.info(f"No actual changes detected for SSN {masked_ssn}, skipping charge")
        # Return current record without charging
        current_record['source_table'] = enrich_request.table_name
        email_count = 1 if current_record.get('email') and current_record['email'].strip() else 0
        phone_count = 1 if current_record.get('phone') and current_record['phone'].strip() else 0
        current_record['email_count'] = email_count
        current_record['phone_count'] = phone_count
        return EnrichRecordResponse(
            record=SSNRecord(**current_record),
            updated_fields=[],
            enrichment_cost=0.0,
            enrichment_success=False,
            changes={}
        )

    # Step 6: PHASE 1 - Atomically deduct base cost ($1.00) with row lock and commit
    # Use UPDATE with WHERE condition to ensure atomic check-and-decrement
    # This prevents race conditions where concurrent requests pass the pre-check
    try:
        # Atomic balance decrement: deduct base cost only if sufficient funds available
        # Returns the new balance if successful, no rows if insufficient funds
        stmt = (
            update(User)
            .where(User.id == current_user.id, User.balance >= ENRICHMENT_FAILURE_COST)
            .values(balance=User.balance - ENRICHMENT_FAILURE_COST)
            .returning(User.balance)
        )
        result = await db.execute(stmt)
        new_balance_row = result.fetchone()

        if new_balance_row is None:
            # No row returned = insufficient balance (race condition caught)
            logger.warning(
                f"Atomic balance check failed for user {current_user.id}: "
                f"insufficient funds at transaction time"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient balance. Required: ${ENRICHMENT_FAILURE_COST}"
            )

        new_balance = new_balance_row[0]
        logger.info(
            f"Atomically deducted ${ENRICHMENT_FAILURE_COST} (base cost) from user {current_user.id}. "
            f"New balance: ${new_balance}"
        )

        # Commit the transaction
        await db.commit()

        # Explicit commit completed - base charge is now finalized
        logger.info(f"Postgres base charge committed for user {current_user.id}")

    except HTTPException:
        # Re-raise HTTP exceptions (insufficient balance)
        raise
    except Exception as e:
        logger.error(
            f"Failed to process payment for user {current_user.id}: {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process payment"
        )

    # Step 7: PHASE 2 - Apply update to SQLite; compensate on failure
    # SQLite update happens AFTER Postgres commit, so charge always precedes application

    # Log changes before applying them
    old_values = {k: current_record.get(k) for k in update_data.keys()}
    logger.info(
        f"Enrichment changes for SSN {masked_ssn}: fields={list(update_data.keys())}, "
        f"old={old_values}, new={update_data}"
    )

    try:
        update_result = data_manager.update_record(
            enrich_request.table_name,
            enrich_request.ssn,
            update_data
        )

        if not update_result['success']:
            logger.error(
                f"SQLite update failed for SSN {masked_ssn}: {update_result.get('error')}"
            )
            # Compensate: refund the base charge
            try:
                refund_stmt = (
                    update(User)
                    .where(User.id == current_user.id)
                    .values(balance=User.balance + ENRICHMENT_FAILURE_COST)
                )
                await db.execute(refund_stmt)
                await db.commit()
                logger.info(
                    f"Refunded ${ENRICHMENT_FAILURE_COST} to user {current_user.id} after SQLite failure"
                )
            except Exception as refund_error:
                logger.critical(
                    f"CRITICAL: Failed to refund ${ENRICHMENT_FAILURE_COST} to user {current_user.id} "
                    f"after SQLite failure: {refund_error}",
                    exc_info=True
                )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=update_result.get('error', 'Failed to update record')
            )

        updated_fields = update_result.get('updated_fields', [])
        updated_values = update_result.get('updated_values', {})
        logger.info(
            f"Successfully updated {len(updated_fields)} fields for SSN {masked_ssn}: {updated_fields}"
        )

        # Step 7.5: PHASE 3 - Charge additional $0.50 for successful enrichment
        # SQLite update succeeded, so now charge the success premium
        enrichment_success = True
        final_cost = ENRICHMENT_SUCCESS_COST

        try:
            # Charge additional $0.50 for successful enrichment
            additional_charge_stmt = (
                update(User)
                .where(User.id == current_user.id)
                .values(balance=User.balance - ENRICHMENT_SUCCESS_ADDITIONAL)
                .returning(User.balance)
            )
            result = await db.execute(additional_charge_stmt)
            final_balance = result.fetchone()

            if final_balance is None:
                logger.warning(
                    f"Failed to charge additional ${ENRICHMENT_SUCCESS_ADDITIONAL} to user {current_user.id} "
                    f"(insufficient balance after base charge). Treating as partial success."
                )
                # Keep enrichment_success = True, but use base cost only
                final_cost = ENRICHMENT_FAILURE_COST
            else:
                await db.commit()
                logger.info(
                    f"Charged additional ${ENRICHMENT_SUCCESS_ADDITIONAL} to user {current_user.id}. "
                    f"Total enrichment cost: ${ENRICHMENT_SUCCESS_COST}. New balance: ${final_balance[0]}"
                )
        except Exception as e:
            logger.error(
                f"Error charging additional success fee for user {current_user.id}: {str(e)}",
                exc_info=True
            )
            # Keep enrichment_success = True, but use base cost only
            final_cost = ENRICHMENT_FAILURE_COST

    except HTTPException:
        # Re-raise HTTP exceptions (already compensated above)
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error during SQLite update for SSN {masked_ssn}: {str(e)}",
            exc_info=True
        )
        # Compensate: refund the base charge
        try:
            refund_stmt = (
                update(User)
                .where(User.id == current_user.id)
                .values(balance=User.balance + ENRICHMENT_FAILURE_COST)
            )
            await db.execute(refund_stmt)
            await db.commit()
            logger.info(
                f"Refunded ${ENRICHMENT_FAILURE_COST} to user {current_user.id} after unexpected error"
            )
        except Exception as refund_error:
            logger.critical(
                f"CRITICAL: Failed to refund ${ENRICHMENT_FAILURE_COST} to user {current_user.id} "
                f"after unexpected error: {refund_error}",
                exc_info=True
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update record"
        )

    # Step 8: Build response from current record + updated values (no second DB query needed)
    updated_record = {**current_record, **updated_values}

    # Add source_table field
    updated_record['source_table'] = enrich_request.table_name

    # Count email and phone
    email_count = 1 if updated_record.get('email') and updated_record['email'].strip() else 0
    phone_count = 1 if updated_record.get('phone') and updated_record['phone'].strip() else 0

    # Check if counts changed
    old_email_count = 1 if current_record.get('email') and current_record['email'].strip() else 0
    old_phone_count = 1 if current_record.get('phone') and current_record['phone'].strip() else 0

    updated_record['email_count'] = email_count
    updated_record['phone_count'] = phone_count

    # Build changes dict: include updated_values plus changed counts
    changes = {**updated_values}
    if email_count != old_email_count:
        changes['email_count'] = email_count
    if phone_count != old_phone_count:
        changes['phone_count'] = phone_count

    # Keep actual email and phone values (user paid for enrichment)
    # No need to modify - they're already in updated_record

    logger.info(f"Enrichment completed successfully for SSN {masked_ssn}")

    return EnrichRecordResponse(
        record=SSNRecord(**updated_record),
        updated_fields=updated_fields,
        enrichment_cost=float(final_cost),
        enrichment_success=enrichment_success,
        changes=changes
    )


@router.post("/enrich-by-name-zip", response_model=EnrichRecordResponse)
# @limiter.limit("10/hour")  # Commented out for testing
async def enrich_by_name_zip(
    request: Request,
    response: Response,
    enrich_request: EnrichByNameZipRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Third enrichment method: Search and enrich record by name and ZIP code.

    This endpoint searches for a person using their first name, last name, and ZIP code,
    then enriches the first matching record in the specified table with the found data.

    Cost: $3.00 per successful enrichment
    Only updates safe fields: dob, address, city, state, zip, phone, email, middlename
    """
    # Step 1: Check user balance
    if current_user.balance < ENRICHMENT_FAILURE_COST:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient balance. Required: ${ENRICHMENT_FAILURE_COST}, Available: ${current_user.balance}"
        )

    # Step 2: Search for records with matching name in the specified table
    dm = DataManager(SQLITE_PATH)

    # Search for records with matching first and last name
    search_conditions = {
        'firstname': enrich_request.firstname,
        'lastname': enrich_request.lastname
    }

    records = dm.search_records(enrich_request.table_name, **search_conditions)

    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No records found with name {enrich_request.firstname} {enrich_request.lastname} in table {enrich_request.table_name}"
        )

    # Use the first matching record
    current_record = records[0]
    record_ssn = current_record.get('ssn')

    if not record_ssn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Record does not have SSN field"
        )

    # Mask SSN for logging
    masked_ssn = record_ssn[:3] + '-XX-' + record_ssn[-4:] if len(record_ssn) >= 7 else 'XXX-XX-XXXX'
    logger.info(f"Processing enrichment by name+zip for SSN {masked_ssn} from table {enrich_request.table_name}")

    # Step 3: Call external API to search by name and ZIP
    try:
        async with create_searchbug_client() as sb_client:
            # Use the search_person_by_name_zip method
            enrichment_data = await sb_client.search_person_by_name_zip(
                firstname=enrich_request.firstname,
                lastname=enrich_request.lastname,
                zipcode=enrich_request.zip
            )

            if not enrichment_data:
                logger.info(f"No enrichment data found for {enrich_request.firstname} {enrich_request.lastname} in ZIP {enrich_request.zip}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No enrichment data found for the provided name and ZIP code"
                )

    except SearchbugRateLimitError:
        logger.error("External API rate limit exceeded")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
    except SearchbugNotFoundError:
        logger.info(f"No data found for {enrich_request.firstname} {enrich_request.lastname} in ZIP {enrich_request.zip}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No enrichment data found for the provided name and ZIP code"
        )
    except SearchbugAPIError as e:
        logger.error(f"External API error: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="External enrichment service error"
        )
    except Exception as e:
        logger.error(f"Error during external API call: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch enrichment data"
        )

    # Step 4: Process and validate enrichment data
    # Extract and map fields from external API response
    updated_values = {}
    updated_fields = []

    # Extract primary address
    if enrichment_data.get('addresses') and len(enrichment_data['addresses']) > 0:
        address_info = enrichment_data['addresses'][0]
        if address_info.get('full_street'):
            updated_values['address'] = address_info['full_street']
            updated_fields.append('address')
        if address_info.get('city'):
            updated_values['city'] = address_info['city']
            updated_fields.append('city')
        if address_info.get('state'):
            updated_values['state'] = address_info['state']
            updated_fields.append('state')
        if address_info.get('zip_code'):
            updated_values['zip'] = address_info['zip_code']
            updated_fields.append('zip')

    # Extract primary phone
    if enrichment_data.get('phones') and len(enrichment_data['phones']) > 0:
        phone_info = enrichment_data['phones'][0]
        phone_number = phone_info.get('phone_number', '')
        if phone_number:
            # Format phone as (XXX) XXX-XXXX
            phone_clean = phone_number.replace('-', '').replace('(', '').replace(')', '').replace(' ', '')
            if len(phone_clean) == 10:
                formatted_phone = f"({phone_clean[:3]}) {phone_clean[3:6]}-{phone_clean[6:]}"
                updated_values['phone'] = formatted_phone
                updated_fields.append('phone')

    # Extract email
    if enrichment_data.get('emails') and len(enrichment_data['emails']) > 0:
        email = enrichment_data['emails'][0]
        if email:
            updated_values['email'] = email
            updated_fields.append('email')

    # Extract DOB
    if enrichment_data.get('dob'):
        updated_values['dob'] = str(enrichment_data['dob'])
        updated_fields.append('dob')

    # Extract middle name
    if enrichment_data.get('names') and len(enrichment_data['names']) > 0:
        middle_name = enrichment_data['names'][0].get('middle_name')
        if middle_name:
            updated_values['middlename'] = middle_name
            updated_fields.append('middlename')

    # Step 5: Check if there are any actual updates
    actual_updates = {}
    for field, new_value in updated_values.items():
        if field in SAFE_UPDATE_FIELDS:
            current_value = current_record.get(field, '')
            # Compare normalized values
            if str(current_value).strip().lower() != str(new_value).strip().lower():
                actual_updates[field] = new_value

    if not actual_updates:
        logger.info(f"No new data to update for SSN {masked_ssn}")
        # Return current record without charging
        current_record['source_table'] = enrich_request.table_name
        return EnrichRecordResponse(
            record=SSNRecord(**current_record),
            updated_fields=[],
            enrichment_cost=0.0,
            enrichment_success=False,
            changes={}
        )

    # Step 6: Perform transactional update - charge user base cost first
    try:
        # Atomic balance deduction (base cost)
        result = await db.execute(
            update(User)
            .where(User.id == current_user.id)
            .where(User.balance >= ENRICHMENT_FAILURE_COST)
            .values(balance=User.balance - ENRICHMENT_FAILURE_COST)
            .returning(User.balance)
        )

        new_balance = result.scalar()
        if new_balance is None:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient balance or concurrent modification"
            )

        await db.commit()
        logger.info(f"Charged user {current_user.id} ${ENRICHMENT_FAILURE_COST} (base cost) for enrichment. New balance: ${new_balance}")

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to charge user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process payment"
        )

    # Step 7: Update the SQLite record
    enrichment_success = False
    final_cost = ENRICHMENT_FAILURE_COST

    try:
        # Update only the safe fields that changed
        dm.update_record(
            table_name=enrich_request.table_name,
            ssn=record_ssn,
            **actual_updates
        )
        logger.info(f"Successfully updated {len(actual_updates)} fields for SSN {masked_ssn}")

        # Step 7.5: Charge additional $0.50 for successful enrichment
        enrichment_success = True
        final_cost = ENRICHMENT_SUCCESS_COST

        try:
            # Charge additional $0.50 for successful enrichment
            additional_charge_result = await db.execute(
                update(User)
                .where(User.id == current_user.id)
                .values(balance=User.balance - ENRICHMENT_SUCCESS_ADDITIONAL)
                .returning(User.balance)
            )
            final_balance = additional_charge_result.scalar()

            if final_balance is None:
                logger.warning(
                    f"Failed to charge additional ${ENRICHMENT_SUCCESS_ADDITIONAL} to user {current_user.id}. "
                    f"Treating as partial success."
                )
                final_cost = ENRICHMENT_FAILURE_COST
            else:
                await db.commit()
                logger.info(
                    f"Charged additional ${ENRICHMENT_SUCCESS_ADDITIONAL} to user {current_user.id}. "
                    f"Total cost: ${ENRICHMENT_SUCCESS_COST}. New balance: ${final_balance}"
                )
        except Exception as e:
            logger.error(f"Error charging additional success fee: {str(e)}", exc_info=True)
            final_cost = ENRICHMENT_FAILURE_COST

    except Exception as e:
        # Compensation: refund the base charge
        logger.error(f"Failed to update SQLite record: {e}. Initiating refund.")

        try:
            await db.execute(
                update(User)
                .where(User.id == current_user.id)
                .values(balance=User.balance + ENRICHMENT_FAILURE_COST)
            )
            await db.commit()
            logger.info(f"Refunded ${ENRICHMENT_FAILURE_COST} to user {current_user.id}")
        except Exception as refund_error:
            logger.critical(f"Failed to refund user {current_user.id}: {refund_error}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update record"
        )

    # Step 8: Build response
    updated_record = {**current_record, **actual_updates}
    updated_record['source_table'] = enrich_request.table_name

    # Update email and phone counts
    email_count = 1 if updated_record.get('email') and updated_record['email'].strip() else 0
    phone_count = 1 if updated_record.get('phone') and updated_record['phone'].strip() else 0

    old_email_count = 1 if current_record.get('email') and current_record['email'].strip() else 0
    old_phone_count = 1 if current_record.get('phone') and current_record['phone'].strip() else 0

    updated_record['email_count'] = email_count
    updated_record['phone_count'] = phone_count

    # Build changes dict
    changes = {**actual_updates}
    if email_count != old_email_count:
        changes['email_count'] = email_count
    if phone_count != old_phone_count:
        changes['phone_count'] = phone_count

    logger.info(f"Enrichment by name+zip completed successfully for SSN {masked_ssn}")

    return EnrichRecordResponse(
        record=SSNRecord(**updated_record),
        updated_fields=list(actual_updates.keys()),
        enrichment_cost=float(final_cost),
        enrichment_success=enrichment_success,
        changes=changes
    )
