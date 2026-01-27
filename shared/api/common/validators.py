"""
Centralized validation module for input data security.

This module provides validation functions for all types of user input
to protect against SQL injection, XSS, and other attacks.

Security:
- All validators return (is_valid, error_message) tuple or raise ValueError
- Validators use whitelists for allowed characters where possible
- Maximum length limits are enforced to prevent DoS attacks
"""
import re
import logging
from typing import Optional, Tuple, Union
from datetime import datetime


logger = logging.getLogger(__name__)


# Constants for validation limits
MAX_NAME_LENGTH = 100
MAX_ADDRESS_LENGTH = 500
MAX_EMAIL_LENGTH = 254
MAX_PHONE_LENGTH = 20
MAX_SSN_LENGTH = 11  # XXX-XX-XXXX
MAX_DOB_LENGTH = 10  # YYYY-MM-DD
MAX_ZIP_LENGTH = 10  # 5 or 9 digits with dash
MAX_STATE_LENGTH = 2
MAX_COUPON_LENGTH = 20
MAX_TELEGRAM_LENGTH = 32
MAX_JABBER_LENGTH = 254
MAX_STRING_LENGTH = 1000
MAX_LIMIT_VALUE = 1000
MAX_METADATA_DEPTH = 5
MAX_METADATA_SIZE = 10000


# Regex patterns
EMAIL_PATTERN = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)
PHONE_PATTERN = re.compile(r'^[\d\s\-\(\)\+\.]+$')
SSN_PATTERN = re.compile(r'^(\d{9}|\d{3}-\d{2}-\d{4})$')
ZIP_PATTERN = re.compile(r'^(\d{5}|\d{5}-\d{4}|\d{9})$')
STATE_PATTERN = re.compile(r'^[A-Z]{2}$')
TELEGRAM_PATTERN = re.compile(r'^@?[a-zA-Z][a-zA-Z0-9_]{4,31}$')
COUPON_PATTERN = re.compile(r'^[A-Z0-9\-]+$')
NAME_PATTERN = re.compile(r"^[a-zA-Z\s\-'\.]+$")
DOB_PATTERN = re.compile(r'^(\d{8}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})$')


def validate_string_length(
    value: str,
    min_len: int,
    max_len: int,
    field_name: str
) -> Tuple[bool, Optional[str]]:
    """
    Validate string length within bounds.

    Args:
        value: String to validate
        min_len: Minimum length (inclusive)
        max_len: Maximum length (inclusive)
        field_name: Field name for error messages

    Returns:
        Tuple of (is_valid, error_message)
    """
    if value is None:
        return False, f"{field_name} is required"

    if not isinstance(value, str):
        return False, f"{field_name} must be a string"

    length = len(value)
    if length < min_len:
        return False, f"{field_name} must be at least {min_len} characters"

    if length > max_len:
        return False, f"{field_name} must be at most {max_len} characters"

    return True, None


def validate_name(value: str, field_name: str = "name") -> Tuple[bool, Optional[str]]:
    """
    Validate name field (firstname, lastname, middlename).

    Allowed characters: letters, spaces, hyphens, apostrophes, periods.
    Length: 2-100 characters.

    Args:
        value: Name to validate
        field_name: Field name for error messages

    Returns:
        Tuple of (is_valid, error_message)

    Security:
        - Only allows safe characters (whitelist approach)
        - Rejects SQL injection attempts
        - Maximum length enforced
    """
    if not value:
        return False, f"{field_name} is required"

    # Check length
    is_valid, error = validate_string_length(value, 2, MAX_NAME_LENGTH, field_name)
    if not is_valid:
        return False, error

    # Check allowed characters
    if not NAME_PATTERN.match(value):
        logger.warning(f"Invalid characters in {field_name}: {value[:50]}...")
        return False, f"{field_name} contains invalid characters. Only letters, spaces, hyphens, apostrophes, and periods are allowed"

    return True, None


