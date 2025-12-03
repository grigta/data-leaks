"""
Centralized sanitization module for input data security.

This module provides sanitization functions to clean and normalize user input
before storing in the database or using in queries.

Security:
- All sanitizers return clean values or None on invalid input
- Sanitizers remove potentially dangerous characters
- Output length is always bounded
"""
import re
import logging
import html
from typing import Any, Dict, Optional, Union


logger = logging.getLogger(__name__)


# Constants for sanitization limits
MAX_STRING_LENGTH = 1000
MAX_NAME_LENGTH = 100
MAX_ADDRESS_LENGTH = 500
MAX_EMAIL_LENGTH = 254
MAX_PHONE_LENGTH = 20
MAX_SSN_LENGTH = 11
MAX_METADATA_DEPTH = 5
MAX_METADATA_SIZE = 10000
MAX_KEY_LENGTH = 100
MAX_VALUE_LENGTH = 1000


def remove_control_chars(value: str) -> str:
    """
    Remove control characters from string.

    Keeps: printable ASCII, newlines, tabs, carriage returns.
    Removes: \x00-\x08, \x0b, \x0c, \x0e-\x1f

    Args:
        value: String to clean

    Returns:
        String without control characters
    """
    if not value:
        return value

    # Keep printable chars, newline, tab, carriage return
    return ''.join(
        c for c in value
        if c >= ' ' or c in '\n\r\t'
    )


def normalize_whitespace(value: str) -> str:
    """
    Normalize whitespace in string.

    Replaces multiple spaces/tabs with single space.
    Strips leading/trailing whitespace.

    Args:
        value: String to normalize

    Returns:
        String with normalized whitespace
    """
    if not value:
        return value

    # Replace multiple whitespace with single space
    normalized = re.sub(r'\s+', ' ', value)
    return normalized.strip()


def truncate_string(value: str, max_length: int, suffix: str = '...') -> str:
    """
    Safely truncate string to maximum length.

    Args:
        value: String to truncate
        max_length: Maximum length (including suffix)
        suffix: Suffix to add if truncated (default: '...')

    Returns:
        Truncated string
    """
    if not value:
        return value

    if len(value) <= max_length:
        return value

    # Ensure suffix fits within max_length
    if len(suffix) >= max_length:
        return value[:max_length]

    return value[:max_length - len(suffix)] + suffix


def sanitize_string(value: Optional[str], max_length: int = MAX_STRING_LENGTH) -> Optional[str]:
    """
    Basic string sanitization.

    Operations:
    1. Remove control characters
    2. Normalize whitespace
    3. Truncate to max length

    Args:
        value: String to sanitize
        max_length: Maximum output length

    Returns:
        Sanitized string or None if input is None/empty
    """
    if value is None:
        return None

    if not isinstance(value, str):
        try:
            value = str(value)
        except (ValueError, TypeError):
            return None

    # Remove control characters
    clean = remove_control_chars(value)

    # Normalize whitespace
    clean = normalize_whitespace(clean)

    # Truncate if needed
    if len(clean) > max_length:
        clean = truncate_string(clean, max_length)

    # Return None if empty after sanitization
    return clean if clean else None


def sanitize_html(value: Optional[str]) -> Optional[str]:
    """
    Escape HTML special characters.

    Escapes: <, >, &, ", '

    Args:
        value: String to sanitize

    Returns:
        HTML-escaped string
    """
    if value is None:
        return None

    if not isinstance(value, str):
        try:
            value = str(value)
        except (ValueError, TypeError):
            return None

    return html.escape(value, quote=True)


def sanitize_sql_like_pattern(value: Optional[str]) -> Optional[str]:
    """
    Escape SQL LIKE wildcard characters for safe use in LIKE queries.

    Escapes: %, _, [, ]

    This is for use in LIKE patterns where you want literal matching.
    The primary defense is still parameterized queries.

    Args:
        value: String to sanitize

    Returns:
        String with escaped LIKE wildcards
    """
    if value is None:
        return None

    if not isinstance(value, str):
        try:
            value = str(value)
        except (ValueError, TypeError):
            return None

    # Escape LIKE wildcards
    # Note: Use ESCAPE clause in SQL: WHERE col LIKE ? ESCAPE '\'
    escaped = value.replace('\\', '\\\\')  # Escape backslash first
    escaped = escaped.replace('%', '\\%')
    escaped = escaped.replace('_', '\\_')
    escaped = escaped.replace('[', '\\[')
    escaped = escaped.replace(']', '\\]')

    return escaped


