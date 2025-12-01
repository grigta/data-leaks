"""Message handler for bot mentions."""
import logging
import os
import aiohttp
from decimal import Decimal
from uuid import UUID
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram import Dispatcher

from db_operations import get_db_session, get_telegram_chat, store_message_reference
from utils.parser import extract_mention_text, parse_ticket_message
from utils.validators import validate_ticket_data
from utils.formatters import (
    format_order_header,
    format_instant_ssn_result,
    format_manual_ticket_created,
    format_error_message
)
from bot.config.pricing import INSTANT_SSN_PRICE, MANUAL_SSN_PRICE


logger = logging.getLogger(__name__)
router = Router(name='messages')


# API configuration
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://localhost:8000")


async def get_jwt_token(access_code: str) -> str:
    """Get JWT token by logging in with access code.

    Args:
        access_code: User's access code

    Returns:
        JWT access token

    Raises:
        Exception: If login fails
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{PUBLIC_API_URL}/auth/login",
            json={"access_code": access_code}
        ) as response:
            if response.status != 200:
                raise Exception(f"Login failed with status {response.status}")

            data = await response.json()
            return data["access_token"]


async def create_manual_ticket_via_api(access_code: str, firstname: str, lastname: str, address: str) -> dict:
    """Create manual SSN ticket via API.

    Args:
        access_code: User's access code
        firstname: First name
        lastname: Last name
        address: Address

    Returns:
        Ticket response data

    Raises:
        Exception: If ticket creation fails
    """
    # Get JWT token
    token = await get_jwt_token(access_code)

    # Create ticket
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {token}"}
        async with session.post(
            f"{PUBLIC_API_URL}/tickets",
            json={
                "firstname": firstname,
                "lastname": lastname,
                "address": address,
                "source": "telegram_bot"
            },
            headers=headers
        ) as response:
            if response.status != 201:
                raise Exception(f"Ticket creation failed with status {response.status}")

            return await response.json()


async def search_instant_ssn_via_api(access_code: str, firstname: str, lastname: str, address: str) -> dict:
    """Search for SSN via instant SSN API.

    Args:
        access_code: User's access code
        firstname: First name
        lastname: Last name
        address: Address

    Returns:
        Search response data with SSN matches

    Raises:
        Exception: If search fails
    """
    # Get JWT token
    token = await get_jwt_token(access_code)

    # Perform instant SSN search
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {token}"}
        async with session.post(
            f"{PUBLIC_API_URL}/search/instant-ssn",
            json={
                "firstname": firstname,
                "lastname": lastname,
                "address": address,
                "source": "telegram_bot"
            },
            headers=headers
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Instant SSN search failed with status {response.status}: {error_text}")

            return await response.json()


async def has_bot_mention(message: Message, bot_username: str) -> bool:
    """Check if message has mention of the bot using Telegram entities.

    Args:
        message: Telegram message
        bot_username: Bot username

    Returns:
        True if message mentions the bot
    """
    if not message.text or not message.entities:
        return False

    for entity in message.entities:
        if entity.type == "mention":
            # Extract mention text from message
            mention = message.text[entity.offset:entity.offset + entity.length]
            if mention == f"@{bot_username}":
                return True
    return False


async def handle_instant_search(message: Message, telegram_chat, ticket_data):
    """Handle instant SSN search mode.

    Args:
        message: Telegram message
        telegram_chat: TelegramChat object
        ticket_data: Parsed ticket data
    """
    try:
        logger.info(f"Instant SSN search for {ticket_data.firstname} {ticket_data.lastname}")

        # Perform instant SSN search
        search_response = await search_instant_ssn_via_api(
            telegram_chat.access_code,
            ticket_data.firstname,
            ticket_data.lastname,
            ticket_data.address
        )

        ssn_matches = search_response.get("results", [])
        if not ssn_matches:
            error_msg = format_error_message(
                "Не найдено",
                f"SSN не найден для {ticket_data.firstname} {ticket_data.lastname}\nАдрес: {ticket_data.address}"
            )
            await message.reply(error_msg, parse_mode='HTML')
            return

        # Get order_id and username for header
        order_id = search_response.get("order_id")
        if not order_id:
            logger.warning("No order_id in search response")
            await message.reply("❌ Ошибка: отсутствует ID заказа", parse_mode='HTML')
            return

        username = telegram_chat.user.username if telegram_chat.user else "unknown"

        # Generate header
        header = format_order_header(
            UUID(order_id),
            username,
            'instant_ssn',
            INSTANT_SSN_PRICE
        )

        # Format complete message
        result_message = format_instant_ssn_result(header, ssn_matches, ticket_data)

        await message.reply(result_message, parse_mode='HTML')

        # Log charged amount
        charged = search_response.get("charged_amount", 0)
        logger.info(f"Instant SSN search completed, charged ${charged}")

    except Exception as e:
        logger.error(f"Error in instant SSN search: {e}", exc_info=True)
        error_msg = format_error_message("Ошибка", "Ошибка при поиске SSN. Попробуйте позже.")
        await message.reply(error_msg, parse_mode='HTML')


async def handle_manual_ticket(message: Message, telegram_chat, ticket_data):
    """Handle manual SSN ticket mode.

    Args:
        message: Telegram message
        telegram_chat: TelegramChat object
        ticket_data: Parsed ticket data
    """
    try:
        logger.info(f"Creating manual ticket for {ticket_data.firstname} {ticket_data.lastname}")

        # Create manual ticket
        ticket_response = await create_manual_ticket_via_api(
            telegram_chat.access_code,
            ticket_data.firstname,
            ticket_data.lastname,
            ticket_data.address
        )

        ticket_id = UUID(ticket_response['id'])

        # Store message reference for later reply
        try:
            async with get_db_session() as session:
                await store_message_reference(
                    session,
                    ticket_id,
                    message.chat.id,
                    message.message_id
                )
        except Exception as store_error:
            logger.error(f"Failed to store message reference: {store_error}", exc_info=True)
            # Continue even if storing failed

        # Format confirmation message
        confirmation_message = format_manual_ticket_created(
            None,  # No header for manual tickets at creation time
            ticket_id,
            ticket_data.__dict__,
            ticket_response['status']
        )

        await message.reply(confirmation_message, parse_mode='HTML')
        logger.info(f"Manual ticket {ticket_response['id']} created for chat {message.chat.id}")

    except Exception as e:
        logger.error(f"Error creating manual ticket: {e}", exc_info=True)
        error_msg = format_error_message("Ошибка", "Ошибка при создании тикета. Попробуйте позже.")
        await message.reply(error_msg, parse_mode='HTML')


async def handle_hybrid_search(message: Message, telegram_chat, ticket_data):
    """Handle hybrid search mode (instant first, fallback to manual).

    Args:
        message: Telegram message
        telegram_chat: TelegramChat object
        ticket_data: Parsed ticket data
    """
    try:
        logger.info(f"Hybrid search for {ticket_data.firstname} {ticket_data.lastname}")

        # First, try instant SSN search
        try:
            search_response = await search_instant_ssn_via_api(
                telegram_chat.access_code,
                ticket_data.firstname,
                ticket_data.lastname,
                ticket_data.address
            )

            ssn_matches = search_response.get("results", [])

            if ssn_matches:
                # Found SSN - format and send results
                order_id = search_response.get("order_id")
                if not order_id:
                    logger.warning("No order_id in hybrid search response")
                    await message.reply("❌ Ошибка: отсутствует ID заказа", parse_mode='HTML')
                    return

                username = telegram_chat.user.username if telegram_chat.user else "unknown"

                # Generate header
                header = format_order_header(
                    UUID(order_id),
                    username,
                    'instant_ssn',
                    INSTANT_SSN_PRICE
                )

                # Format complete message
                result_message = format_instant_ssn_result(header, ssn_matches, ticket_data)

                await message.reply(result_message, parse_mode='HTML')
                logger.info(f"Hybrid: Instant search found SSN")
                return

        except Exception as instant_error:
            logger.warning(f"Instant search failed in hybrid mode: {instant_error}")

        # If instant search didn't find anything or failed, create manual ticket
        logger.info(f"Hybrid: Falling back to manual ticket")
        ticket_response = await create_manual_ticket_via_api(
            telegram_chat.access_code,
            ticket_data.firstname,
            ticket_data.lastname,
            ticket_data.address
        )

        ticket_id = UUID(ticket_response['id'])

        # Store message reference for later reply
        try:
            async with get_db_session() as session:
                await store_message_reference(
                    session,
                    ticket_id,
                    message.chat.id,
                    message.message_id
                )
        except Exception as store_error:
            logger.error(f"Failed to store message reference: {store_error}", exc_info=True)
            # Continue even if storing failed

        # Format fallback confirmation message
        fallback_message = format_manual_ticket_created(
            None,
            ticket_id,
            ticket_data.__dict__,
            ticket_response['status']
        )

        # Add note about fallback
        fallback_message = f"⚡ Instant поиск не дал результатов.\n\n{fallback_message}"

        await message.reply(fallback_message, parse_mode='HTML')
        logger.info(f"Hybrid: Manual ticket {ticket_response['id']} created as fallback")

    except Exception as e:
        logger.error(f"Error in hybrid search: {e}", exc_info=True)
        error_msg = format_error_message("Ошибка", "Ошибка при обработке запроса. Попробуйте позже.")
        await message.reply(error_msg, parse_mode='HTML')


@router.message()
async def handle_mention(message: Message, bot: Bot, telegram_chat=None):
    """Handle messages with bot mention.

    Args:
        message: Telegram message.
        bot: Bot instance.
        telegram_chat: Telegram chat object from middleware.
    """
    try:
        # Get bot username
        bot_info = await bot.get_me()
        bot_username = bot_info.username

        logger.info(f"Received message: {message.text[:100] if message.text else 'No text'}")
        logger.info(f"Bot username: {bot_username}")

        # Skip if no text
        if not message.text:
            logger.info("Message has no text, skipping")
            return

        # Check if message contains bot mention using entities
        has_mention = await has_bot_mention(message, bot_username)
        logger.info(f"Has bot mention: {has_mention}")

        if not has_mention:
            # Not a mention for this bot, ignore
            return

        # Extract text after mention
        mention_text = extract_mention_text(message.text, bot_username)
        logger.info(f"Extracted mention text: {mention_text[:100] if mention_text else 'None'}")

        if not mention_text:
            # No text after mention, ignore
            error_msg = format_error_message("Ошибка", "Пожалуйста, укажите данные после упоминания бота")
            await message.reply(error_msg, parse_mode='HTML')
            return

        logger.info(f"Processing mention from chat {message.chat.id}")

        # Parse ticket data
        ticket_data = parse_ticket_message(mention_text)
        if not ticket_data:
            error_msg = format_error_message(
                "Ошибка парсинга",
                "Не удалось распознать данные. Используйте формат:\nFirstname Lastname\nAddress"
            )
            await message.reply(error_msg, parse_mode='HTML')
            return

        # Validate ticket data
        is_valid, error_message = validate_ticket_data(
            ticket_data.firstname,
            ticket_data.lastname,
            ticket_data.address
        )

        if not is_valid:
            error_msg = format_error_message("Ошибка валидации", error_message)
            await message.reply(error_msg, parse_mode='HTML')
            return

        # Use telegram_chat from middleware
        if not telegram_chat:
            error_msg = format_error_message("Не авторизован", "Чат не активирован. Используйте /login ACCESS_CODE")
            await message.reply(error_msg, parse_mode='HTML')
            return

        # Get search mode
        search_mode = telegram_chat.search_mode
        logger.info(f"Search mode for chat {message.chat.id}: {search_mode}")

        # Process based on search mode
        if search_mode == "instant_ssn":
            await handle_instant_search(message, telegram_chat, ticket_data)
        elif search_mode == "manual_ssn":
            await handle_manual_ticket(message, telegram_chat, ticket_data)
        elif search_mode == "hybrid":
            await handle_hybrid_search(message, telegram_chat, ticket_data)
        else:
            error_msg = format_error_message("Ошибка", "Неизвестный режим поиска. Пожалуйста, выберите режим через /mode")
            await message.reply(error_msg, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Error handling mention: {e}", exc_info=True)
        error_msg = format_error_message("Ошибка", "Произошла ошибка при создании тикета. Попробуйте позже.")
        await message.reply(error_msg, parse_mode='HTML')


def register_message_handlers(dp: Dispatcher) -> None:
    """Register message handlers.

    Args:
        dp: Dispatcher instance.
    """
    dp.include_router(router)
    logger.info("Message handlers registered")