def validate_address(value: str) -> Tuple[bool, Optional[str]]:
    """
    Validate address field.

    Length: 10-500 characters.
    Allows most printable characters for addresses.

    Args:
        value: Address to validate

    Returns:
        Tuple of (is_valid, error_message)

    Security:
        - Maximum length enforced to prevent DoS
        - Control characters are rejected
    """
    if not value:
        return False, "Address is required"

    # Check length
    is_valid, error = validate_string_length(value, 10, MAX_ADDRESS_LENGTH, "address")
    if not is_valid:
        return False, error

    # Check for control characters
    if any(ord(c) < 32 and c not in '\n\r\t' for c in value):
        logger.warning(f"Control characters detected in address")
        return False, "Address contains invalid characters"

    return True, None


def validate_email(value: str) -> Tuple[bool, Optional[str]]:
    """
    Validate email address format.

    Args:
        value: Email to validate

    Returns:
        Tuple of (is_valid, error_message)

    Security:
        - Validates format with regex
        - Maximum length enforced (254 chars per RFC)
    """
    if not value:
        return False, "Email is required"

    # Check length
    is_valid, error = validate_string_length(value, 5, MAX_EMAIL_LENGTH, "email")
    if not is_valid:
        return False, error

    # Check format
    if not EMAIL_PATTERN.match(value):
        logger.warning(f"Invalid email format: {value[:30]}...")
        return False, "Invalid email format"

    return True, None


def validate_phone(value: str) -> Tuple[bool, Optional[str]]:
    """
    Validate phone number format.

    Allows: digits, spaces, hyphens, parentheses, plus sign, periods.
    Length: 10-20 digits after cleanup.

    Args:
        value: Phone number to validate

    Returns:
        Tuple of (is_valid, error_message)

    Security:
        - Whitelist of allowed characters
        - Minimum digit count enforced
    """
    if not value:
        return False, "Phone is required"

    # Check length before cleanup
    if len(value) > MAX_PHONE_LENGTH * 2:  # Allow extra chars for formatting
        return False, f"Phone must be at most {MAX_PHONE_LENGTH * 2} characters"

    # Check allowed characters
    if not PHONE_PATTERN.match(value):
        logger.warning(f"Invalid phone format: {value[:20]}...")
        return False, "Phone contains invalid characters"

    # Extract digits and validate count
    digits = ''.join(c for c in value if c.isdigit())
    if len(digits) < 10:
        return False, "Phone must contain at least 10 digits"

    if len(digits) > MAX_PHONE_LENGTH:
        return False, f"Phone must contain at most {MAX_PHONE_LENGTH} digits"

    return True, None


def validate_telegram(value: str) -> Tuple[bool, Optional[str]]:
    """
    Validate Telegram username format.

    Format: @username or username
    Length: 5-32 characters (excluding @)
    Allowed: letters, digits, underscores; must start with letter.

    Args:
        value: Telegram username to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not value:
        return False, "Telegram username is required"

    # Remove leading @ if present
    username = value.lstrip('@')

    # Check length
    is_valid, error = validate_string_length(username, 5, MAX_TELEGRAM_LENGTH, "telegram")
    if not is_valid:
        return False, error

    # Check format
    if not TELEGRAM_PATTERN.match(value):
        logger.warning(f"Invalid telegram format: {value[:32]}")
        return False, "Invalid Telegram username format. Must start with a letter and contain only letters, digits, and underscores"

    return True, None


def validate_jabber(value: str) -> Tuple[bool, Optional[str]]:
    """
    Validate Jabber ID format (similar to email).

    Args:
        value: Jabber ID to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not value:
        return False, "Jabber ID is required"

    # Jabber ID has similar format to email
    return validate_email(value)