def sanitize_name(value: Optional[str]) -> Optional[str]:
    """
    Sanitize and normalize name field.

    Operations:
    1. Strip whitespace
    2. Remove control characters
    3. Normalize to title case (optional, can be disabled)
    4. Remove multiple spaces
    5. Truncate to max length

    Args:
        value: Name to sanitize

    Returns:
        Sanitized name or None
    """
    if value is None:
        return None

    # Basic sanitization
    clean = sanitize_string(value, MAX_NAME_LENGTH)
    if not clean:
        return None

    # Don't change case - preserve original
    # (some names have specific capitalization)

    return clean


def sanitize_address(value: Optional[str]) -> Optional[str]:
    """
    Sanitize and normalize address field.

    Operations:
    1. Strip whitespace
    2. Remove control characters
    3. Normalize to uppercase (standard for addresses)
    4. Remove multiple spaces
    5. Truncate to max length

    Args:
        value: Address to sanitize

    Returns:
        Sanitized address or None
    """
    if value is None:
        return None

    # Basic sanitization
    clean = sanitize_string(value, MAX_ADDRESS_LENGTH)
    if not clean:
        return None

    # Convert to uppercase (standard for US addresses)
    clean = clean.upper()

    return clean


def sanitize_email(value: Optional[str]) -> Optional[str]:
    """
    Sanitize and normalize email address.

    Operations:
    1. Strip whitespace
    2. Convert to lowercase
    3. Remove control characters
    4. Truncate to max length

    Args:
        value: Email to sanitize

    Returns:
        Sanitized email or None
    """
    if value is None:
        return None

    # Basic sanitization (but preserve case for local part initially)
    clean = sanitize_string(value, MAX_EMAIL_LENGTH)
    if not clean:
        return None

    # Convert to lowercase
    clean = clean.lower()

    return clean


def sanitize_phone(value: Optional[str]) -> Optional[str]:
    """
    Sanitize and normalize phone number.

    Operations:
    1. Remove all characters except digits and +
    2. Truncate to max length

    Args:
        value: Phone to sanitize

    Returns:
        Sanitized phone (digits and + only) or None
    """
    if value is None:
        return None

    if not isinstance(value, str):
        try:
            value = str(value)
        except (ValueError, TypeError):
            return None

    # Keep only digits and +
    clean = ''.join(c for c in value if c.isdigit() or c == '+')

    # Truncate
    if len(clean) > MAX_PHONE_LENGTH:
        clean = clean[:MAX_PHONE_LENGTH]

    return clean if clean else None


def sanitize_ssn(value: Optional[str]) -> Optional[str]:
    """
    Sanitize and normalize SSN.

    Operations:
    1. Remove all characters except digits
    2. Format as XXX-XX-XXXX (if 9 digits)
    3. Keep as-is if 4 digits (last4 search)

    Args:
        value: SSN to sanitize

    Returns:
        Sanitized SSN or None
    """
    if value is None:
        return None

    if not isinstance(value, str):
        try:
            value = str(value)
        except (ValueError, TypeError):
            return None

    # Keep only digits
    digits = ''.join(c for c in value if c.isdigit())

    # Format based on length
    if len(digits) == 9:
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    elif len(digits) == 4:
        return digits  # Last 4 digits search
    elif len(digits) > 9:
        # Too many digits - truncate and format
        digits = digits[:9]
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    else:
        # Invalid length
        logger.warning(f"Invalid SSN length after sanitization: {len(digits)} digits")
        return None


