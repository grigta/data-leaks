"""
Manual SSN Tickets Router
Handles manual SSN lookup ticket management with role-based access control.
"""

import logging
import os
from datetime import datetime
from typing import List, Optional
from uuid import UUID

import aiohttp
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.admin.dependencies import get_current_admin_user
from api.admin.websocket import ws_manager
from api.common.database import get_postgres_session
from api.common.models_postgres import ManualSSNTicket, TicketStatus, User, Order, OrderStatus, OrderType, AppSettings
from api.public.dependencies import get_current_user
from decimal import Decimal

# Configuration for internal API calls
PUBLIC_API_INTERNAL_URL = os.getenv("PUBLIC_API_INTERNAL_URL", "http://public_api:8000")
WORKER_API_URL = os.getenv("WORKER_API_URL", "http://worker_api:8003")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

# Setup logging
logger = logging.getLogger(__name__)

# Router instance
router = APIRouter(prefix="/tickets", tags=["Manual SSN Tickets"])


# Pydantic Models
class CreateTicketRequest(BaseModel):
    """Request model for creating a new manual SSN ticket"""
    firstname: str = Field(..., max_length=100)
    lastname: str = Field(..., max_length=100)
    address: str = Field(..., description="Full address")


class UpdateTicketRequest(BaseModel):
    """Request model for updating a ticket"""
    status: Optional[str] = None
    response_data: Optional[dict] = None


class AssignTicketRequest(BaseModel):
    """Request model for assigning a ticket to a worker"""
    worker_id: str = Field(..., description="Worker user ID in UUID format")


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
        """Convert ManualSSNTicket model to response"""
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
    """Response model for list of tickets"""
    tickets: List[TicketResponse]
    total_count: int
    page: int
    per_page: int


