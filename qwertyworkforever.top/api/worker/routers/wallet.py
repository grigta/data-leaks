"""
Worker wallet and withdraw management router.
"""
import os
import logging
from decimal import Decimal
from typing import Optional, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from api.common.database import get_postgres_session as get_db
from api.common.models_postgres import User, ManualSSNTicket, TicketStatus, WorkerInvoice, InvoiceStatus
from api.common.pricing import MANUAL_SSN_COST
from api.worker.dependencies import get_current_worker_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Worker Wallet"])

ADMIN_API_URL = os.getenv("ADMIN_API_URL", "http://admin_api:8002")


# --- Pydantic models ---

class WalletResponse(BaseModel):
    wallet_address: Optional[str] = None
    wallet_network: Optional[str] = None
    total_earned: str
    total_paid: str
    available_balance: str


class UpdateWalletRequest(BaseModel):
    wallet_address: str
    wallet_network: str

    @field_validator("wallet_address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10 or len(v) > 255:
            raise ValueError("Wallet address must be between 10 and 255 characters")
        return v

    @field_validator("wallet_network")
    @classmethod
    def validate_network(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("erc20", "trc20"):
            raise ValueError("Network must be 'erc20' or 'trc20'")
        return v


class WithdrawRequest(BaseModel):
    amount: Decimal

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be positive")
        return v


class InvoiceResponse(BaseModel):
    id: str
    amount: str
    wallet_address: str
    wallet_network: str
    status: str
    paid_at: Optional[str] = None
    created_at: str


class InvoiceListResponse(BaseModel):
    invoices: List[InvoiceResponse]
    total_count: int


# --- Helper ---

async def _calc_worker_balance(db: AsyncSession, worker_id) -> tuple[Decimal, Decimal, Decimal]:
    """Calculate worker's total_earned, total_paid, available_balance."""
    # Total completed tickets
    result = await db.execute(
        select(func.count()).select_from(ManualSSNTicket).where(
            ManualSSNTicket.worker_id == worker_id,
            ManualSSNTicket.status == TicketStatus.completed,
        )
    )
    total_completed = result.scalar_one()
    total_earned = Decimal(total_completed) * MANUAL_SSN_COST

    # Total paid invoices
    result = await db.execute(
        select(func.coalesce(func.sum(WorkerInvoice.amount), Decimal("0"))).where(
            WorkerInvoice.worker_id == worker_id,
            WorkerInvoice.status == InvoiceStatus.paid,
        )
    )
    total_paid = result.scalar_one()

    # Total pending invoices (reserved amount)
    result = await db.execute(
        select(func.coalesce(func.sum(WorkerInvoice.amount), Decimal("0"))).where(
            WorkerInvoice.worker_id == worker_id,
            WorkerInvoice.status == InvoiceStatus.pending,
        )
    )
    total_pending = result.scalar_one()

    available_balance = total_earned - total_paid - total_pending
    return total_earned, total_paid, available_balance


# --- Endpoints ---

@router.get("/me", response_model=WalletResponse)
async def get_wallet(
    current_user: User = Depends(get_current_worker_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current worker wallet info and balance."""
    total_earned, total_paid, available_balance = await _calc_worker_balance(db, current_user.id)

    return WalletResponse(
        wallet_address=current_user.wallet_address,
        wallet_network=current_user.wallet_network,
        total_earned=f"{total_earned:.2f}",
        total_paid=f"{total_paid:.2f}",
        available_balance=f"{available_balance:.2f}",
    )


@router.put("/me", response_model=WalletResponse)
async def update_wallet(
    body: UpdateWalletRequest,
    current_user: User = Depends(get_current_worker_user),
    db: AsyncSession = Depends(get_db),
):
    """Update worker wallet address and network."""
    current_user.wallet_address = body.wallet_address
    current_user.wallet_network = body.wallet_network
    await db.commit()
    await db.refresh(current_user)

    total_earned, total_paid, available_balance = await _calc_worker_balance(db, current_user.id)

    logger.info(f"Worker {current_user.username} updated wallet: {body.wallet_network} {body.wallet_address[:8]}...")
    return WalletResponse(
        wallet_address=current_user.wallet_address,
        wallet_network=current_user.wallet_network,
        total_earned=f"{total_earned:.2f}",
        total_paid=f"{total_paid:.2f}",
        available_balance=f"{available_balance:.2f}",
    )


@router.post("/withdraw", response_model=InvoiceResponse)
async def create_withdraw(
    body: WithdrawRequest,
    current_user: User = Depends(get_current_worker_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a withdraw request (invoice)."""
    if not current_user.wallet_address or not current_user.wallet_network:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set wallet address and network first",
        )

    total_earned, total_paid, available_balance = await _calc_worker_balance(db, current_user.id)

    if body.amount > available_balance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Available: ${available_balance:.2f}",
        )

    invoice = WorkerInvoice(
        worker_id=current_user.id,
        amount=body.amount,
        wallet_address=current_user.wallet_address,
        wallet_network=current_user.wallet_network,
        status=InvoiceStatus.pending,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)

    logger.info(f"Worker {current_user.username} created withdraw request: ${body.amount:.2f} to {current_user.wallet_network}")

    # Notify admin panel
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{ADMIN_API_URL}/api/admin/internal/notify-invoice-created",
                json={
                    "invoice_data": {
                        "id": str(invoice.id),
                        "worker_id": str(current_user.id),
                        "worker_username": current_user.username,
                        "amount": f"{invoice.amount:.2f}",
                        "wallet_address": invoice.wallet_address,
                        "wallet_network": invoice.wallet_network,
                        "created_at": invoice.created_at.isoformat(),
                    }
                },
            )
    except Exception as e:
        logger.warning(f"Failed to notify admin about new invoice: {e}")

    return InvoiceResponse(
        id=str(invoice.id),
        amount=f"{invoice.amount:.2f}",
        wallet_address=invoice.wallet_address,
        wallet_network=invoice.wallet_network,
        status=invoice.status.value,
        paid_at=None,
        created_at=invoice.created_at.isoformat(),
    )


@router.get("/invoices", response_model=InvoiceListResponse)
async def get_invoices(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_worker_user),
    db: AsyncSession = Depends(get_db),
):
    """Get worker's invoice history."""
    query = (
        select(WorkerInvoice)
        .where(WorkerInvoice.worker_id == current_user.id)
        .order_by(WorkerInvoice.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    invoices = result.scalars().all()

    count_result = await db.execute(
        select(func.count()).select_from(WorkerInvoice).where(
            WorkerInvoice.worker_id == current_user.id
        )
    )
    total = count_result.scalar_one()

    return InvoiceListResponse(
        invoices=[
            InvoiceResponse(
                id=str(inv.id),
                amount=f"{inv.amount:.2f}",
                wallet_address=inv.wallet_address,
                wallet_network=inv.wallet_network,
                status=inv.status.value,
                paid_at=inv.paid_at.isoformat() if inv.paid_at else None,
                created_at=inv.created_at.isoformat(),
            )
            for inv in invoices
        ],
        total_count=total,
    )
