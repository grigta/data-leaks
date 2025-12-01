"""Validation utilities."""
import re
import logging
from typing import Optional, Tuple


logger = logging.getLogger(__name__)


def validate_access_code(access_code: str) -> bool:
    """Validate access code format.

    Expected format: XXX-XXX-XXX-XXX (15 characters total)

    Args:
        access_code: Access code to validate.

    Returns:
        True if format is valid, False otherwise.
    """
    try:
        pattern = r'^\d{3}-\d{3}-\d{3}-\d{3}$'
        is_valid = bool(re.match(pattern, access_code))

        if not is_valid:
            logger.warning(f"Invalid access code format: {access_code}")

        return is_valid
    except Exception as e:
        logger.error(f"Error validating access code: {e}", exc_info=True)
        return False


def is_group_chat(chat_type: str) -> bool:
    """Check if chat is a group or supergroup.

    Args:
        chat_type: Chat type from Telegram.

    Returns:
        True if group or supergroup, False otherwise.
    """
    return chat_type in ['group', 'supergroup']


def validate_ticket_data(
    firstname: str, lastname: str, address: str
) -> Tuple[bool, Optional[str]]:
    """Validate ticket data.

    Args:
        firstname: First name.
        lastname: Last name.
        address: Address.

    Returns:
        Tuple of (is_valid, error_message).
    """
    try:
        # Check all fields are non-empty
        if not firstname or not lastname or not address:
            return False, "Все обязательные поля должны быть заполнены"

        # Check minimum lengths
        if len(firstname) < 2:
            return False, "Имя должно содержать минимум 2 символа"

        if len(lastname) < 2:
            return False, "Фамилия должна содержать минимум 2 символа"

        if len(address) < 10:
            return False, "Адрес должен содержать минимум 10 символов"

        return True, None

    except Exception as e:
        logger.error(f"Error validating ticket data: {e}", exc_info=True)
        return False, "Ошибка валидации данных"
