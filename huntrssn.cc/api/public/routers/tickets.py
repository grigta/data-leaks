"""
Public Tickets Router
Handles ticket viewing for regular users.
"""

import logging
import os
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.common.database import get_postgres_session
from api.common.models_postgres import ManualSSNTicket, TicketStatus, User, Order, OrderStatus, OrderType
from api.common.pricing import MANUAL_SSN_PRICE, check_maintenance_mode, get_user_price
from api.public.dependencies import get_current_user

# Configuration for internal API calls
ADMIN_API_INTERNAL_URL = os.getenv("ADMIN_API_INTERNAL_URL", "http://admin_api:8002")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

# Setup logging
logger = logging.getLogger(__name__)

# Manual SSN ticket cost (from centralized pricing module)
MANUAL_SSN_COST = MANUAL_SSN_PRICE

# Router instance
router = APIRouter(tags=["User Tickets"])


# Response models (reusing from admin router structure)
from pydantic import BaseModel, Field


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
    is_viewed: bool = False
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
            is_viewed=ticket.is_viewed,
            created_at=ticket.created_at.isoformat(),
            updated_at=ticket.updated_at.isoformat()
        )


class TicketListResponse(BaseModel):
    """Response model for list of tickets"""
    tickets: List[TicketResponse]
    total_count: int


class TicketCreateRequest(BaseModel):
    """Request model for creating a ticket"""
    firstname: str = Field(..., min_length=1, max_length=100)
    lastname: str = Field(..., min_length=1, max_length=100)
    address: str = Field(..., min_length=1, max_length=500)
    source: Optional[str] = Field(default="web", description="Request source: web, telegram_bot, or other")


class CountResponse(BaseModel):
    """Response model for count endpoints"""
    count: int


class MarkViewedRequest(BaseModel):
    """Request model for marking tickets as viewed"""
    ticket_ids: List[UUID] = Field(..., min_length=1, description="List of ticket UUIDs to mark as viewed")


# Endpoints
@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    ticket_data: TicketCreateRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new manual SSN ticket.

    Cost: $3.00 per ticket (or custom pricing if set).
    The cost is atomically deducted from the user's balance at the moment of ticket creation
    using get_user_price() to determine the final price. If any error occurs after deduction,
    the system attempts to refund the amount.

    Args:
        ticket_data: Ticket data (firstname, lastname, address)
        db: Database session
        current_user: Current authenticated user

    Returns:
        Created ticket

    Raises:
        HTTPException 402: Insufficient balance
        HTTPException 503: Service is in maintenance mode
        HTTPException 500: Failed to create ticket
    """
    try:
        # Check if Manual SSN is in maintenance mode
        is_maintenance, maintenance_message = await check_maintenance_mode(db, 'manual_ssn')
        if is_maintenance:
            default_message = "Manual SSN service is currently under maintenance. Please try again later."
            message = maintenance_message or default_message
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=message
            )

        # Get custom price for this user or use default
        manual_ssn_price = await get_user_price(
            db=db,
            access_code=current_user.access_code or '',
            service_name='manual_ssn',
            default_price=MANUAL_SSN_PRICE
        )

        # Step 1: Check user balance
        if current_user.balance < manual_ssn_price:
            logger.warning(
                f"Insufficient balance for user {current_user.id}: "
                f"required ${manual_ssn_price}, available ${current_user.balance}"
            )
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient balance. Required: ${manual_ssn_price}, Available: ${current_user.balance}"
            )

        # Step 2: Atomically deduct cost from user balance
        stmt = (
            update(User)
            .where(User.id == current_user.id, User.balance >= manual_ssn_price)
            .values(balance=User.balance - manual_ssn_price)
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
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Insufficient balance. Required: ${manual_ssn_price}"
            )

        new_balance = new_balance_row[0]
        logger.info(
            f"Atomically deducted ${manual_ssn_price} from user {current_user.id}. "
            f"New balance: ${new_balance}"
        )

        # Determine source from request
        from api.common.models_postgres import RequestSource
        if ticket_data.source == "telegram_bot":
            source = RequestSource.telegram_bot
        elif ticket_data.source == "web":
            source = RequestSource.web
        else:
            source = RequestSource.other

        # Step 3: Create new ticket
        new_ticket = ManualSSNTicket(
            user_id=current_user.id,
            firstname=ticket_data.firstname,
            lastname=ticket_data.lastname,
            address=ticket_data.address,
            status=TicketStatus.pending,
            source=source
        )

        db.add(new_ticket)
        await db.commit()
        await db.refresh(new_ticket, ["user"])

        logger.info(f"Created ticket {new_ticket.id} for user {current_user.username}")

        # Notify admin API via internal endpoint to broadcast to admins via WebSocket
        try:
            notify_data = {
                "id": str(new_ticket.id),
                "user_id": str(new_ticket.user_id),
                "username": current_user.username,
                "firstname": new_ticket.firstname,
                "lastname": new_ticket.lastname,
                "address": new_ticket.address,
                "status": new_ticket.status.value,
                "created_at": new_ticket.created_at.isoformat()
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{ADMIN_API_INTERNAL_URL}/internal/notify-ticket-created",
                    json={"ticket_data": notify_data},
                    headers={"X-Internal-Api-Key": INTERNAL_API_KEY},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to notify Admin API: HTTP {response.status}")
                    else:
                        logger.info(f"Successfully notified Admin API about ticket {new_ticket.id}")
        except HTTPException:
            raise
        except Exception as notify_error:
            logger.error(f"Error notifying Admin API about ticket creation: {notify_error}")

        return TicketResponse.from_ticket(new_ticket)

    except HTTPException:
        # Re-raise HTTP exceptions
        await db.rollback()
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating ticket: {e}", exc_info=True)
        await db.rollback()

        # Attempt to refund if balance was deducted
        try:
            refund_stmt = (
                update(User)
                .where(User.id == current_user.id)
                .values(balance=User.balance + manual_ssn_price)
            )
            await db.execute(refund_stmt)
            await db.commit()
            logger.info(f"Refunded ${manual_ssn_price} to user {current_user.id} after ticket creation failure")
        except HTTPException:
            raise
        except Exception as refund_error:
            logger.critical(
                f"CRITICAL: Failed to refund ${manual_ssn_price} to user {current_user.id}: {refund_error}",
                exc_info=True
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ticket"
        )



@router.get("", response_model=TicketListResponse)
async def get_my_tickets(
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's tickets.
    Available to all authenticated users.
    """
    try:
        # Build base query - filter by current user
        query = select(ManualSSNTicket).options(
            selectinload(ManualSSNTicket.user),
            selectinload(ManualSSNTicket.worker)
        ).where(ManualSSNTicket.user_id == current_user.id)

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

        # Get total count with same filters
        count_query = select(func.count()).select_from(ManualSSNTicket).where(
            ManualSSNTicket.user_id == current_user.id
        )
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

        logger.info(f"User {current_user.username} retrieved {len(tickets)} tickets")

        return TicketListResponse(
            tickets=[TicketResponse.from_ticket(t) for t in tickets],
            total_count=total_count
        )

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user tickets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get tickets"
        )


