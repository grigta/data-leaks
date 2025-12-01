"""Mode handler for selecting search mode."""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db_operations import get_db_session, update_search_mode


logger = logging.getLogger(__name__)

# Router instance
router = Router()


# Mode descriptions
MODE_NAMES = {
    "instant_ssn": "⚡ Instant SSN ($2)",
    "manual_ssn": "👤 Manual SSN ($3.00)",
    "hybrid": "🔄 Hybrid (авто)"
}

MODE_DESCRIPTIONS = {
    "instant_ssn": "Мгновенный поиск SSN. Списание $2 только при успешном результате.",
    "manual_ssn": "Создание тикета для ручной обработки воркерами. Стоимость: $3.00 за запрос.",
    "hybrid": "Сначала пытается instant поиск ($2 при успехе). Если SSN не найден → автоматически создаёт manual тикет ($3.00)."
}


def get_mode_keyboard(current_mode: str = None) -> InlineKeyboardBuilder:
    """Build inline keyboard for mode selection.

    Args:
        current_mode: Currently selected mode (to mark with ✓).

    Returns:
        InlineKeyboardBuilder with mode buttons.
    """
    builder = InlineKeyboardBuilder()

    for mode_key, mode_name in MODE_NAMES.items():
        # Add checkmark if this is current mode
        button_text = f"{mode_name} ✓" if mode_key == current_mode else mode_name
        builder.button(
            text=button_text,
            callback_data=f"mode:{mode_key}"
        )

    # Arrange buttons in 1 column
    builder.adjust(1)

    return builder


@router.message(Command("mode"))
async def handle_mode_command(message: Message, telegram_chat=None):
    """Handle /mode command - show mode selection menu.

    Args:
        message: Telegram message.
        telegram_chat: TelegramChat object from middleware.
    """
    logger.info(f"Mode command from chat {message.chat.id}")

    if not telegram_chat:
        await message.answer(
            "⚠️ Пожалуйста, выполните /login перед использованием этой команды."
        )
        return

    # Get current mode
    current_mode = telegram_chat.search_mode

    # Build message
    if current_mode:
        mode_text = f"🔧 <b>Текущий режим:</b> {MODE_NAMES[current_mode]}\n\n"
    else:
        mode_text = "⚠️ <b>Режим не выбран!</b>\n\n"

    mode_text += "📋 <b>Доступные режимы:</b>\n\n"

    for mode_key, mode_name in MODE_NAMES.items():
        mode_text += f"<b>{mode_name}</b>\n{MODE_DESCRIPTIONS[mode_key]}\n\n"

    mode_text += "Выберите режим для поиска SSN:"

    # Send message with inline keyboard
    keyboard = get_mode_keyboard(current_mode)

    await message.answer(
        mode_text,
        reply_markup=keyboard.as_markup(),
        parse_mode='HTML'
    )


@router.callback_query(F.data.startswith("mode:"))
async def handle_mode_selection(callback: CallbackQuery):
    """Handle mode selection callback.

    Args:
        callback: Callback query from inline button.
    """
    # Extract mode from callback data
    mode = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    logger.info(f"Mode selection: {mode} from chat {chat_id}")

    # Update search mode in database
    async with get_db_session() as session:
        updated_chat = await update_search_mode(session, chat_id, mode)

        if not updated_chat:
            await callback.answer("❌ Ошибка обновления режима", show_alert=True)
            return

    # Show confirmation
    await callback.answer(f"✅ Режим изменён на {MODE_NAMES[mode]}", show_alert=False)

    # Update message with new keyboard (showing checkmark on selected mode)
    keyboard = get_mode_keyboard(mode)

    # Build confirmation text
    confirmation_text = f"✅ <b>Режим изменён на:</b> {MODE_NAMES[mode]}\n\n"

    # Add description only for manual_ssn and hybrid modes
    if mode in ["manual_ssn", "hybrid"]:
        confirmation_text += f"{MODE_DESCRIPTIONS[mode]}\n\n"

    confirmation_text += "Теперь вы можете отправлять данные боту для поиска SSN."

    await callback.message.edit_text(
        confirmation_text,
        reply_markup=keyboard.as_markup(),
        parse_mode='HTML'
    )


def register_mode_handlers(dp):
    """Register mode handlers.

    Args:
        dp: Dispatcher instance.
    """
    dp.include_router(router)
    logger.info("Mode handlers registered")