# Endpoints
@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    request: CreateTicketRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new manual SSN ticket.
    Available to all authenticated users.
    Auto-assigns to an online worker with the fewest active tickets.
    """
    try:
        # Create new ticket
        ticket = ManualSSNTicket(
            user_id=current_user.id,
            firstname=request.firstname,
            lastname=request.lastname,
            address=request.address,
            status=TicketStatus.pending
        )

        # Auto-assign to online worker based on distribution config
        online_worker_ids = []
        try:
            async with httpx.AsyncClient(timeout=5.0) as http_client:
                resp = await http_client.get(
                    f"{WORKER_API_URL}/internal/online-workers",
                    headers={"X-Internal-Api-Key": INTERNAL_API_KEY}
                )
                if resp.status_code == 200:
                    online_worker_ids = resp.json().get("online_worker_ids", [])
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Failed to fetch online workers: {e}")
        assigned_worker = None

        if online_worker_ids:
            # Get distribution mode
            setting = await db.execute(
                select(AppSettings).where(AppSettings.key == "worker_distribution_mode")
            )
            mode_row = setting.scalar_one_or_none()
            dist_mode = mode_row.value if mode_row else "even"

            worker_uuids = [UUID(wid) for wid in online_worker_ids]

            # Filter only workers with active shift (worker_status == 'active')
            active_workers_result = await db.execute(
                select(User.id).where(
                    User.id.in_(worker_uuids),
                    User.worker_status == 'active',
                )
            )
            active_ids = [str(row.id) for row in active_workers_result]
            if active_ids:
                worker_uuids = [UUID(wid) for wid in active_ids]
                online_worker_ids = active_ids
            else:
                # No active workers — ticket stays pending
                worker_uuids = []
                online_worker_ids = []

            # Count active tickets per online worker
            ticket_counts_query = (
                select(
                    ManualSSNTicket.worker_id,
                    func.count(ManualSSNTicket.id).label("active_count")
                )
                .where(
                    ManualSSNTicket.worker_id.in_(worker_uuids),
                    ManualSSNTicket.status.in_([TicketStatus.pending, TicketStatus.processing])
                )
                .group_by(ManualSSNTicket.worker_id)
            )
            result_counts = await db.execute(ticket_counts_query)
            counts_map = {str(row.worker_id): row.active_count for row in result_counts}

            best_worker_id = None

            if dist_mode == "percentage":
                # Get workers with their load_percentage
                workers_result = await db.execute(
                    select(User).where(
                        User.id.in_(worker_uuids),
                        User.load_percentage.isnot(None),
                        User.load_percentage > 0,
                    )
                )
                workers_with_pct = workers_result.scalars().all()

                if workers_with_pct:
                    # Count ALL completed+active tickets per worker (for ratio calculation)
                    all_counts_query = (
                        select(
                            ManualSSNTicket.worker_id,
                            func.count(ManualSSNTicket.id).label("total_count")
                        )
                        .where(ManualSSNTicket.worker_id.in_(worker_uuids))
                        .group_by(ManualSSNTicket.worker_id)
                    )
                    all_result = await db.execute(all_counts_query)
                    all_counts = {str(r.worker_id): r.total_count for r in all_result}

                    # Find worker with biggest gap: target_ratio - actual_ratio
                    total_all = sum(all_counts.values()) or 1
                    best_gap = -float("inf")
                    for w in workers_with_pct:
                        wid = str(w.id)
                        if wid not in online_worker_ids:
                            continue
                        target_ratio = w.load_percentage / 100.0
                        actual_ratio = all_counts.get(wid, 0) / total_all
                        gap = target_ratio - actual_ratio
                        if gap > best_gap:
                            best_gap = gap
                            best_worker_id = wid

            if not best_worker_id:
                # Even mode (or percentage fallback): least active tickets
                min_count = float('inf')
                for wid in online_worker_ids:
                    count = counts_map.get(wid, 0)
                    if count < min_count:
                        min_count = count
                        best_worker_id = wid

            if best_worker_id:
                ticket.worker_id = UUID(best_worker_id)
                ticket.status = TicketStatus.processing
                assigned_worker = best_worker_id
                logger.info(f"Auto-assigned ticket to worker {best_worker_id} (mode: {dist_mode})")

        db.add(ticket)
        await db.commit()
        await db.refresh(ticket)

        # Load relationships
        result = await db.execute(
            select(ManualSSNTicket)
            .options(
                selectinload(ManualSSNTicket.user),
                selectinload(ManualSSNTicket.worker)
            )
            .where(ManualSSNTicket.id == ticket.id)
        )
        ticket = result.scalar_one()

        # Prepare broadcast data
        ticket_data = {
            "id": str(ticket.id),
            "user_id": str(ticket.user_id),
            "username": ticket.user.username if ticket.user else "Unknown",
            "firstname": ticket.firstname,
            "lastname": ticket.lastname,
            "address": ticket.address,
            "status": ticket.status.value,
            "worker_id": str(ticket.worker_id) if ticket.worker_id else None,
            "worker_username": ticket.worker.username if ticket.worker else None,
            "created_at": ticket.created_at.isoformat()
        }

        # Broadcast to admins
        try:
            await ws_manager.broadcast_ticket_created(ticket_data)
        except HTTPException:
            raise
        except Exception as ws_error:
            logger.error(f"WebSocket broadcast failed: {ws_error}")

        # Notify assigned worker via WebSocket
        if assigned_worker:
            try:
                await ws_manager.broadcast_to_worker(assigned_worker, "ticket_created", ticket_data)
            except HTTPException:
                raise
            except Exception as ws_error:
                logger.error(f"WebSocket worker notification failed: {ws_error}")

        # Notify ticket creator via Public API internal endpoint
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{PUBLIC_API_INTERNAL_URL}/internal/notify-ticket-created",
                    json={"user_id": str(ticket.user_id), "ticket_data": ticket_data},
                    headers={"X-Internal-Api-Key": INTERNAL_API_KEY},
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to notify Public API: HTTP {response.status}")
                    else:
                        logger.info(f"Successfully notified Public API about ticket creation")
        except HTTPException:
            raise
        except Exception as notify_error:
            logger.error(f"Error notifying Public API: {notify_error}", exc_info=True)

        logger.info(f"Ticket created: {ticket.id} by user {current_user.username}")

        return TicketResponse.from_ticket(ticket)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating ticket: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ticket"
        )


@router.get("/pending-count")
async def get_pending_tickets_count(
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get count of pending tickets for current user.
    Admin/Worker only endpoint.
    - Workers see count of their assigned pending tickets
    - Admins see count of all pending tickets
    """
    try:
        # Build count query for pending tickets
        count_query = select(func.count()).select_from(ManualSSNTicket).where(
            ManualSSNTicket.status == TicketStatus.pending
        )

        result = await db.execute(count_query)
        count = result.scalar_one()

        return {"count": count}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pending tickets count: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get pending tickets count"
        )


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    List tickets with role-based filtering.
    Admin/Worker only endpoint.
    - Workers see only their assigned tickets
    - Admins see all tickets
    """
    try:
        # Build base query
        query = select(ManualSSNTicket).options(
            selectinload(ManualSSNTicket.user),
            selectinload(ManualSSNTicket.worker)
        )

        # Apply status filter if provided
        if status_filter:
            try:
                status_enum = TicketStatus(status_filter)
                query = query.where(ManualSSNTicket.status == status_enum)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status. Must be one of: {[s.value for s in TicketStatus]}"
                )

        logger.info(f"Admin {current_user.username} listing all tickets")

        # Get total count with same filters
        count_query = select(func.count()).select_from(ManualSSNTicket)
        if status_filter:
            count_query = count_query.where(ManualSSNTicket.status == status_enum)

        total_result = await db.execute(count_query)
        total_count = total_result.scalar_one()

        # Apply pagination and ordering
        query = query.order_by(ManualSSNTicket.created_at.desc())
        query = query.offset(offset).limit(limit)

        # Execute query
        result = await db.execute(query)
        tickets = result.scalars().all()

        return TicketListResponse(
            tickets=[TicketResponse.from_ticket(t) for t in tickets],
            total_count=total_count,
            page=offset // limit + 1 if limit > 0 else 1,
            per_page=limit
        )

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing tickets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list tickets"
        )


@router.get("/unassigned", response_model=TicketListResponse)
async def get_unassigned_tickets(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get all unassigned pending tickets.
    Available to both workers and admins.
    Workers can claim these tickets for themselves.
    """
    try:
        # Query for unassigned pending tickets
        query = select(ManualSSNTicket).options(
            selectinload(ManualSSNTicket.user),
            selectinload(ManualSSNTicket.worker)
        ).where(
            ManualSSNTicket.worker_id.is_(None),
            ManualSSNTicket.status == TicketStatus.pending
        ).order_by(ManualSSNTicket.created_at.desc())

        # Apply pagination
        query = query.limit(limit).offset(offset)

        result = await db.execute(query)
        tickets = result.scalars().all()

        # Count total unassigned tickets
        count_query = select(func.count()).select_from(ManualSSNTicket).where(
            ManualSSNTicket.worker_id.is_(None),
            ManualSSNTicket.status == TicketStatus.pending
        )
        total_result = await db.execute(count_query)
        total_count = total_result.scalar_one()

        logger.info(f"User {current_user.username} listing {len(tickets)} unassigned tickets")

        # Convert to response model
        tickets_data = [TicketResponse.from_ticket(ticket) for ticket in tickets]

        return TicketListResponse(
            tickets=tickets_data,
            total_count=total_count,
            page=offset // limit + 1 if limit > 0 else 1,
            per_page=limit
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting unassigned tickets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get unassigned tickets"
        )