@router.get("/unviewed-count")
async def get_unviewed_tickets_count(
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get count of unviewed completed tickets for current user.
    Only counts tickets with status='completed' and is_viewed=False.
    """
    logger.info(f"[UNVIEWED-COUNT] Endpoint called for user {current_user.username}")
    try:
        count_query = select(func.count()).select_from(ManualSSNTicket).where(
            ManualSSNTicket.user_id == current_user.id,
            ManualSSNTicket.status == TicketStatus.completed,
            ManualSSNTicket.is_viewed == False
        )
        result = await db.execute(count_query)
        count = result.scalar() or 0

        logger.info(f"[UNVIEWED-COUNT] User {current_user.username} has {count} unviewed tickets")
        return {"count": int(count)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting unviewed tickets count: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get unviewed tickets count"
        )


@router.post("/mark-viewed", response_model=dict)
async def mark_tickets_as_viewed(
    request: MarkViewedRequest,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Mark specified tickets as viewed.
    Only marks tickets owned by current user.

    Args:
        request: Request containing list of ticket UUIDs
        db: Database session
        current_user: Current authenticated user

    Returns:
        Success status and count of updated tickets

    Raises:
        HTTPException 422: If ticket_ids contain invalid UUIDs (handled by Pydantic)
        HTTPException 500: If database operation fails
    """
    try:
        # UUIDs are already validated by Pydantic
        uuid_ids = request.ticket_ids

        # Update tickets
        stmt = (
            update(ManualSSNTicket)
            .where(
                ManualSSNTicket.id.in_(uuid_ids),
                ManualSSNTicket.user_id == current_user.id
            )
            .values(is_viewed=True)
        )
        result = await db.execute(stmt)
        await db.commit()

        updated_count = result.rowcount
        logger.info(f"Marked {updated_count} tickets as viewed for user {current_user.username}")

        return {"success": True, "updated_count": updated_count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking tickets as viewed: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark tickets as viewed"
        )


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket_details(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Get details of a specific ticket.
    Available to all authenticated users (owner only).
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

        # Authorization check - only owner can view
        if ticket.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this ticket"
            )

        logger.info(f"User {current_user.username} viewed ticket {ticket_id}")

        return TicketResponse.from_ticket(ticket)

    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ticket details {ticket_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get ticket details"
        )


class OrderResponse(BaseModel):
    """Response model for order data"""
    id: str
    user_id: str
    items: list
    total_price: str
    status: str
    is_viewed: bool
    created_at: str
    updated_at: str


@router.post("/{ticket_id}/move-to-order", response_model=OrderResponse)
async def move_ticket_to_order(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_postgres_session),
    current_user: User = Depends(get_current_user)
):
    """
    Move a ticket to orders.

    Creates a new order from ticket's response_data and deletes the ticket.
    Cost: $0.00 (already paid when ticket was created).

    Args:
        ticket_id: Ticket ID
        db: Database session
        current_user: Current authenticated user

    Returns:
        Created order
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

        # Step 2: Authorization check - only owner can move
        if ticket.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to move this ticket"
            )

        # Step 3: Prepare order items from ticket data
        from api.common.pricing import get_user_price_by_id, get_default_instant_ssn_price
        default_instant_price = await get_default_instant_ssn_price(db)
        user_price = await get_user_price_by_id(db, current_user.id, 'instant_ssn', default_instant_price)

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

        # Step 4: Create order
        new_order = Order(
            user_id=current_user.id,
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

        # Step 5: Delete the ticket
        await db.delete(ticket)

        # Step 6: Commit transaction
        await db.commit()
        await db.refresh(new_order)

        logger.info(
            f"Moved ticket {ticket_id} to order {new_order.id} for user {current_user.username}"
        )

        return OrderResponse(
            id=str(new_order.id),
            user_id=str(new_order.user_id),
            items=new_order.items,
            total_price=str(new_order.total_price),
            status=new_order.status.value,
            is_viewed=new_order.is_viewed,
            created_at=new_order.created_at.isoformat(),
            updated_at=new_order.updated_at.isoformat()
        )

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
