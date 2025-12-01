"""Balance handler for checking user balance."""
import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from config.pricing import INSTANT_SSN_PRICE, MANUAL_SSN_PRICE


logger = logging.getLogger(__name__)

# Router instance
router = Router()


@router.message(Command("balance"))
async def handle_balance_command(message: Message, telegram_chat=None):
    """Handle /balance command - show user balance and pricing.

    Args:
        message: Telegram message.
        telegram_chat: TelegramChat object from middleware.
    """
    logger.info(f"Balance command from chat {message.chat.id}")

    if not telegram_chat:
        await message.answer(
            "⚠️ Пожалуйста, выполните /login перед использованием этой команды."
        )
        return

    # Get user balance from relationship
    user_balance = telegram_chat.user.balance

    # Format balance message
    balance_message = (
        f"💰 <b>Ваш баланс</b>\n\n"
        f"Текущий баланс: <b>${user_balance:.2f}</b>\n\n"
        f"📋 <b>Цены:</b>\n"
        f"• ⚡ Instant SSN: ${INSTANT_SSN_PRICE:.2f}\n"
        f"• 👤 Manual SSN: ${MANUAL_SSN_PRICE:.2f}"
    )

    await message.answer(
        balance_message,
        parse_mode='HTML'
    )


def register_balance_handlers(dp):
    """Register balance handlers.

    Args:
        dp: Dispatcher instance.
    """
    dp.include_router(router)
    logger.info("Balance handlers registered")
