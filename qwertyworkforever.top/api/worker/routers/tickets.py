"""
Worker tickets router.
Handles ticket claiming and processing for workers.
"""
import logging
import os
import re
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, update, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.common.database import get_postgres_session
from api.common.models_postgres import ManualSSNTicket, TicketStatus, User, Order, OrderStatus, OrderType, TestSearchHistory, WorkerShift
from api.worker.dependencies import get_current_worker_user
from api.worker.websocket import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Worker Tickets"])

ADMIN_API_URL = os.getenv("ADMIN_API_URL", "http://admin_api:8002")
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://public_api:8000")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


async def _notify_ticket_update(ticket: ManualSSNTicket, event: str):
    """Notify Admin API and Public API about ticket changes via internal endpoints."""
    ticket_data = {
        "id": str(ticket.id),
        "user_id": str(ticket.user_id),
        "firstname": ticket.firstname,
        "lastname": ticket.lastname,
        "address": ticket.address,
        "status": ticket.status.value,
        "worker_id": str(ticket.worker_id) if ticket.worker_id else None,
        "response_data": ticket.response_data,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
    }

    internal_headers = {"X-Internal-Api-Key": INTERNAL_API_KEY}
    async with httpx.AsyncClient(timeout=5.0) as client:
        # Notify Admin API (internal Docker URL, no /api/admin/ prefix)
        try:
            await client.post(
                f"{ADMIN_API_URL}/internal/notify-ticket-updated",
                json={"ticket_data": ticket_data},
                headers=internal_headers
            )
            logger.info(f"Notified admin API: {event} for ticket {ticket.id}")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed to notify admin API about {event}: {e}")

        # Notify Public API (user WebSocket, internal Docker URL, no /api/public/ prefix)
        try:
            if event == "ticket_completed":
                public_endpoint = "/internal/notify-ticket-completed"
            else:
                public_endpoint = "/internal/notify-ticket-updated"
            await client.post(
                f"{PUBLIC_API_URL}{public_endpoint}",
                json={"user_id": str(ticket.user_id), "ticket_data": ticket_data},
                headers=internal_headers
            )
            logger.info(f"Notified public API: {event} for user {ticket.user_id}")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed to notify public API about {event}: {e}")


async def _increment_shift_counter(db: AsyncSession, worker_id, field: str):
    """Increment tickets_completed or tickets_rejected on the worker's current open shift."""
    try:
        from sqlalchemy import desc
        result = await db.execute(
            select(WorkerShift).where(
                WorkerShift.worker_id == worker_id,
                WorkerShift.ended_at.is_(None),
            ).order_by(desc(WorkerShift.started_at)).limit(1)
        )
        shift = result.scalar_one_or_none()
        if shift:
            setattr(shift, field, getattr(shift, field) + 1)
            await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to increment shift counter: {e}")


class TicketResponse(BaseModel):
    """Response model for ticket data"""
    id: str
    user_id: str
    username: str
    firstname: str
    lastname: str
    address: str
    status: str
    worker_id: Optional[str] = None
    worker_username: Optional[str] = None
    response_data: Optional[dict] = None
    created_at: str
    updated_at: str

    @classmethod
    def from_ticket(cls, ticket: ManualSSNTicket) -> "TicketResponse":
        return cls(
            id=str(ticket.id),
            user_id=str(ticket.user_id),
            username=ticket.user.username if ticket.user else "Unknown",
            firstname=ticket.firstname,
            lastname=ticket.lastname,
            address=ticket.address,
            status=ticket.status.value,
            worker_id=str(ticket.worker_id) if ticket.worker_id else None,
            worker_username=ticket.worker.username if ticket.worker else None,
            response_data=ticket.response_data,
            created_at=ticket.created_at.isoformat(),
            updated_at=ticket.updated_at.isoformat()
        )


class TicketListResponse(BaseModel):
    tickets: List[TicketResponse]
    total_count: int


