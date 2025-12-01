"""Middlewares registration module."""
import logging
from aiogram import Dispatcher

from middlewares.chat_activation import ChatActivationMiddleware


logger = logging.getLogger(__name__)


def setup_middlewares(dp: Dispatcher) -> None:
    """Setup middlewares.

    Args:
        dp: Dispatcher instance.

    Notes:
        - ChatActivationMiddleware инжектирует telegram_chat в данные обработчика
        - telegram_chat.user загружается через selectinload в db_operations.get_telegram_chat()
        - Это обеспечивает доступ к telegram_chat.user.username в обработчиках
    """
    # Register chat activation middleware
    dp.message.middleware(ChatActivationMiddleware())

    logger.info("Middlewares registered successfully")
