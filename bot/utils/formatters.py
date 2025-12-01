"""Message formatting utilities."""
import logging
from typing import Optional
from decimal import Decimal
from uuid import UUID
import html


logger = logging.getLogger(__name__)


def escape_html(text: str) -> str:
    """Safely escape HTML characters.

    Args:
        text: Text to escape.

    Returns:
        HTML-escaped text.
    """
    return html.escape(str(text))


def format_price(price: Decimal) -> str:
    """Format price consistently.

    Args:
        price: Price as Decimal.

    Returns:
        Formatted price string (e.g., "$2.00").
    """
    return f"${price:.2f}"


def shorten_uuid(uuid_str: str) -> str:
    """Extract display ID from UUID.

    Args:
        uuid_str: UUID string.

    Returns:
        Last 8 characters of UUID.
    """
    return str(uuid_str)[-8:]


def format_order_header(order_id: UUID, username: str, order_type: str, price: Decimal) -> str:
    """Generate order header string.

    Args:
        order_id: Order UUID.
        username: User's username.
        order_type: Type of order (instant_ssn, manual_ssn).
        price: Order price.

    Returns:
        Formatted header string (e.g., "№ a1b2c3d4 username | SSNDOB $2.00").
    """
    short_id = shorten_uuid(str(order_id))

    # Map order types to display names
    type_mapping = {
        'instant_ssn': 'SSNDOB',
        'manual_ssn': 'SSNDOB'
    }
    display_type = type_mapping.get(order_type, order_type)

    formatted_price = format_price(price)

    return f"№ {short_id} {username} | {display_type} {formatted_price}"


def format_instant_ssn_result(header: str, results: list, original_request: dict) -> str:
    """Format instant SSN search results.

    Args:
        header: Order header string.
        results: List of search result dictionaries.
        original_request: Original request data (TicketData).

    Returns:
        Formatted message ready for Telegram.
    """
    try:
        message_parts = [f"<b>{escape_html(header)}</b>\n"]

        # Add original request info
        message_parts.append("\n<b>Запрос:</b>")
        if hasattr(original_request, 'firstname'):
            message_parts.append(f"Имя: {escape_html(original_request.firstname)} {escape_html(original_request.lastname)}")
        if hasattr(original_request, 'address'):
            message_parts.append(f"Адрес: {escape_html(original_request.address)}")

        message_parts.append("\n<b>Результаты:</b>")

        if not results:
            message_parts.append("❌ Ничего не найдено")
        else:
            for idx, result in enumerate(results, 1):
                message_parts.append(f"\n<b>Результат {idx}:</b>")

                if isinstance(result, dict):
                    if result.get('ssn'):
                        message_parts.append(f"SSN: <code>{escape_html(result['ssn'])}</code>")
                    if result.get('dob'):
                        message_parts.append(f"DOB: {escape_html(result['dob'])}")
                    if result.get('phone'):
                        message_parts.append(f"Телефон: {escape_html(result['phone'])}")
                    if result.get('email'):
                        message_parts.append(f"Email: {escape_html(result['email'])}")
                    if result.get('address'):
                        message_parts.append(f"Адрес: {escape_html(result['address'])}")
                else:
                    # Handle object with attributes
                    if hasattr(result, 'ssn') and result.ssn:
                        message_parts.append(f"SSN: <code>{escape_html(result.ssn)}</code>")
                    if hasattr(result, 'dob') and result.dob:
                        message_parts.append(f"DOB: {escape_html(result.dob)}")
                    if hasattr(result, 'phone') and result.phone:
                        message_parts.append(f"Телефон: {escape_html(result.phone)}")
                    if hasattr(result, 'email') and result.email:
                        message_parts.append(f"Email: {escape_html(result.email)}")
                    if hasattr(result, 'address') and result.address:
                        message_parts.append(f"Адрес: {escape_html(result.address)}")

        return "\n".join(message_parts)

    except Exception as e:
        logger.error(f"Error formatting instant SSN result: {e}", exc_info=True)
        return f"{header}\n\n❌ Ошибка форматирования результатов"