class HistoryStatsResponse(BaseModel):
    total: int
    completed: int
    rejected: int
    success_rate: float
    avg_time: str
    payout: str


class HistoryResponse(BaseModel):
    tickets: List[TicketResponse]
    total_count: int
    stats: HistoryStatsResponse


class UpdateTicketRequest(BaseModel):
    status: Optional[str] = None
    response_data: Optional[dict] = None


class QuickRespondRequest(BaseModel):
    text: str


def parse_worker_response(text: str) -> dict:
    """Parse SSN and DOB from a single text line."""
    result = {'ssn': None, 'dob': None}
    text = text.strip()

    # SSN: 3-2-4 digits with optional dash/space separators
    ssn_match = re.search(r'(\d{3})[-\s]?(\d{2})[-\s]?(\d{4})', text)
    if ssn_match:
        result['ssn'] = f"{ssn_match.group(1)}-{ssn_match.group(2)}-{ssn_match.group(3)}"
        text = text[:ssn_match.start()] + ' ' + text[ssn_match.end():]

    # DOB: MM/DD/YYYY or MM-DD-YYYY
    dob_match = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text)
    if dob_match:
        m, d, y = dob_match.group(1), dob_match.group(2), dob_match.group(3)
        result['dob'] = f"{m.zfill(2)}/{d.zfill(2)}/{y}"
    else:
        # YYYY-MM-DD
        dob_match = re.search(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', text)
        if dob_match:
            y, m, d = dob_match.group(1), dob_match.group(2), dob_match.group(3)
            result['dob'] = f"{m.zfill(2)}/{d.zfill(2)}/{y}"
        else:
            # 8 consecutive digits: YYYYMMDD or MMDDYYYY
            dob_match = re.search(r'\b(\d{8})\b', text)
            if dob_match:
                d8 = dob_match.group(1)
                if int(d8[:4]) > 1900:
                    result['dob'] = f"{d8[4:6]}/{d8[6:8]}/{d8[:4]}"
                else:
                    result['dob'] = f"{d8[:2]}/{d8[2:4]}/{d8[4:8]}"

    return result


@router.get("/unassigned", response_model=TicketListResponse)
async def get_unassigned_tickets(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_worker_user)
):
    """Get all unassigned pending tickets."""
    try:
        query = select(ManualSSNTicket).options(
            selectinload(ManualSSNTicket.user),
            selectinload(ManualSSNTicket.worker)
        ).where(
            ManualSSNTicket.worker_id.is_(None),
            ManualSSNTicket.status == TicketStatus.pending
        ).order_by(ManualSSNTicket.created_at.desc())

        query = query.limit(limit).offset(offset)
        result = await db.execute(query)
        tickets = result.scalars().all()

        count_query = select(func.count()).select_from(ManualSSNTicket).where(
            ManualSSNTicket.worker_id.is_(None),
            ManualSSNTicket.status == TicketStatus.pending
        )
        total_result = await db.execute(count_query)
        total_count = total_result.scalar_one()

        return TicketListResponse(
            tickets=[TicketResponse.from_ticket(t) for t in tickets],
            total_count=total_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting unassigned tickets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get unassigned tickets"
        )