@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Get ticket details.
    Admin/Worker only endpoint.
    Accessible to assigned worker or admin.
    """
    try:
        # Query ticket with relationships
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found"
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
    current_user: User = Depends(get_current_admin_user)
):
    """
    Update ticket status and/or response data.
    Admin/Worker only endpoint.
    Accessible to assigned worker or admin.
    """
    try:
        # Validate that at least one field is provided
        if request.status is None and request.response_data is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one field (status or response_data) must be provided for update"
            )

        # Query ticket
        result = await db.execute(
            select(ManualSSNTicket).where(ManualSSNTicket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()

        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found"
            )

        # Update fields
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

        # Auto-create Order when ticket is completed and has response_data
        new_order = None
        if ticket.status == TicketStatus.completed and ticket.response_data and not ticket.order_id:
            # Create order items from ticket data
            order_item = {
                "source": "manual_ticket",
                "ticket_id": str(ticket.id),
                "firstname": ticket.firstname,
                "lastname": ticket.lastname,
                "address": ticket.address,
                "ticket_status": ticket.status.value,
                "purchased_at": ticket.created_at.isoformat()
            }
            # Add response_data
            order_item.update(ticket.response_data)

            # Get user's actual search price
            from api.common.pricing import get_user_price_by_id, get_default_instant_ssn_price
            default_instant_price = await get_default_instant_ssn_price(db)
            user_price = await get_user_price_by_id(db, ticket.user_id, 'instant_ssn', default_instant_price)
            order_item["price"] = str(user_price)

            # Create order
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

            # Link order to ticket
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

        # Prepare broadcast data
        ticket_data = {
            "id": str(ticket.id),
            "user_id": str(ticket.user_id),
            "username": ticket.user.username if ticket.user else "Unknown",
            "firstname": ticket.firstname,
            "lastname": ticket.lastname,
            "address": ticket.address,
            "status": ticket.status.value,
            "worker_id": str(ticket.worker_id) if ticket.worker_id else None,
            "worker_username": ticket.worker.username if ticket.worker else None,
            "response_data": ticket.response_data,
            "updated_at": ticket.updated_at.isoformat()
        }

        # Broadcast update
        try:
            await ws_manager.broadcast_ticket_updated(ticket_data)
        except HTTPException:
            raise
        except Exception as ws_error:
            logger.error(f"WebSocket broadcast failed: {ws_error}")

        # Notify ticket creator via Public API internal endpoint
        try:
            # Determine endpoint based on status
            endpoint = "notify-ticket-completed" if ticket.status == TicketStatus.completed else "notify-ticket-updated"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{PUBLIC_API_INTERNAL_URL}/internal/{endpoint}",
                    json={"user_id": str(ticket.user_id), "ticket_data": ticket_data},
                    headers={"X-Internal-Api-Key": INTERNAL_API_KEY},
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to notify Public API: HTTP {response.status}")
                    else:
                        logger.info(f"Successfully notified Public API about ticket update (endpoint: {endpoint})")
        except HTTPException:
            raise
        except Exception as notify_error:
            logger.error(f"Error notifying Public API: {notify_error}", exc_info=True)

        logger.info(f"Ticket {ticket.id} updated by {current_user.username}, new status: {ticket.status.value}")

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


@router.post("/{ticket_id}/assign", response_model=TicketResponse)
async def assign_ticket(
    ticket_id: UUID,
    request: AssignTicketRequest,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Assign a ticket to a worker.
    Admin-only endpoint (blocks workers).
    """
    try:
        # Query ticket
        result = await db.execute(
            select(ManualSSNTicket).where(ManualSSNTicket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()

        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found"
            )

        # Parse and validate worker_id
        try:
            worker_uuid = UUID(request.worker_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid worker_id format"
            )

        # Query worker
        worker_result = await db.execute(
            select(User).where(User.id == worker_uuid)
        )
        worker = worker_result.scalar_one_or_none()

        if not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker not found"
            )

        # Verify worker role
        if not worker.worker_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not a worker"
            )

        # Update ticket
        ticket.worker_id = worker_uuid

        # Optionally set status to processing if currently pending
        if ticket.status == TicketStatus.pending:
            ticket.status = TicketStatus.processing

        await db.commit()
        await db.refresh(ticket)

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

        # Prepare broadcast data
        ticket_data = {
            "id": str(ticket.id),
            "user_id": str(ticket.user_id),
            "username": ticket.user.username if ticket.user else "Unknown",
            "firstname": ticket.firstname,
            "lastname": ticket.lastname,
            "address": ticket.address,
            "status": ticket.status.value,
            "worker_id": str(ticket.worker_id),
            "worker_username": ticket.worker.username if ticket.worker else None,
            "updated_at": ticket.updated_at.isoformat()
        }

        # Broadcast assignment
        try:
            await ws_manager.broadcast_ticket_updated(ticket_data)
        except HTTPException:
            raise
        except Exception as ws_error:
            logger.error(f"WebSocket broadcast failed: {ws_error}")

        # Notify ticket creator via Public API internal endpoint
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{PUBLIC_API_INTERNAL_URL}/internal/notify-ticket-updated",
                    json={"user_id": str(ticket.user_id), "ticket_data": ticket_data},
                    headers={"X-Internal-Api-Key": INTERNAL_API_KEY},
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to notify Public API: HTTP {response.status}")
                    else:
                        logger.info(f"Successfully notified Public API about ticket assignment")
        except HTTPException:
            raise
        except Exception as notify_error:
            logger.error(f"Error notifying Public API: {notify_error}", exc_info=True)

        logger.info(f"Ticket {ticket.id} assigned to worker {worker.username} by admin {admin_user.username}")

        return TicketResponse.from_ticket(ticket)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error assigning ticket {ticket_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign ticket"
        )