def validate_ssn(value: str) -> Tuple[bool, Optional[str]]:
    """
    Validate Social Security Number format.

    Formats accepted:
    - XXXXXXXXX (9 digits)
    - XXX-XX-XXXX (with dashes)

    Args:
        value: SSN to validate

    Returns:
        Tuple of (is_valid, error_message)

    Security:
        - Strict format validation
        - Only digits and dashes allowed
    """
    if not value:
        return False, "SSN is required"

    # Check length
    if len(value) > MAX_SSN_LENGTH:
        return False, f"SSN must be at most {MAX_SSN_LENGTH} characters"

    # Normalize: remove dashes and spaces
    normalized = value.replace('-', '').replace(' ', '')

    # Check if only digits
    if not normalized.isdigit():
        logger.warning(f"Invalid SSN format: non-digit characters detected")
        return False, "SSN must contain only digits and dashes"

    # Check digit count (must be 9 or 4 for last4 search)
    if len(normalized) not in (4, 9):
        return False, "SSN must be 9 digits (or 4 digits for last4 search)"

    return True, None


def validate_dob(value: str) -> Tuple[bool, Optional[str]]:
    """
    Validate date of birth format.

    Formats accepted:
    - YYYYMMDD
    - YYYY-MM-DD
    - MM/DD/YYYY

    Args:
        value: Date of birth to validate

    Returns:
        Tuple of (is_valid, error_message)

    Security:
        - Strict format validation
        - Date range validation (reasonable birth years)
    """
    if not value:
        return False, "Date of birth is required"

    # Check length
    if len(value) > MAX_DOB_LENGTH + 2:  # Allow for different separators
        return False, f"Date of birth must be at most {MAX_DOB_LENGTH + 2} characters"

    # Check format
    if not DOB_PATTERN.match(value):
        logger.warning(f"Invalid DOB format: {value}")
        return False, "Invalid date format. Use YYYYMMDD, YYYY-MM-DD, or MM/DD/YYYY"

    # Try to parse and validate date range
    try:
        # Normalize to digits only
        digits = ''.join(c for c in value if c.isdigit())

        if len(digits) == 8:
            # Check if it's YYYYMMDD or MMDDYYYY based on format
            if '/' in value:  # MM/DD/YYYY
                year = int(digits[4:8])
                month = int(digits[0:2])
                day = int(digits[2:4])
            else:  # YYYYMMDD or YYYY-MM-DD
                year = int(digits[0:4])
                month = int(digits[4:6])
                day = int(digits[6:8])

            # Validate year range (reasonable for birth dates)
            current_year = datetime.now().year
            if year < 1900 or year > current_year:
                return False, f"Birth year must be between 1900 and {current_year}"

            # Validate month and day
            if month < 1 or month > 12:
                return False, "Invalid month in date of birth"

            if day < 1 or day > 31:
                return False, "Invalid day in date of birth"

    except (ValueError, IndexError):
        return False, "Invalid date of birth"

    return True, None


def validate_zip(value: str) -> Tuple[bool, Optional[str]]:
    """
    Validate ZIP code format.

    Formats accepted:
    - XXXXX (5 digits)
    - XXXXX-XXXX (ZIP+4)
    - XXXXXXXXX (9 digits without dash)

    Args:
        value: ZIP code to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not value:
        return False, "ZIP code is required"

    # Check length
    if len(value) > MAX_ZIP_LENGTH:
        return False, f"ZIP code must be at most {MAX_ZIP_LENGTH} characters"

    # Check format
    if not ZIP_PATTERN.match(value):
        logger.warning(f"Invalid ZIP format: {value}")
        return False, "Invalid ZIP code format. Use 5 or 9 digits"

    return True, None


def validate_state(value: str) -> Tuple[bool, Optional[str]]:
    """
    Validate US state code format.

    Format: 2 uppercase letters (e.g., CA, NY, TX)

    Args:
        value: State code to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not value:
        return False, "State is required"

    # Normalize to uppercase
    normalized = value.upper().strip()

    # Check format
    if not STATE_PATTERN.match(normalized):
        logger.warning(f"Invalid state format: {value}")
        return False, "State must be 2 uppercase letters"

    return True, None