def format_manual_ticket_created(header: Optional[str], ticket_id: UUID, ticket_data: dict, status: str) -> str:
    """Format manual ticket creation confirmation.

    Args:
        header: Order header string (may be None for tickets without orders yet).
        ticket_id: Ticket UUID.
        ticket_data: Ticket data dictionary.
        status: Ticket status.

    Returns:
        Formatted confirmation message.
    """
    try:
        short_id = shorten_uuid(str(ticket_id))

        message_parts = []

        if header:
            message_parts.append(f"<b>{escape_html(header)}</b>\n")

        message_parts.append(f"✅ <b>Ручной тикет создан</b>")
        message_parts.append(f"Номер тикета: <code>{short_id}</code>")
        message_parts.append(f"Статус: {escape_html(status)}")

        message_parts.append("\n<b>Данные запроса:</b>")
        if isinstance(ticket_data, dict):
            if ticket_data.get('firstname'):
                message_parts.append(f"Имя: {escape_html(ticket_data['firstname'])} {escape_html(ticket_data.get('lastname', ''))}")
            if ticket_data.get('address'):
                message_parts.append(f"Адрес: {escape_html(ticket_data['address'])}")
        else:
            if hasattr(ticket_data, 'firstname'):
                message_parts.append(f"Имя: {escape_html(ticket_data.firstname)} {escape_html(ticket_data.lastname)}")
            if hasattr(ticket_data, 'address'):
                message_parts.append(f"Адрес: {escape_html(ticket_data.address)}")

        message_parts.append("\n⏳ <i>Ожидаемое время обработки: 5-15 минут</i>")

        return "\n".join(message_parts)

    except Exception as e:
        logger.error(f"Error formatting manual ticket created: {e}", exc_info=True)
        return f"✅ Ручной тикет создан\nНомер тикета: {shorten_uuid(str(ticket_id))}"


def format_manual_ticket_completed(header: str, ticket_data: dict, response_data: dict) -> str:
    """Format manual ticket completion notification.

    Args:
        header: Order header string.
        ticket_data: Original ticket request data.
        response_data: Response data with SSN and other fields.

    Returns:
        Formatted completion message.
    """
    try:
        message_parts = [f"<b>{escape_html(header)}</b>\n"]

        message_parts.append("✅ <b>Ручной тикет завершен</b>\n")

        # Add original request info
        message_parts.append("<b>Запрос:</b>")
        if isinstance(ticket_data, dict):
            if ticket_data.get('firstname'):
                message_parts.append(f"Имя: {escape_html(ticket_data['firstname'])} {escape_html(ticket_data.get('lastname', ''))}")
            if ticket_data.get('address'):
                message_parts.append(f"Адрес: {escape_html(ticket_data['address'])}")

        # Add response data
        message_parts.append("\n<b>Результат:</b>")

        if isinstance(response_data, dict):
            if response_data.get('ssn'):
                message_parts.append(f"SSN: <code>{escape_html(response_data['ssn'])}</code>")
            if response_data.get('dob'):
                message_parts.append(f"DOB: {escape_html(response_data['dob'])}")
            if response_data.get('phone'):
                message_parts.append(f"Телефон: {escape_html(response_data['phone'])}")
            if response_data.get('email'):
                message_parts.append(f"Email: {escape_html(response_data['email'])}")
            if response_data.get('address'):
                message_parts.append(f"Адрес: {escape_html(response_data['address'])}")
        elif isinstance(response_data, str):
            # Handle plain text format
            message_parts.append(escape_html(response_data))

        return "\n".join(message_parts)

    except Exception as e:
        logger.error(f"Error formatting manual ticket completed: {e}", exc_info=True)
        return f"{header}\n\n✅ Ручной тикет завершен"


def format_error_message(error_type: str, details: str) -> str:
    """Format error messages with consistent style.

    Args:
        error_type: Type of error (error, warning).
        details: Error details.

    Returns:
        Formatted error message.
    """
    emoji = "❌" if error_type == "error" else "⚠️"
    return f"{emoji} <b>{escape_html(error_type.upper())}</b>\n{escape_html(details)}"