def sanitize_metadata(
    data: Any,
    max_depth: int = MAX_METADATA_DEPTH,
    max_size: int = MAX_METADATA_SIZE,
    current_depth: int = 0
) -> Optional[Dict[str, Any]]:
    """
    Recursively sanitize metadata dictionary.

    Operations:
    1. Limit nesting depth
    2. Sanitize all string values
    3. Limit key and value lengths
    4. Remove None values
    5. Limit total size

    Args:
        data: Data to sanitize (dict, list, or primitive)
        max_depth: Maximum nesting depth
        max_size: Maximum total size in bytes (approximate)
        current_depth: Current recursion depth

    Returns:
        Sanitized data or None if invalid
    """
    if data is None:
        return None

    # Check depth limit - return truncated value instead of None
    if current_depth > max_depth:
        logger.warning(f"Metadata depth limit exceeded: {current_depth}")
        # Return a placeholder indicating truncation
        if isinstance(data, str):
            return sanitize_string(data, MAX_VALUE_LENGTH)
        elif isinstance(data, (bool, int, float)):
            return data
        elif isinstance(data, dict):
            return {"_truncated": True}
        elif isinstance(data, list):
            return ["_truncated"]
        else:
            return "_truncated"

    # Handle different types
    if isinstance(data, dict):
        result = {}
        total_size = 0

        for key, value in data.items():
            # Sanitize key
            if not isinstance(key, str):
                key = str(key)

            if len(key) > MAX_KEY_LENGTH:
                key = key[:MAX_KEY_LENGTH]

            # Skip keys with control characters
            if any(ord(c) < 32 for c in key):
                continue

            # Recursively sanitize value
            sanitized_value = sanitize_metadata(
                value,
                max_depth,
                max_size - total_size,
                current_depth + 1
            )

            if sanitized_value is not None or (isinstance(value, (bool, int, float)) and value == sanitized_value):
                result[key] = sanitized_value

                # Approximate size tracking
                total_size += len(key) + len(str(sanitized_value))
                if total_size > max_size:
                    logger.warning(f"Metadata size limit exceeded: {total_size}")
                    break

        return result if result else None

    elif isinstance(data, list):
        result = []
        total_size = 0

        for item in data:
            sanitized_item = sanitize_metadata(
                item,
                max_depth,
                max_size - total_size,
                current_depth + 1
            )

            if sanitized_item is not None:
                result.append(sanitized_item)

                # Approximate size tracking
                total_size += len(str(sanitized_item))
                if total_size > max_size:
                    logger.warning(f"Metadata list size limit exceeded: {total_size}")
                    break

        return result if result else None

    elif isinstance(data, str):
        # Sanitize string
        sanitized = sanitize_string(data, MAX_VALUE_LENGTH)
        return sanitized

    elif isinstance(data, (bool, int, float)):
        # Primitives are safe
        return data

    else:
        # Unknown type - convert to string
        try:
            return sanitize_string(str(data), MAX_VALUE_LENGTH)
        except (ValueError, TypeError):
            return None


def sanitize_for_logging(value: Any, max_length: int = 100) -> str:
    """
    Sanitize value for safe logging.

    Masks sensitive data patterns and truncates long values.

    Args:
        value: Value to sanitize for logging
        max_length: Maximum output length

    Returns:
        Safe string for logging
    """
    if value is None:
        return "None"

    try:
        str_value = str(value)
    except (ValueError, TypeError):
        return "<non-serializable>"

    # Mask potential sensitive data

    # Mask SSN patterns
    str_value = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '***-**-****', str_value)
    str_value = re.sub(r'\b\d{9}\b', '*********', str_value)

    # Mask email local part
    str_value = re.sub(
        r'\b([a-zA-Z0-9._%+-])[a-zA-Z0-9._%+-]*@',
        r'\1***@',
        str_value
    )

    # Mask phone numbers (keep last 4)
    str_value = re.sub(
        r'\b(\+?1?[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?(\d{4})\b',
        r'***-***-\2',
        str_value
    )

    # Truncate if needed
    if len(str_value) > max_length:
        str_value = str_value[:max_length - 3] + '...'

    return str_value


def sanitize_filename(value: Optional[str], max_length: int = 255) -> Optional[str]:
    """
    Sanitize filename for safe file system operations.

    Removes path separators and special characters.

    Args:
        value: Filename to sanitize
        max_length: Maximum filename length

    Returns:
        Safe filename or None
    """
    if value is None:
        return None

    if not isinstance(value, str):
        try:
            value = str(value)
        except (ValueError, TypeError):
            return None

    # Remove path separators
    clean = value.replace('/', '_').replace('\\', '_')

    # Remove other dangerous characters
    clean = re.sub(r'[<>:"|?*\x00-\x1f]', '_', clean)

    # Remove leading/trailing dots and spaces
    clean = clean.strip('. ')

    # Truncate
    if len(clean) > max_length:
        # Preserve extension if present
        if '.' in clean:
            name, ext = clean.rsplit('.', 1)
            max_name_len = max_length - len(ext) - 1
            if max_name_len > 0:
                clean = name[:max_name_len] + '.' + ext
            else:
                clean = clean[:max_length]
        else:
            clean = clean[:max_length]

    return clean if clean else None
