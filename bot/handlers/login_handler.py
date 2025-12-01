"""Login command handler."""
import logging
import os
import aiohttp
from aiogram import Router, F
from aiogram.types import Message
from aiogram import Dispatcher

from db_operations import get_db_session, create_or_update_telegram_chat
from utils.validators import validate_access_code, is_group_chat


logger = logging.getLogger(__name__)
router = Router(name='login')


# API configuration
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://localhost:8000")


async def verify_access_code_via_api(access_code: str) -> dict:
    """Verify access code via API and get user info.

    Args:
        access_code: User's access code

    Returns:
        Dict with access_token and user info

    Raises:
        Exception: If verification fails
    """
    async with aiohttp.ClientSession() as session:
        # Login with access code
        async with session.post(
            f"{PUBLIC_API_URL}/auth/login",
            json={"access_code": access_code}
        ) as response:
            if response.status != 200:
                raise Exception(f"Access code verification failed with status {response.status}")

            login_data = await response.json()
            access_token = login_data["access_token"]

        # Get user info
        headers = {"Authorization": f"Bearer {access_token}"}
        async with session.get(
            f"{PUBLIC_API_URL}/auth/me",
            headers=headers
        ) as response:
            if response.status != 200:
                raise Exception(f"Failed to get user info with status {response.status}")

            user_data = await response.json()
            return {
                "access_token": access_token,
                "user": user_data
            }


@router.message(F.text.startswith('/login'))
async def handle_login(message: Message):
    """Handle /login command.

    Args:
        message: Telegram message.
    """
    try:
        # Check if command is in group chat
        if not is_group_chat(message.chat.type):
            await message.answer("Бот работает только в групповых чатах")
            return

        # Extract access_code from command
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await message.answer(
                    "Неверный формат команды. Используйте: /login XXX-XXX-XXX-XXX"
                )
                return

            access_code = parts[1]
        except IndexError:
            await message.answer(
                "Неверный формат команды. Используйте: /login XXX-XXX-XXX-XXX"
            )
            return

        # Validate access_code format
        if not validate_access_code(access_code):
            await message.answer(
                "Неверный формат access code. Используйте формат: XXX-XXX-XXX-XXX"
            )
            return

        # Verify access code via API
        try:
            auth_data = await verify_access_code_via_api(access_code)
            user_data = auth_data["user"]
        except Exception as e:
            logger.warning(f"Access code verification failed: {e}")
            await message.answer("Access code не найден")
            return

        # Get database session
        async with get_db_session() as session:
            # Create or update telegram chat
            from uuid import UUID
            user_id = UUID(user_data["id"])
            await create_or_update_telegram_chat(
                session, message.chat.id, user_id, access_code
            )

            # Send welcome message with reminder to select mode
            welcome_message = (
                f"✅ Бот активирован!\n\n"
                f"Пользователь: {user_data['username']}\n"
                f"Баланс: ${user_data['balance']}\n\n"
                f"⚠️ <b>Перед отправкой данных выберите режим поиска через команду /mode</b>\n\n"
                f"Доступные режимы:\n"
                f"• ⚡ Instant SSN ($2) - быстрый поиск\n"
                f"• 👤 Manual SSN ($3) - обработка воркерами\n"
                f"• 🔄 Hybrid (авто) - instant, затем manual\n\n"
                f"💰 Для проверки баланса используйте команду /balance"
            )
            await message.answer(welcome_message, parse_mode='HTML')

            logger.info(
                f"Chat {message.chat.id} activated for user {user_data['username']}"
            )

    except Exception as e:
        logger.error(f"Error handling login command: {e}", exc_info=True)
        await message.answer(
            "Произошла ошибка при активации бота. Попробуйте позже."
        )


def register_login_handlers(dp: Dispatcher) -> None:
    """Register login handlers.

    Args:
        dp: Dispatcher instance.
    """
    dp.include_router(router)
    logger.info("Login handlers registered")