@router.post("/{ticket_id}/move-to-order")
async def move_ticket_to_order(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Move a completed ticket to orders (worker/admin only).

    Creates a new order from ticket's response_data and deletes the ticket.
    Cost: $0.00 (already paid when ticket was created).

    Authorization:
        - Assigned worker can move their tickets
        - Full admin can move any ticket

    Args:
        ticket_id: Ticket ID
        db: Database session
        current_user: Current authenticated user (worker or admin)

    Returns:
        Created order data
    """
    try:
        # Step 1: Get the ticket
        result = await db.execute(
            select(ManualSSNTicket)
            .options(selectinload(ManualSSNTicket.user))
            .where(ManualSSNTicket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()

        if not ticket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found"
            )

        # Step 2: Validate ticket status - only completed tickets can be moved
        if ticket.status != TicketStatus.completed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot move ticket with status '{ticket.status.value}'. Only completed tickets can be moved to orders."
            )

        # Step 4: Validate that response_data exists
        if not ticket.response_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot move ticket without response data. Please process the ticket first."
            )

        # Step 5: Prepare order items from ticket data
        from api.common.pricing import get_user_price_by_id, get_default_instant_ssn_price
        default_instant_price = await get_default_instant_ssn_price(db)
        user_price = await get_user_price_by_id(db, ticket.user_id, 'instant_ssn', default_instant_price)

        order_items = []

        # Base item with ticket metadata
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

        # Add response_data if available
        if ticket.response_data:
            order_item.update(ticket.response_data)

        order_items.append(order_item)

        # Step 6: Create order (belongs to ticket owner, not current_user)
        new_order = Order(
            user_id=ticket.user_id,  # Order belongs to the ticket owner
            items=order_items,
            total_price=user_price,
            status=OrderStatus.completed,
            order_type=OrderType.manual_ssn,
            is_viewed=False
        )

        db.add(new_order)
        await db.flush()  # Get new_order.id before deletion

        # Link order to ticket before deletion (for audit/debugging)
        ticket.order_id = new_order.id

        # Step 7: Delete the ticket
        await db.delete(ticket)

        # Step 8: Commit transaction
        await db.commit()
        await db.refresh(new_order)

        logger.info(
            f"Worker {current_user.username} moved ticket {ticket_id} to order {new_order.id} "
            f"for user {ticket.user.username if ticket.user else ticket.user_id}"
        )

        # Step 9: Return order data
        return {
            "id": str(new_order.id),
            "user_id": str(new_order.user_id),
            "items": new_order.items,
            "total_price": str(new_order.total_price),
            "status": new_order.status.value,
            "is_viewed": new_order.is_viewed,
            "created_at": new_order.created_at.isoformat(),
            "updated_at": new_order.updated_at.isoformat()
        }

    except HTTPException:
        await db.rollback()
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error moving ticket {ticket_id} to order: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to move ticket to order"
        )



@router.post("/{ticket_id}/claim", response_model=TicketResponse)
async def claim_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Allow an admin to claim an unassigned ticket.
    Admin-only endpoint.
    """
    try:
        # Get the ticket with lock
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ticket not found"
            )

        # Check if ticket is unassigned
        if ticket.worker_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This ticket is already assigned to another worker"
            )

        # Check if ticket is still pending
        if ticket.status != TicketStatus.pending:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot claim ticket with status: {ticket.status.value}"
            )

        # Assign ticket to current user
        ticket.worker_id = current_user.id
        ticket.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(ticket)

        # Load worker relationship
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

        # Broadcast update via WebSocket
        try:
            ticket_data = {
                "id": str(ticket.id),
                "worker_id": str(ticket.worker_id),
                "worker_username": current_user.username,
                "status": ticket.status.value,
                "updated_at": ticket.updated_at.isoformat()
            }
            await ws_manager.broadcast_ticket_updated(ticket_data)
        except HTTPException:
            raise
        except Exception as ws_error:
            logger.error(f"WebSocket broadcast failed: {ws_error}")

        return TicketResponse(
            id=str(ticket.id),
            user_id=str(ticket.user_id),
            username=ticket.user.username if ticket.user else "Unknown",
            worker_id=str(ticket.worker_id),
            worker_username=ticket.worker.username if ticket.worker else current_user.username,
            firstname=ticket.firstname,
            lastname=ticket.lastname,
            address=ticket.address,
            status=ticket.status.value,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at
        )

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
