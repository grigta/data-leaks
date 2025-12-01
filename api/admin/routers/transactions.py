"""
Transactions management router for Admin API.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from typing import Optional
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime

from api.common.database import get_postgres_session
from api.admin.dependencies import get_current_admin_user
from api.common.models_postgres import User, Transaction, TransactionStatus, PaymentMethod

router = APIRouter(tags=["Admin Transactions"])


# Pydantic models
class TransactionResponse(BaseModel):
    """Transaction response model."""
    id: str
    user_id: str
    username: str
    amount: Decimal
    payment_method: str
    status: str
    payment_provider: Optional[str] = None
    external_transaction_id: Optional[str] = None
    currency: Optional[str] = None
    network: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    """Transaction list response."""
    transactions: list[TransactionResponse]
    total_count: int
    page: int
    page_size: int


@router.get("/", response_model=TransactionListResponse)
async def get_transactions(
    status_filter: Optional[str] = Query(None, description="Filter by status (pending, paid, expired, failed)"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get all transactions with optional filtering.

    Admin only endpoint for viewing all transactions in the system.
    """
    # Build query
    query = (
        select(Transaction, User.username)
        .join(User, Transaction.user_id == User.id)
    )

    # Apply status filter if provided
    if status_filter:
        try:
            status = TransactionStatus(status_filter)
            query = query.where(Transaction.status == status)
        except ValueError:
            pass  # Invalid status, ignore filter

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total_count = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(desc(Transaction.created_at)).limit(limit).offset(offset)

    # Execute query
    result = await session.execute(query)
    rows = result.all()

    # Format response
    transactions = []
    for transaction, username in rows:
        transactions.append(TransactionResponse(
            id=str(transaction.id),
            user_id=str(transaction.user_id),
            username=username,
            amount=transaction.amount,
            payment_method=transaction.payment_method.value,
            status=transaction.status.value,
            payment_provider=transaction.payment_provider,
            external_transaction_id=transaction.external_transaction_id,
            currency=transaction.currency,
            network=transaction.network,
            created_at=transaction.created_at,
            updated_at=transaction.updated_at
        ))

    return TransactionListResponse(
        transactions=transactions,
        total_count=total_count,
        page=offset // limit + 1 if limit > 0 else 1,
        page_size=limit
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: str,
    session: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get transaction by ID.

    Admin only endpoint for viewing transaction details.
    """
    from uuid import UUID

    query = (
        select(Transaction, User.username)
        .join(User, Transaction.user_id == User.id)
        .where(Transaction.id == UUID(transaction_id))
    )

    result = await session.execute(query)
    row = result.first()

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Transaction not found")

    transaction, username = row

    return TransactionResponse(
        id=str(transaction.id),
        user_id=str(transaction.user_id),
        username=username,
        amount=transaction.amount,
        payment_method=transaction.payment_method.value,
        status=transaction.status.value,
        payment_provider=transaction.payment_provider,
        external_transaction_id=transaction.external_transaction_id,
        currency=transaction.currency,
        network=transaction.network,
        created_at=transaction.created_at,
        updated_at=transaction.updated_at
    )