@router.get("/my", response_model=TicketListResponse)
async def get_my_tickets(
    status_filter: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_worker_user)
):
    """Get active tickets: assigned to current worker OR unassigned pending."""
    try:
        # Show worker's own tickets + all unassigned pending tickets
        base_filter = or_(
            ManualSSNTicket.worker_id == current_user.id,
            and_(
                ManualSSNTicket.worker_id.is_(None),
                ManualSSNTicket.status == TicketStatus.pending
            )
        )

        query = select(ManualSSNTicket).options(
            selectinload(ManualSSNTicket.user),
            selectinload(ManualSSNTicket.worker)
        ).where(base_filter)

        # Only show active statuses (pending/processing), not completed/rejected
        query = query.where(ManualSSNTicket.status.in_([TicketStatus.pending, TicketStatus.processing]))

        if status_filter:
            try:
                status_enum = TicketStatus(status_filter)
                query = query.where(ManualSSNTicket.status == status_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status. Must be one of: {[s.value for s in TicketStatus]}"
                )

        count_query = select(func.count()).select_from(ManualSSNTicket).where(base_filter).where(
            ManualSSNTicket.status.in_([TicketStatus.pending, TicketStatus.processing])
        )
        if status_filter:
            count_query = count_query.where(ManualSSNTicket.status == TicketStatus(status_filter))

        total_result = await db.execute(count_query)
        total_count = total_result.scalar_one()

        query = query.order_by(ManualSSNTicket.created_at.desc())
        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        tickets = result.scalars().all()

        return TicketListResponse(
            tickets=[TicketResponse.from_ticket(t) for t in tickets],
            total_count=total_count
        )

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting worker tickets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get tickets"
        )


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    period: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_worker_user)
):
    """Get completed/rejected tickets for current worker with stats.
    period: '24h', '7d', '30d' or None (all time)."""
    try:
        done_filter = and_(
            ManualSSNTicket.worker_id == current_user.id,
            ManualSSNTicket.status.in_([TicketStatus.completed, TicketStatus.rejected])
        )

        # Apply period filter
        if period:
            now = datetime.utcnow()
            period_map = {'24h': timedelta(hours=24), '7d': timedelta(days=7), '30d': timedelta(days=30)}
            delta = period_map.get(period)
            if delta:
                done_filter = and_(done_filter, ManualSSNTicket.updated_at >= now - delta)

        # Stats
        stats_query = select(
            func.count().label('total'),
            func.count().filter(ManualSSNTicket.status == TicketStatus.completed).label('completed'),
            func.count().filter(ManualSSNTicket.status == TicketStatus.rejected).label('rejected'),
            func.avg(
                func.extract('epoch', ManualSSNTicket.updated_at) - func.extract('epoch', ManualSSNTicket.created_at)
            ).filter(ManualSSNTicket.status == TicketStatus.completed).label('avg_seconds'),
        ).select_from(ManualSSNTicket).where(done_filter)

        stats_result = await db.execute(stats_query)
        row = stats_result.one()
        total = row.total
        completed = row.completed
        rejected = row.rejected
        success_rate = (completed / total * 100) if total > 0 else 0.0
        payout = Decimal("1.50") * completed

        # Format avg time
        avg_seconds = row.avg_seconds
        if avg_seconds and avg_seconds > 0:
            avg_sec = int(avg_seconds)
            if avg_sec >= 3600:
                avg_time = f"{avg_sec // 3600}h {(avg_sec % 3600) // 60}m"
            elif avg_sec >= 60:
                avg_time = f"{avg_sec // 60}m {avg_sec % 60}s"
            else:
                avg_time = f"{avg_sec}s"
        else:
            avg_time = "—"

        # Paginated tickets
        query = select(ManualSSNTicket).options(
            selectinload(ManualSSNTicket.user),
            selectinload(ManualSSNTicket.worker)
        ).where(done_filter).order_by(ManualSSNTicket.updated_at.desc())
        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        tickets = result.scalars().all()

        return HistoryResponse(
            tickets=[TicketResponse.from_ticket(t) for t in tickets],
            total_count=total,
            stats=HistoryStatsResponse(
                total=total,
                completed=completed,
                rejected=rejected,
                success_rate=round(success_rate, 1),
                avg_time=avg_time,
                payout=f"{payout:.2f}"
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting worker history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get history"
        )


@router.post("/{ticket_id}/claim", response_model=TicketResponse)
async def claim_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_worker_user)
):
    """Claim an unassigned ticket. Uses SELECT FOR UPDATE to prevent race conditions."""
    try:
        result = await db.execute(
            select(ManualSSNTicket)
            .options(
                selectinload(ManualSSNTicket.user),
                selectinload(ManualSSNTicket.worker)
            )
            .where(ManualSSNTicket.id == ticket_id)
            .with_for_update()
        )
        ticket = result.scalar_one_or_none()

        if not ticket:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

        if ticket.worker_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This ticket is already assigned to another worker"
            )

        if ticket.status != TicketStatus.pending:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot claim ticket with status: {ticket.status.value}"
            )

        ticket.worker_id = current_user.id
        ticket.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(ticket)

        # Reload with relationships
        result = await db.execute(
            select(ManualSSNTicket)
            .options(
                selectinload(ManualSSNTicket.user),
                selectinload(ManualSSNTicket.worker)
            )
            .where(ManualSSNTicket.id == ticket_id)
        )
        ticket = result.scalar_one()

        logger.info(f"Worker {current_user.username} claimed ticket {ticket_id}")

        # Notify other workers that ticket is claimed
        await ws_manager.broadcast("TICKET_CLAIMED", {
            "ticket_id": str(ticket_id),
            "worker_id": str(current_user.id),
            "worker_username": current_user.username
        })

        # Notify Admin API about ticket update
        await _notify_ticket_update(ticket, "ticket_claimed")

        return TicketResponse.from_ticket(ticket)

    except HTTPException:
        await db.rollback()
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error claiming ticket {ticket_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to claim ticket"
        )


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_worker_user)
):
    """Get ticket details. Worker can only view their assigned tickets."""
    try:
        result = await db.execute(
            select(ManualSSNTicket)
            .options(
                selectinload(ManualSSNTicket.user),
                selectinload(ManualSSNTicket.worker)
            )
            .where(ManualSSNTicket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()

        if not ticket:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

        if ticket.worker_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this ticket"
            )

        return TicketResponse.from_ticket(ticket)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ticket {ticket_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get ticket"
        )


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: UUID,
    request: UpdateTicketRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_worker_user)
):
    """
    Update ticket status and/or response_data.
    When status=completed + response_data → auto-create Order for the ticket owner.
    """
    try:
        if request.status is None and request.response_data is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one field (status or response_data) must be provided"
            )

        result = await db.execute(
            select(ManualSSNTicket).where(ManualSSNTicket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()

        if not ticket:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

        if ticket.worker_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this ticket"
            )

        if request.status is not None:
            try:
                status_enum = TicketStatus(request.status)
                ticket.status = status_enum
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status. Must be one of: {[s.value for s in TicketStatus]}"
                )

        if request.response_data is not None:
            ticket.response_data = request.response_data

        await db.commit()
        await db.refresh(ticket)

        # Auto-create Order when ticket is completed with response_data
        if ticket.status == TicketStatus.completed and ticket.response_data and not ticket.order_id:
            from api.common.pricing import get_user_price_by_id, get_default_instant_ssn_price
            default_instant_price = await get_default_instant_ssn_price(db)
            user_price = await get_user_price_by_id(db, ticket.user_id, 'instant_ssn', default_instant_price)

            order_item = {
                "source": "manual_ticket",
                "ticket_id": str(ticket.id),
                "price": str(user_price),
                "firstname": ticket.firstname,
                "lastname": ticket.lastname,
                "address": ticket.address,
                "ticket_status": ticket.status.value,
                "purchased_at": ticket.created_at.isoformat()
            }
            order_item.update(ticket.response_data)

            new_order = Order(
                user_id=ticket.user_id,
                items=[order_item],
                total_price=user_price,
                status=OrderStatus.completed,
                order_type=OrderType.manual_ssn,
                is_viewed=False
            )
            db.add(new_order)
            await db.commit()
            await db.refresh(new_order)

            ticket.order_id = new_order.id
            await db.commit()

            logger.info(f"Auto-created order {new_order.id} for completed ticket {ticket.id}")

        # Reload with relationships
        result = await db.execute(
            select(ManualSSNTicket)
            .options(
                selectinload(ManualSSNTicket.user),
                selectinload(ManualSSNTicket.worker)
            )
            .where(ManualSSNTicket.id == ticket.id)
        )
        ticket = result.scalar_one()

        logger.info(f"Ticket {ticket.id} updated by worker {current_user.username}")
        return TicketResponse.from_ticket(ticket)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating ticket {ticket_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ticket"
        )