def validate_coupon_code(value: str) -> Tuple[bool, Optional[str]]:
    """
    Validate coupon code format.

    Format: Alphanumeric with dashes, uppercase.
    Length: 1-20 characters.

    Args:
        value: Coupon code to validate

    Returns:
        Tuple of (is_valid, error_message)

    Security:
        - Whitelist of allowed characters
        - Maximum length enforced
    """
    if not value:
        return False, "Coupon code is required"

    # Normalize to uppercase
    normalized = value.upper().strip()

    # Check length
    is_valid, error = validate_string_length(normalized, 1, MAX_COUPON_LENGTH, "coupon code")
    if not is_valid:
        return False, error

    # Check format
    if not COUPON_PATTERN.match(normalized):
        logger.warning(f"Invalid coupon code format: {value[:20]}")
        return False, "Coupon code must contain only letters, digits, and dashes"

    return True, None


def validate_limit(value: Union[int, str, None], max_limit: int = MAX_LIMIT_VALUE) -> Tuple[bool, Optional[str]]:
    """
    Validate LIMIT parameter for SQL queries.

    Args:
        value: Limit value to validate
        max_limit: Maximum allowed limit (default 1000)

    Returns:
        Tuple of (is_valid, error_message)

    Security:
        - Ensures positive integer
        - Maximum value enforced to prevent DoS
        - Rejects non-numeric input
    """
    if value is None:
        return True, None  # None is valid (no limit)

    # Convert to int if string
    try:
        limit = int(value)
    except (ValueError, TypeError):
        logger.warning(f"Invalid limit value: {value}")
        return False, "Limit must be a positive integer"

    # Check range
    if limit < 1:
        return False, "Limit must be a positive integer"

    if limit > max_limit:
        return False, f"Limit must be at most {max_limit}"

    return True, None


def validate_amount(
    value: Union[float, int, str],
    min_amount: float = 0.01,
    max_amount: float = 100000.00
) -> Tuple[bool, Optional[str]]:
    """
    Validate monetary amount.

    Args:
        value: Amount to validate
        min_amount: Minimum allowed amount
        max_amount: Maximum allowed amount

    Returns:
        Tuple of (is_valid, error_message)

    Security:
        - Ensures valid numeric value
        - Range validation
    """
    try:
        amount = float(value)
    except (ValueError, TypeError):
        return False, "Amount must be a number"

    if amount < min_amount:
        return False, f"Amount must be at least {min_amount}"

    if amount > max_amount:
        return False, f"Amount must be at most {max_amount}"

    return True, None


def validate_no_sql_injection(value: str, field_name: str = "input") -> Tuple[bool, Optional[str]]:
    """
    Check for common SQL injection patterns.

    This is a secondary defense layer - parameterized queries are the primary defense.

    Args:
        value: String to check
        field_name: Field name for error messages

    Returns:
        Tuple of (is_valid, error_message)

    Security:
        - Detects common SQL injection patterns
        - Logs suspicious input for monitoring
    """
    if not value:
        return True, None

    # Convert to lowercase for pattern matching
    lower_value = value.lower()

    # Common SQL injection patterns
    suspicious_patterns = [
        "' or ",
        "' and ",
        "'; --",
        "'; drop",
        "'; delete",
        "'; update",
        "'; insert",
        "' union ",
        "1=1",
        "1'='1",
        "or 1=1",
        "/*",
        "*/",
        "xp_",
        "exec(",
        "execute(",
        "char(",
        "convert(",
        "cast(",
    ]

    for pattern in suspicious_patterns:
        if pattern in lower_value:
            logger.warning(f"Potential SQL injection detected in {field_name}: {value[:100]}...")
            return False, f"Invalid characters in {field_name}"

    return True, None


def safe_int(value: Union[int, str, None], default: int = 0, max_value: int = MAX_LIMIT_VALUE) -> int:
    """
    Safely convert value to integer with bounds checking.

    Args:
        value: Value to convert
        default: Default value if conversion fails
        max_value: Maximum allowed value

    Returns:
        Safe integer value within bounds

    Security:
        - Prevents integer overflow
        - Returns safe default on invalid input
    """
    if value is None:
        return default

    try:
        result = int(value)
        if result < 0:
            return default
        if result > max_value:
            return max_value
        return result
    except (ValueError, TypeError):
        logger.warning(f"Failed to convert to int: {value}")
        return default
