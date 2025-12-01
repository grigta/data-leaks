"""Message parsing utilities."""
import logging
import re
from typing import Optional
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass
class TicketData:
    """Ticket data structure."""
    firstname: str
    lastname: str
    address: str
    phone: Optional[str] = None
    dob: Optional[str] = None
    ssn: Optional[str] = None
    dob_str: Optional[str] = None
    phone_str: Optional[str] = None
    email: Optional[str] = None


def extract_mention_text(message_text: str, bot_username: str) -> Optional[str]:
    """Extract text after bot mention.

    Args:
        message_text: Message text.
        bot_username: Bot username.

    Returns:
        Text after mention or None if no mention found.
    """
    try:
        mention = f"@{bot_username}"

        if mention not in message_text:
            return None

        # Remove mention and get remaining text
        text = message_text.replace(mention, "").strip()

        if not text:
            return None

        logger.debug(f"Extracted text after mention: {text[:50]}...")
        return text
    except Exception as e:
        logger.error(f"Error extracting mention text: {e}", exc_info=True)
        return None


def extract_labeled_field(text: str, labels: list[str]) -> Optional[str]:
    """Extract value from labeled field format.

    Args:
        text: Text to search in.
        labels: List of possible label names (e.g., ['Name', 'Full Name']).

    Returns:
        Extracted value or None.
    """
    for label in labels:
        pattern = rf"{label}\s*[:\-]\s*(.+?)(?:\n|$)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def normalize_name(name: str) -> tuple[Optional[str], Optional[str]]:
    """Parse name in various formats.

    Args:
        name: Name string (e.g., "John Doe", "Doe, John").

    Returns:
        Tuple of (firstname, lastname) or (None, None).
    """
    if not name:
        return None, None

    # Handle "Last, First" format
    if ',' in name:
        parts = [p.strip() for p in name.split(',')]
        if len(parts) >= 2:
            return parts[1], parts[0]

    # Handle "First Last" format
    parts = name.split()
    if len(parts) >= 2:
        return parts[0], parts[1]

    return None, None


def extract_ssn_pattern(text: str) -> Optional[str]:
    """Extract SSN from text using regex.

    Args:
        text: Text to search in.

    Returns:
        SSN string or None.
    """
    # Pattern: XXX-XX-XXXX or XXXXXXXXX
    pattern = r'\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b'
    match = re.search(pattern, text)
    return match.group(0) if match else None


def extract_dob_pattern(text: str) -> Optional[str]:
    """Extract date of birth from text.

    Args:
        text: Text to search in.

    Returns:
        DOB string or None.
    """
    # Patterns: MM/DD/YYYY, MM-DD-YYYY, YYYY-MM-DD
    patterns = [
        r'\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b',
        r'\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b'
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def parse_flexible_format(text: str) -> Optional[TicketData]:
    """Parse ticket data with flexible format support.

    Supports multiple formats:
    - Labeled fields: "Name: John Doe\\nAddress: 123 Main St"
    - Simple format: "John Doe\\n123 Main St"
    - Extended format with SSN, DOB, phone, email

    Args:
        text: Message text to parse.

    Returns:
        TicketData object or None if parsing failed.
    """
    try:
        logger.info(f"Parsing with flexible format: {text[:200]}")

        # Strategy 1: Try labeled fields
        name = extract_labeled_field(text, ['Name', 'Full Name', 'FullName', 'Firstname Lastname'])
        address = extract_labeled_field(text, ['Address', 'Addr'])
        phone = extract_labeled_field(text, ['Phone', 'Tel', 'Telephone'])
        dob = extract_labeled_field(text, ['DOB', 'Date of Birth', 'Birth Date', 'BirthDate'])
        ssn = extract_labeled_field(text, ['SSN', 'Social Security'])
        email = extract_labeled_field(text, ['Email', 'E-mail'])

        # If name and address found via labels, use this strategy
        if name and address:
            firstname, lastname = normalize_name(name)
            if firstname and lastname:
                logger.info("Parsed using labeled fields strategy")
                return TicketData(
                    firstname=firstname,
                    lastname=lastname,
                    address=address,
                    phone=phone,
                    dob=dob,
                    ssn=ssn,
                    dob_str=dob,
                    phone_str=phone,
                    email=email
                )

        # Strategy 2: Try pattern extraction for SSN/DOB if present
        if not ssn:
            ssn = extract_ssn_pattern(text)
        if not dob:
            dob = extract_dob_pattern(text)

        # Strategy 3: Fall back to simple line-based format
        lines = [line.strip() for line in text.strip().split('\n') if line.strip()]

        if len(lines) < 2:
            logger.warning(f"Not enough lines in message: {len(lines)}")
            return None

        # Parse first line: firstname lastname
        name_parts = lines[0].split()
        if len(name_parts) < 2:
            logger.warning(f"Invalid name format: {lines[0]}")
            return None

        firstname = name_parts[0]
        lastname = name_parts[1]

        # Parse second line: address
        address = lines[1]

        # Optional: phone and dob from remaining lines if not already found
        if not phone and len(lines) > 2:
            phone = lines[2]
        if not dob and len(lines) > 3:
            dob = lines[3]

        # Validate minimum requirements
        if not firstname or not lastname or not address:
            logger.warning("Missing required fields")
            return None

        logger.info(f"Parsed ticket data (simple format): {firstname} {lastname}")
        return TicketData(
            firstname=firstname,
            lastname=lastname,
            address=address,
            phone=phone,
            dob=dob,
            ssn=ssn,
            dob_str=dob,
            phone_str=phone,
            email=email
        )

    except Exception as e:
        logger.error(f"Error in flexible parsing: {e}", exc_info=True)
        return None


def parse_ticket_message(text: str) -> Optional[TicketData]:
    """Parse ticket data from message text.

    Expected format:
        Firstname Lastname
        Address line 1, City, State ZIP
        Phone (optional)
        DOB (optional)

    Args:
        text: Message text to parse.

    Returns:
        TicketData object or None if parsing failed.
    """
    try:
        logger.info(f"Parsing ticket message: {text[:200]}")

        # Try flexible parser first
        result = parse_flexible_format(text)
        if result:
            return result

        # Fallback to original simple parser
        lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
        logger.info(f"Split into {len(lines)} lines: {lines}")

        if len(lines) < 2:
            logger.warning(f"Not enough lines in message: {len(lines)}")
            return None

        # Parse first line: firstname lastname
        name_parts = lines[0].split()
        if len(name_parts) < 2:
            logger.warning(f"Invalid name format: {lines[0]}")
            return None

        firstname = name_parts[0]
        lastname = name_parts[1]

        # Parse second line: address
        address = lines[1]

        # Optional: phone and dob
        phone = lines[2] if len(lines) > 2 else None
        dob = lines[3] if len(lines) > 3 else None

        # Validate minimum requirements
        if not firstname or not lastname or not address:
            logger.warning("Missing required fields")
            return None

        ticket_data = TicketData(
            firstname=firstname,
            lastname=lastname,
            address=address,
            phone=phone,
            dob=dob
        )

        logger.info(f"Parsed ticket data: {firstname} {lastname}")
        return ticket_data

    except Exception as e:
        logger.error(f"Error parsing ticket message: {e}", exc_info=True)
        return None