@router.post("/{ticket_id}/respond", response_model=TicketResponse)
async def respond_to_ticket(
    ticket_id: UUID,
    request: QuickRespondRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_worker_user)
):
    """
    Quick respond to a ticket with a single text line containing SSN and optionally DOB.
    Parses SSN+DOB from text, updates ticket + linked TestSearchHistory, creates Order.
    """
    try:
        parsed = parse_worker_response(request.text)
        if not parsed['ssn']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not parse SSN from text. Expected format: 123-45-6789 01/15/1985"
            )

        result = await db.execute(
            select(ManualSSNTicket)
            .options(
                selectinload(ManualSSNTicket.user),
                selectinload(ManualSSNTicket.worker)
            )
            .where(ManualSSNTicket.id == ticket_id)
            .with_for_update()
        )
        ticket = result.scalar_one_or_none()

        if not ticket:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

        # Auto-claim if unassigned
        if ticket.worker_id is None:
            ticket.worker_id = current_user.id
            logger.info(f"Auto-claimed ticket {ticket_id} by worker {current_user.username}")
        elif ticket.worker_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this ticket"
            )

        if ticket.status == TicketStatus.completed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket is already completed"
            )

        # Update ticket
        response_data = {'ssn': parsed['ssn']}
        if parsed['dob']:
            response_data['dob'] = parsed['dob']

        ticket.status = TicketStatus.completed
        ticket.response_data = response_data
        ticket.updated_at = datetime.utcnow()

        # Update linked TestSearchHistory if exists
        if ticket.test_search_history_id:
            hist_values = {
                'status': 'done',
                'found': True,
                'ssn': parsed['ssn'],
            }
            if parsed['dob']:
                hist_values['dob'] = parsed['dob']

            hist_stmt = (
                update(TestSearchHistory)
                .where(TestSearchHistory.id == ticket.test_search_history_id)
                .values(**hist_values)
            )
            await db.execute(hist_stmt)

        await db.commit()

        # Auto-create Order
        if not ticket.order_id:
            from api.common.pricing import get_user_price_by_id, get_default_instant_ssn_price
            default_instant_price = await get_default_instant_ssn_price(db)
            user_price = await get_user_price_by_id(db, ticket.user_id, 'instant_ssn', default_instant_price)

            order_item = {
                "source": "manual_ticket",
                "ticket_id": str(ticket.id),
                "price": str(user_price),
                "firstname": ticket.firstname,
                "lastname": ticket.lastname,
                "address": ticket.address,
                "ssn": parsed['ssn'],
            }
            if parsed['dob']:
                order_item['dob'] = parsed['dob']

            new_order = Order(
                user_id=ticket.user_id,
                items=[order_item],
                total_price=user_price,
                status=OrderStatus.completed,
                order_type=OrderType.manual_ssn,
                is_viewed=False
            )
            db.add(new_order)
            await db.commit()
            await db.refresh(new_order)

            ticket.order_id = new_order.id
            await db.commit()

            logger.info(f"Auto-created order {new_order.id} for ticket {ticket.id}")

        # Reload with relationships
        result = await db.execute(
            select(ManualSSNTicket)
            .options(
                selectinload(ManualSSNTicket.user),
                selectinload(ManualSSNTicket.worker)
            )
            .where(ManualSSNTicket.id == ticket.id)
        )
        ticket = result.scalar_one()

        masked_ssn = f"***-**-{parsed['ssn'][-4:]}" if parsed['ssn'] else "N/A"
        logger.info(f"Ticket {ticket.id} responded by worker {current_user.username}: SSN={masked_ssn}")

        # Increment shift counter
        await _increment_shift_counter(db, current_user.id, 'tickets_completed')

        # Notify Admin + Public about ticket completion
        await _notify_ticket_update(ticket, "ticket_completed")

        # Notify other workers that ticket is done
        await ws_manager.broadcast("TICKET_COMPLETED", {
            "ticket_id": str(ticket.id),
            "worker_id": str(current_user.id),
        })

        return TicketResponse.from_ticket(ticket)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error responding to ticket {ticket_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to respond to ticket"
        )


