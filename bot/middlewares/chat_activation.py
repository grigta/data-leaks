"""Chat activation middleware."""
import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from db_operations import get_db_session, get_telegram_chat


logger = logging.getLogger(__name__)


class ChatActivationMiddleware(BaseMiddleware):
    """Middleware to check chat activation status."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """Process event through middleware.

        Args:
            handler: Next handler to call.
            event: Telegram event.
            data: Handler data.

        Returns:
            Handler result or None if blocked.
        """
        # Check if event is a Message
        if not isinstance(event, Message):
            return await handler(event, data)

        message: Message = event

        logger.info(f"Middleware: Processing message from chat {message.chat.id}, type: {message.chat.type}")
        logger.info(f"Middleware: Message text: {message.text[:100] if message.text else 'No text'}")

        # Check if it's a group chat
        if message.chat.type not in ['group', 'supergroup']:
            logger.info(f"Middleware: Not a group chat, passing through")
            return await handler(event, data)

        # Skip activation check for /login, /mode, /balance commands
        if message.text and (message.text.startswith('/login') or message.text.startswith('/mode') or message.text.startswith('/balance')):
            logger.info(f"Middleware: Command ({message.text.split()[0]}), skipping activation check")
            # Still need to load telegram_chat for /mode and /balance commands
            if message.text.startswith('/mode') or message.text.startswith('/balance'):
                try:
                    async with get_db_session() as session:
                        telegram_chat = await get_telegram_chat(session, message.chat.id)
                        data['telegram_chat'] = telegram_chat
                except Exception as e:
                    logger.error(f"Error loading telegram_chat for command: {e}")
            return await handler(event, data)

        # Check chat activation
        logger.info(f"Middleware: Checking activation for chat {message.chat.id}")
        try:
            async with get_db_session() as session:
                telegram_chat = await get_telegram_chat(session, message.chat.id)

                logger.info(f"Middleware: Chat found: {telegram_chat is not None}, active: {telegram_chat.is_active if telegram_chat else 'N/A'}")

                if not telegram_chat or not telegram_chat.is_active:
                    await message.answer(
                        "❌ Чат не активирован. Используйте /login ACCESS_CODE"
                    )
                    logger.warning(
                        f"Blocked message from inactive chat {message.chat.id}"
                    )
                    return None

                # Check if search mode is selected (for non-command messages)
                if not message.text or not message.text.startswith('/'):
                    if not telegram_chat.search_mode:
                        await message.answer(
                            "⚠️ Пожалуйста, выберите режим поиска через /mode перед отправкой данных."
                        )
                        logger.warning(
                            f"Blocked message from chat {message.chat.id} - search_mode not selected"
                        )
                        return None

                # Add telegram_chat to data for handlers
                data['telegram_chat'] = telegram_chat

                logger.info(f"Middleware: Chat activated, passing to handler")
                return await handler(event, data)

        except Exception as e:
            # Fail-open: log error and allow message through
            logger.error(
                f"Error in ChatActivationMiddleware: {e}",
                exc_info=True
            )
            return await handler(event, data)
