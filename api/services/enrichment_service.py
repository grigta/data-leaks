"""
Unified enrichment service for SSN record enrichment.

Provides centralized enrichment logic with transactional guarantees:
- Atomic balance deduction in PostgreSQL
- SQLite record updates
- Automatic compensation on failures
"""
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from api.common.models_postgres import User
from database.data_manager import DataManager
from api.common.searchbug_client import (
    create_searchbug_client,
    SearchbugAPIError,
    SearchbugRateLimitError,
)

logger = logging.getLogger(__name__)

# Enrichment costs (two-tier pricing)
ENRICHMENT_FAILURE_COST = Decimal('3.00')  # Base cost for failed enrichment
ENRICHMENT_SUCCESS_COST = Decimal('3.50')  # Total cost for successful enrichment
ENRICHMENT_SUCCESS_ADDITIONAL = Decimal('0.50')  # Additional charge for success

# Safe fields that can be updated during enrichment
SAFE_UPDATE_FIELDS = {'dob', 'address', 'city', 'state', 'zip', 'phone', 'email', 'middlename'}


class EnrichmentResult:
    """Result of an enrichment operation."""

    def __init__(
        self,
        success: bool,
        cost: Decimal,
        updated_fields: Optional[list] = None,
        timestamp: Optional[str] = None,
        error: Optional[str] = None
    ):
        self.success = success
        self.cost = cost
        self.updated_fields = updated_fields or []
        # Ensure timestamp is always a valid ISO format string with UTC timezone
        self.timestamp = timestamp if timestamp else datetime.now(timezone.utc).isoformat()
        self.error = error


