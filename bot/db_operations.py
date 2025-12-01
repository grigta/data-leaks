"""Database operations for the bot."""
import logging
from contextlib import asynccontextmanager
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from api.common.database import async_session_maker
from api.common.models_postgres import User, TelegramChat, ManualSSNTicket, TicketStatus, TelegramMessageReference


logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_db_session():
    """Async context manager for database session.

    Yields:
        AsyncSession: Database session.
    """
    session = async_session_maker()
    try:
        yield session
    finally:
        await session.close()


async def get_user_by_access_code(session, access_code: str) -> Optional[User]:
    """Get user by access code.

    Args:
        session: Database session.
        access_code: User's access code.

    Returns:
        User object or None if not found.
    """
    try:
        result = await session.execute(
            select(User).where(User.access_code == access_code)
        )
        user = result.scalar_one_or_none()

        if user:
            logger.info(f"User found: {user.username} (ID: {user.id})")
        else:
            logger.info(f"User not found for access_code: {access_code}")

        return user
    except Exception as e:
        logger.error(f"Error getting user by access_code: {e}", exc_info=True)
        return None


async def get_telegram_chat(session, chat_id: int) -> Optional[TelegramChat]:
    """Get telegram chat by chat_id.

    Args:
        session: Database session.
        chat_id: Telegram chat ID.

    Returns:
        TelegramChat object or None if not found.
    """
    try:
        result = await session.execute(
            select(TelegramChat)
            .where(TelegramChat.chat_id == chat_id)
            .options(selectinload(TelegramChat.user))
        )
        chat = result.scalar_one_or_none()

        if chat:
            logger.info(f"Chat found: {chat_id} (Active: {chat.is_active})")
        else:
            logger.info(f"Chat not found: {chat_id}")

        return chat
    except Exception as e:
        logger.error(f"Error getting telegram chat: {e}", exc_info=True)
        return None


async def get_user_telegram_chats(session, user_id: UUID) -> List[TelegramChat]:
    """Get all active telegram chats for a user.

    Args:
        session: Database session.
        user_id: User ID.

    Returns:
        List of active TelegramChat objects.
    """
    try:
        result = await session.execute(
            select(TelegramChat)
            .where(and_(TelegramChat.user_id == user_id, TelegramChat.is_active == True))
            .options(selectinload(TelegramChat.user))
        )
        chats = result.scalars().all()

        logger.info(f"Found {len(chats)} active chats for user {user_id}")

        return list(chats)
    except Exception as e:
        logger.error(f"Error getting user telegram chats: {e}", exc_info=True)
        return []


async def create_or_update_telegram_chat(
    session, chat_id: int, user_id: UUID, access_code: str
) -> TelegramChat:
    """Create or update telegram chat.

    Args:
        session: Database session.
        chat_id: Telegram chat ID.
        user_id: User ID.
        access_code: User's access code.

    Returns:
        TelegramChat object.
    """
    try:
        chat = await get_telegram_chat(session, chat_id)

        if chat:
            # Update existing chat
            chat.user_id = user_id
            chat.access_code = access_code
            chat.is_active = True
            chat.activated_at = datetime.utcnow()
            logger.info(f"Updated telegram chat: {chat_id}")
        else:
            # Create new chat
            chat = TelegramChat(
                chat_id=chat_id,
                user_id=user_id,
                access_code=access_code,
                is_active=True,
                activated_at=datetime.utcnow()
            )
            session.add(chat)
            logger.info(f"Created new telegram chat: {chat_id}")

        await session.commit()
        await session.refresh(chat)

        return chat
    except Exception as e:
        logger.error(f"Error creating/updating telegram chat: {e}", exc_info=True)
        await session.rollback()
        raise


async def create_manual_ticket(
    session, user_id: UUID, firstname: str, lastname: str, address: str
) -> ManualSSNTicket:
    """Create manual SSN ticket.

    Args:
        session: Database session.
        user_id: User ID.
        firstname: First name.
        lastname: Last name.
        address: Address.

    Returns:
        ManualSSNTicket object.
    """
    try:
        ticket = ManualSSNTicket(
            user_id=user_id,
            firstname=firstname,
            lastname=lastname,
            address=address,
            status=TicketStatus.pending
        )

        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)

        logger.info(f"Created manual ticket: ID={ticket.id}, User={user_id}")

        return ticket
    except Exception as e:
        logger.error(f"Error creating manual ticket: {e}", exc_info=True)
        await session.rollback()
        raise


async def update_search_mode(session, chat_id: int, search_mode: str) -> Optional[TelegramChat]:
    """Update search mode for telegram chat.

    Args:
        session: Database session.
        chat_id: Telegram chat ID.
        search_mode: Search mode ('instant_ssn', 'manual_ssn', 'hybrid').

    Returns:
        Updated TelegramChat object or None if not found.
    """
    try:
        chat = await get_telegram_chat(session, chat_id)

        if not chat:
            logger.error(f"Chat not found: {chat_id}")
            return None

        chat.search_mode = search_mode
        await session.commit()
        await session.refresh(chat)

        logger.info(f"Updated search_mode to '{search_mode}' for chat {chat_id}")

        return chat
    except Exception as e:
        logger.error(f"Error updating search_mode: {e}", exc_info=True)
        await session.rollback()
        raise


async def store_message_reference(session, ticket_id: UUID, chat_id: int, message_id: int) -> Optional[TelegramMessageReference]:
    """Store telegram message reference for later reply.

    Args:
        session: Database session.
        ticket_id: Manual SSN ticket ID.
        chat_id: Telegram chat ID.
        message_id: Telegram message ID.

    Returns:
        TelegramMessageReference object or None if failed.
    """
    try:
        message_ref = TelegramMessageReference(
            ticket_id=ticket_id,
            chat_id=chat_id,
            message_id=message_id
        )

        session.add(message_ref)
        await session.commit()
        await session.refresh(message_ref)

        logger.info(f"Stored message reference: ticket={ticket_id}, chat={chat_id}, msg={message_id}")

        return message_ref
    except Exception as e:
        logger.error(f"Error storing message reference: {e}", exc_info=True)
        await session.rollback()
        return None


async def get_message_reference(session, ticket_id: UUID) -> Optional[TelegramMessageReference]:
    """Get telegram message reference by ticket ID.

    Args:
        session: Database session.
        ticket_id: Manual SSN ticket ID.

    Returns:
        TelegramMessageReference object or None if not found.
    """
    try:
        result = await session.execute(
            select(TelegramMessageReference)
            .where(TelegramMessageReference.ticket_id == ticket_id)
        )
        message_ref = result.scalar_one_or_none()

        if message_ref:
            logger.info(f"Found message reference for ticket {ticket_id}")
        else:
            logger.info(f"No message reference found for ticket {ticket_id}")

        return message_ref
    except Exception as e:
        logger.error(f"Error getting message reference: {e}", exc_info=True)
        return None


async def cleanup_old_message_references(session, days: int = 7) -> int:
    """Delete message references older than specified days.

    Args:
        session: Database session.
        days: Number of days to keep (default: 7).

    Returns:
        Number of deleted records.
    """
    try:
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        result = await session.execute(
            select(TelegramMessageReference)
            .where(TelegramMessageReference.created_at < cutoff_date)
        )
        old_refs = result.scalars().all()

        count = len(old_refs)
        for ref in old_refs:
            await session.delete(ref)

        await session.commit()

        logger.info(f"Cleaned up {count} old message references (older than {days} days)")

        return count
    except Exception as e:
        logger.error(f"Error cleaning up message references: {e}", exc_info=True)
        await session.rollback()
        return 0