@router.post("/{ticket_id}/reject", response_model=TicketResponse)
async def reject_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_worker_user)
):
    """
    Reject a ticket (worker can't find data).
    Updates linked TestSearchHistory to 'nf' and refunds the user.
    """
    try:
        result = await db.execute(
            select(ManualSSNTicket)
            .options(
                selectinload(ManualSSNTicket.user),
                selectinload(ManualSSNTicket.worker)
            )
            .where(ManualSSNTicket.id == ticket_id)
            .with_for_update()
        )
        ticket = result.scalar_one_or_none()

        if not ticket:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

        # Auto-claim if unassigned
        if ticket.worker_id is None:
            ticket.worker_id = current_user.id
            logger.info(f"Auto-claimed ticket {ticket_id} by worker {current_user.username} (reject)")
        elif ticket.worker_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this ticket"
            )

        if ticket.status in (TicketStatus.completed, TicketStatus.rejected):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ticket is already {ticket.status.value}"
            )

        ticket.status = TicketStatus.rejected
        ticket.updated_at = datetime.utcnow()

        # Update linked TestSearchHistory → nf
        if ticket.test_search_history_id:
            hist_stmt = (
                update(TestSearchHistory)
                .where(TestSearchHistory.id == ticket.test_search_history_id)
                .values(status='nf', found=False)
            )
            await db.execute(hist_stmt)

        # Refund user balance
        from api.common.pricing import get_user_price_by_id, get_default_instant_ssn_price
        default_instant_price = await get_default_instant_ssn_price(db)
        search_price = await get_user_price_by_id(db, ticket.user_id, 'instant_ssn', default_instant_price)
        refund_stmt = (
            update(User)
            .where(User.id == ticket.user_id)
            .values(balance=User.balance + search_price)
        )
        await db.execute(refund_stmt)

        await db.commit()

        logger.info(f"Ticket {ticket.id} rejected by worker {current_user.username}, refunded ${search_price} to user {ticket.user_id}")

        # Reload with relationships
        result = await db.execute(
            select(ManualSSNTicket)
            .options(
                selectinload(ManualSSNTicket.user),
                selectinload(ManualSSNTicket.worker)
            )
            .where(ManualSSNTicket.id == ticket.id)
        )
        ticket = result.scalar_one()

        # Increment shift counter
        await _increment_shift_counter(db, current_user.id, 'tickets_rejected')

        # Notify Admin + Public about ticket rejection
        await _notify_ticket_update(ticket, "ticket_rejected")

        # Notify other workers that ticket is rejected (freed up)
        await ws_manager.broadcast("TICKET_REJECTED", {
            "ticket_id": str(ticket.id),
            "worker_id": str(current_user.id),
        })

        # Notify user about balance update (refund)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{PUBLIC_API_URL}/internal/notify-balance-updated",
                    json={"user_id": str(ticket.user_id), "balance_data": {"reason": "ticket_refund", "amount": str(search_price)}},
                    headers={"X-Internal-Api-Key": INTERNAL_API_KEY}
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed to notify balance update: {e}")

        return TicketResponse.from_ticket(ticket)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error rejecting ticket {ticket_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject ticket"
        )