async def perform_enrichment(
    user: User,
    table_name: str,
    ssn: str,
    db_session: AsyncSession,
    data_manager: DataManager
) -> EnrichmentResult:
    """
    Perform atomic enrichment operation with transactional guarantees.

    Process:
    1. Check user balance
    2. Fetch current record from SQLite
    3. Call SearchBug API for enrichment
    4. Atomically deduct base cost ($3.00) from PostgreSQL
    5. Update SQLite record
    6. On success: charge additional $0.50
    7. On failure: refund base cost

    Args:
        user: Current authenticated user
        table_name: SQLite table name (ssn_1 or ssn_2)
        ssn: SSN to enrich
        db_session: PostgreSQL async session
        data_manager: SQLite data manager

    Returns:
        EnrichmentResult with success status, cost, and metadata
    """
    enrichment_timestamp = datetime.now(timezone.utc).isoformat()

    # Step 1: Check balance
    if user.balance < ENRICHMENT_FAILURE_COST:
        logger.warning(f"Insufficient balance for enrichment for user {user.id}")
        return EnrichmentResult(
            success=False,
            cost=Decimal('0.00'),
            timestamp=enrichment_timestamp,
            error=f"Insufficient balance. Required: ${ENRICHMENT_FAILURE_COST}, Available: ${user.balance}"
        )

    # Step 2: Fetch current record
    current_record = data_manager.get_record(table_name, ssn)
    if current_record is None:
        return EnrichmentResult(
            success=False,
            cost=Decimal('0.00'),
            timestamp=enrichment_timestamp,
            error=f"SSN record not found in {table_name}"
        )

    # Step 3: Call SearchBug API
    try:
        async with create_searchbug_client() as sb_client:
            searchbug_record = {
                'firstname': current_record.get('firstname'),
                'lastname': current_record.get('lastname'),
                'middlename': current_record.get('middlename'),
                'city': current_record.get('city'),
                'state': current_record.get('state'),
                'phone': current_record.get('phone'),
                'dob': current_record.get('dob'),
                'email': current_record.get('email'),
                'street': current_record.get('address'),
                'zipcode': current_record.get('zip')
            }

            enriched_data = await sb_client.enrich_person_data(searchbug_record)

            if not enriched_data:
                logger.info(f"No enrichment data found for SSN")
                return EnrichmentResult(
                    success=False,
                    cost=Decimal('0.00'),
                    timestamp=enrichment_timestamp,
                    error="No matching data found"
                )

            # Map enriched data back
            update_data = {}
            if 'street' in enriched_data and enriched_data['street']:
                update_data['address'] = enriched_data['street']
            if 'zipcode' in enriched_data and enriched_data['zipcode']:
                update_data['zip'] = enriched_data['zipcode']

            for field in ['firstname', 'lastname', 'middlename', 'city', 'state', 'phone', 'dob', 'email']:
                if field in enriched_data and enriched_data[field]:
                    update_data[field] = enriched_data[field]

            # Filter to safe fields
            update_data = {k: v for k, v in update_data.items() if k in SAFE_UPDATE_FIELDS}

    except (SearchbugAPIError, SearchbugRateLimitError) as e:
        logger.warning(f"External API error: {str(e)}")
        return EnrichmentResult(
            success=False,
            cost=Decimal('0.00'),
            timestamp=enrichment_timestamp,
            error=f"Enrichment service error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Enrichment error: {str(e)}", exc_info=True)
        return EnrichmentResult(
            success=False,
            cost=Decimal('0.00'),
            timestamp=enrichment_timestamp,
            error=f"Unexpected error during enrichment: {str(e)}"
        )

    # Step 4: Atomically deduct base cost (charged for successful SearchBug response)
    try:
        stmt = (
            update(User)
            .where(User.id == user.id, User.balance >= ENRICHMENT_FAILURE_COST)
            .values(balance=User.balance - ENRICHMENT_FAILURE_COST)
            .returning(User.balance)
        )
        result = await db_session.execute(stmt)
        new_balance_row = result.fetchone()

        if new_balance_row is None:
            logger.warning(f"Atomic balance check failed for user {user.id}")
            return EnrichmentResult(
                success=False,
                cost=Decimal('0.00'),
                timestamp=enrichment_timestamp,
                error=f"Insufficient balance at transaction time"
            )

        await db_session.commit()
        logger.info(f"Deducted ${ENRICHMENT_FAILURE_COST} from user {user.id}")

    except Exception as e:
        await db_session.rollback()
        logger.error(f"Failed to process payment for user {user.id}: {str(e)}", exc_info=True)
        return EnrichmentResult(
            success=False,
            cost=Decimal('0.00'),
            timestamp=enrichment_timestamp,
            error="Failed to process payment"
        )

    # Step 5: Check for changes in update_data
    has_changes = False
    for key, new_value in update_data.items():
        current_value = current_record.get(key)
        normalized_current = str(current_value).strip() if current_value else ""
        normalized_new = str(new_value).strip() if new_value else ""
        if normalized_current != normalized_new:
            has_changes = True
            break

    # If no changes, return with base cost charged
    if not has_changes:
        logger.info(f"No actual changes detected for SSN, base cost charged: ${ENRICHMENT_FAILURE_COST}")
        return EnrichmentResult(
            success=False,
            cost=ENRICHMENT_FAILURE_COST,
            timestamp=enrichment_timestamp
        )

    # Step 6: Update SQLite record (only if there are changes)
    enrichment_cost = ENRICHMENT_FAILURE_COST
    try:
        update_result = data_manager.update_record(table_name, ssn, update_data)

        if not update_result['success']:
            logger.error(f"SQLite update failed: {update_result.get('error')}")

            # Compensate - refund base cost
            try:
                refund_stmt = (
                    update(User)
                    .where(User.id == user.id)
                    .values(balance=User.balance + ENRICHMENT_FAILURE_COST)
                )
                await db_session.execute(refund_stmt)
                await db_session.commit()
                logger.info(f"Refunded ${ENRICHMENT_FAILURE_COST} to user {user.id}")
            except Exception as refund_error:
                logger.critical(
                    f"CRITICAL: Failed to refund ${ENRICHMENT_FAILURE_COST} to user {user.id}: {refund_error}",
                    exc_info=True
                )

            return EnrichmentResult(
                success=False,
                cost=Decimal('0.00'),
                timestamp=enrichment_timestamp,
                error=update_result.get('error', 'Failed to update record')
            )

        updated_fields = update_result.get('updated_fields', [])
        logger.info(f"Successfully updated {len(updated_fields)} fields: {updated_fields}")

        # Step 7: Charge additional success fee
        try:
            additional_stmt = (
                update(User)
                .where(User.id == user.id)
                .values(balance=User.balance - ENRICHMENT_SUCCESS_ADDITIONAL)
                .returning(User.balance)
            )
            additional_result = await db_session.execute(additional_stmt)
            if additional_result.fetchone():
                await db_session.commit()
                enrichment_cost = ENRICHMENT_SUCCESS_COST
                logger.info(f"Charged additional ${ENRICHMENT_SUCCESS_ADDITIONAL}, total: ${ENRICHMENT_SUCCESS_COST}")
            else:
                logger.warning(f"Failed to charge additional fee (insufficient balance)")
        except Exception as e:
            logger.error(f"Error charging additional success fee: {str(e)}", exc_info=True)

        return EnrichmentResult(
            success=True,
            cost=enrichment_cost,
            updated_fields=updated_fields,
            timestamp=enrichment_timestamp
        )

    except Exception as e:
        logger.error(f"Unexpected error during SQLite update: {str(e)}", exc_info=True)

        # Compensate - refund base cost
        try:
            refund_stmt = (
                update(User)
                .where(User.id == user.id)
                .values(balance=User.balance + ENRICHMENT_FAILURE_COST)
            )
            await db_session.execute(refund_stmt)
            await db_session.commit()
            logger.info(f"Refunded ${ENRICHMENT_FAILURE_COST} to user {user.id}")
        except Exception as refund_error:
            logger.critical(
                f"CRITICAL: Failed to refund ${ENRICHMENT_FAILURE_COST} to user {user.id}: {refund_error}",
                exc_info=True
            )

        return EnrichmentResult(
            success=False,
            cost=Decimal('0.00'),
            timestamp=enrichment_timestamp,
            error="Failed to update record"
        )
