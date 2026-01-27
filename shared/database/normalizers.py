"""
Address and name normalization utilities for SSN search.

This module provides functions to normalize addresses and names
to improve matching accuracy between external API data and local database.
"""

import re
from typing import Optional, Tuple


# =============================================================================
# Address Normalization
# =============================================================================

# Direction mappings (full -> abbreviated)
DIRECTION_MAP = {
    'NORTH': 'N',
    'SOUTH': 'S',
    'EAST': 'E',
    'WEST': 'W',
    'NORTHEAST': 'NE',
    'NORTHWEST': 'NW',
    'SOUTHEAST': 'SE',
    'SOUTHWEST': 'SW',
}

# Reverse direction mappings (abbreviated -> full) for matching both ways
DIRECTION_MAP_REVERSE = {v: k for k, v in DIRECTION_MAP.items()}

# Street type mappings (full -> abbreviated)
STREET_TYPE_MAP = {
    'STREET': 'ST',
    'AVENUE': 'AVE',
    'ROAD': 'RD',
    'DRIVE': 'DR',
    'LANE': 'LN',
    'COURT': 'CT',
    'CIRCLE': 'CIR',
    'BOULEVARD': 'BLVD',
    'PLACE': 'PL',
    'TERRACE': 'TER',
    'TRAIL': 'TRL',
    'WAY': 'WAY',
    'PARKWAY': 'PKWY',
    'HIGHWAY': 'HWY',
    'EXPRESSWAY': 'EXPY',
    'FREEWAY': 'FWY',
    'TURNPIKE': 'TPKE',
    'PIKE': 'PIKE',
    'SQUARE': 'SQ',
    'LOOP': 'LOOP',
    'ALLEY': 'ALY',
    'CROSSING': 'XING',
    'POINT': 'PT',
    'GROVE': 'GRV',
    'HEIGHTS': 'HTS',
    'HILLS': 'HLS',
    'HOLLOW': 'HOLW',
    'JUNCTION': 'JCT',
    'LANDING': 'LNDG',
    'MEADOW': 'MDW',
    'MEADOWS': 'MDWS',
    'PASS': 'PASS',
    'PATH': 'PATH',
    'RIDGE': 'RDG',
    'RUN': 'RUN',
    'VALLEY': 'VLY',
    'VIEW': 'VW',
    'VILLAGE': 'VLG',
    'WALK': 'WALK',
}

# Reverse street type mappings
STREET_TYPE_MAP_REVERSE = {v: k for k, v in STREET_TYPE_MAP.items()}

# Unit/apartment indicators to remove
UNIT_PATTERNS = [
    r'\s+APT\.?\s*#?\s*\S+',
    r'\s+APARTMENT\.?\s*#?\s*\S+',
    r'\s+UNIT\.?\s*#?\s*\S+',
    r'\s+SUITE\.?\s*#?\s*\S+',
    r'\s+STE\.?\s*#?\s*\S+',
    r'\s+#\s*\S+',
    r'\s+BLDG\.?\s*#?\s*\S+',
    r'\s+BUILDING\.?\s*#?\s*\S+',
    r'\s+FL\.?\s*#?\s*\d+',
    r'\s+FLOOR\.?\s*#?\s*\d+',
    r'\s+RM\.?\s*#?\s*\S+',
    r'\s+ROOM\.?\s*#?\s*\S+',
]


def normalize_address(address: str) -> str:
    """
    Normalize street address for consistent matching.

    Normalizations applied:
    1. Convert to uppercase
    2. Remove extra whitespace
    3. Standardize directions (NORTH -> N, etc.)
    4. Standardize street types (STREET -> ST, etc.)
    5. Remove unit/apartment numbers
    6. Remove punctuation (except hyphens in house numbers)

    Args:
        address: Raw street address

    Returns:
        Normalized address string
    """
    if not address:
        return ''

    # Convert to uppercase and strip
    normalized = address.upper().strip()

    # Remove common punctuation (keep hyphens for house numbers like 123-A)
    normalized = re.sub(r'[.,;:\'\"!?()]', '', normalized)

    # Remove unit/apartment patterns
    for pattern in UNIT_PATTERNS:
        normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

    # Normalize multiple spaces to single space
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    # Standardize directions - replace full words with abbreviations
    words = normalized.split()
    normalized_words = []
    for word in words:
        if word in DIRECTION_MAP:
            normalized_words.append(DIRECTION_MAP[word])
        elif word in STREET_TYPE_MAP:
            normalized_words.append(STREET_TYPE_MAP[word])
        else:
            normalized_words.append(word)

    return ' '.join(normalized_words)


def extract_street_number(address: str) -> Optional[str]:
    """
    Extract the street number from an address.

    Args:
        address: Street address

    Returns:
        Street number or None if not found
    """
    if not address:
        return None

    # Match patterns like: 123, 123A, 123-A, 12345
    match = re.match(r'^(\d+[A-Z]?(?:-[A-Z0-9]+)?)\s', address.upper())
    if match:
        return match.group(1)
    return None


def extract_street_name(address: str) -> str:
    """
    Extract the street name without number and unit.

    Args:
        address: Street address

    Returns:
        Street name portion
    """
    if not address:
        return ''

    normalized = normalize_address(address)

    # Remove leading street number
    normalized = re.sub(r'^\d+[A-Z]?(?:-[A-Z0-9]+)?\s+', '', normalized)

    return normalized


def addresses_match(addr1: str, addr2: str, fuzzy: bool = False) -> bool:
    """
    Check if two addresses match after normalization.

    Args:
        addr1: First address
        addr2: Second address
        fuzzy: If True, use fuzzy matching (street number + partial street name)

    Returns:
        True if addresses match
    """
    norm1 = normalize_address(addr1)
    norm2 = normalize_address(addr2)

    # Exact match after normalization
    if norm1 == norm2:
        return True

    # Check if one contains the other (for partial addresses)
    if norm1 in norm2 or norm2 in norm1:
        return True

    if fuzzy:
        # Extract street numbers
        num1 = extract_street_number(addr1)
        num2 = extract_street_number(addr2)

        # If both have street numbers and they don't match, not the same address
        if num1 and num2 and num1 != num2:
            return False

        # Extract street names
        name1 = extract_street_name(addr1)
        name2 = extract_street_name(addr2)

        # Check if street names have significant overlap
        words1 = set(name1.split())
        words2 = set(name2.split())

        # Remove common words that don't help matching
        common_words = {'ST', 'AVE', 'RD', 'DR', 'LN', 'CT', 'N', 'S', 'E', 'W', 'NE', 'NW', 'SE', 'SW'}
        words1 = words1 - common_words
        words2 = words2 - common_words

        # Check for overlap
        if words1 and words2:
            overlap = words1 & words2
            if len(overlap) >= 1:  # At least one significant word matches
                return True

    return False


def generate_address_variants(address: str) -> list:
    """
    Generate multiple variants of an address for searching.

    This helps match addresses stored in different formats.

    Args:
        address: Original address

    Returns:
        List of address variants to try
    """
    if not address:
        return []

    variants = []
    normalized = normalize_address(address)
    variants.append(normalized)

    # Also try with full direction/street type names
    words = normalized.split()
    full_variant_words = []
    for word in words:
        if word in DIRECTION_MAP_REVERSE:
            full_variant_words.append(DIRECTION_MAP_REVERSE[word])
        elif word in STREET_TYPE_MAP_REVERSE:
            full_variant_words.append(STREET_TYPE_MAP_REVERSE[word])
        else:
            full_variant_words.append(word)

    full_variant = ' '.join(full_variant_words)
    if full_variant != normalized:
        variants.append(full_variant)

    # Extract just street number + first word of street name (most basic match)
    street_num = extract_street_number(address)
    if street_num:
        street_name = extract_street_name(address)
        if street_name:
            first_word = street_name.split()[0] if street_name.split() else ''
            if first_word and first_word not in {'N', 'S', 'E', 'W', 'NE', 'NW', 'SE', 'SW'}:
                basic_variant = f"{street_num} {first_word}"
                variants.append(basic_variant)

    return variants


# =============================================================================
# Name Normalization
# =============================================================================

# Common nickname mappings (nickname -> canonical name)
NICKNAME_MAP = {
    # Male names
    'BOB': 'ROBERT',
    'BOBBY': 'ROBERT',
    'ROB': 'ROBERT',
    'ROBBY': 'ROBERT',
    'ROBBIE': 'ROBERT',
    'BERT': 'ROBERT',

    'BILL': 'WILLIAM',
    'BILLY': 'WILLIAM',
    'WILL': 'WILLIAM',
    'WILLY': 'WILLIAM',
    'WILLIE': 'WILLIAM',
    'LIAM': 'WILLIAM',

    'MIKE': 'MICHAEL',
    'MIKEY': 'MICHAEL',
    'MICK': 'MICHAEL',
    'MICKEY': 'MICHAEL',

    'JIM': 'JAMES',
    'JIMMY': 'JAMES',
    'JAMIE': 'JAMES',

    'DICK': 'RICHARD',
    'RICK': 'RICHARD',
    'RICKY': 'RICHARD',
    'RICH': 'RICHARD',
    'RICHIE': 'RICHARD',

    'TOM': 'THOMAS',
    'TOMMY': 'THOMAS',
    'THOM': 'THOMAS',

    'CHUCK': 'CHARLES',
    'CHARLIE': 'CHARLES',
    'CHAS': 'CHARLES',

    'JACK': 'JOHN',
    'JOHNNY': 'JOHN',
    'JON': 'JOHN',

    'JOE': 'JOSEPH',
    'JOEY': 'JOSEPH',

    'TONY': 'ANTHONY',

    'ED': 'EDWARD',
    'EDDIE': 'EDWARD',
    'TED': 'EDWARD',
    'TEDDY': 'EDWARD',
    'NED': 'EDWARD',

    'STEVE': 'STEVEN',
    'STEVIE': 'STEVEN',
    'STEPHEN': 'STEVEN',

    'DAN': 'DANIEL',
    'DANNY': 'DANIEL',

    'DAVE': 'DAVID',
    'DAVY': 'DAVID',

    'MATT': 'MATTHEW',
    'MATTY': 'MATTHEW',

    'CHRIS': 'CHRISTOPHER',
    'KIT': 'CHRISTOPHER',

    'ALEX': 'ALEXANDER',
    'AL': 'ALEXANDER',
    'XANDER': 'ALEXANDER',

    'ANDY': 'ANDREW',
    'DREW': 'ANDREW',

    'NICK': 'NICHOLAS',
    'NICKY': 'NICHOLAS',

    'PETE': 'PETER',
    'PETEY': 'PETER',

    'PHIL': 'PHILIP',

    'BEN': 'BENJAMIN',
    'BENNY': 'BENJAMIN',
    'BENJI': 'BENJAMIN',

    'JEFF': 'JEFFREY',
    'GEOFF': 'GEOFFREY',

    'GREG': 'GREGORY',

    'JERRY': 'GERALD',

    'LARRY': 'LAWRENCE',

    'HARRY': 'HAROLD',
    'HAL': 'HAROLD',

    'HANK': 'HENRY',

    'KEN': 'KENNETH',
    'KENNY': 'KENNETH',

    'RON': 'RONALD',
    'RONNIE': 'RONALD',

    'RAY': 'RAYMOND',

    'SAM': 'SAMUEL',
    'SAMMY': 'SAMUEL',

    'TIM': 'TIMOTHY',
    'TIMMY': 'TIMOTHY',

    'GENE': 'EUGENE',

    'FRANK': 'FRANCIS',
    'FRANKIE': 'FRANCIS',
    'FRAN': 'FRANCIS',

    'FRED': 'FREDERICK',
    'FREDDY': 'FREDERICK',
    'FREDDIE': 'FREDERICK',

    # Female names
    'LIZ': 'ELIZABETH',
    'LIZZY': 'ELIZABETH',
    'LIZZIE': 'ELIZABETH',
    'BETH': 'ELIZABETH',
    'BETTY': 'ELIZABETH',
    'BETSY': 'ELIZABETH',
    'ELIZA': 'ELIZABETH',

    'KATE': 'KATHERINE',
    'KATIE': 'KATHERINE',
    'KATHY': 'KATHERINE',
    'CATHY': 'CATHERINE',
    'CATHERINE': 'KATHERINE',
    'KAT': 'KATHERINE',

    'SUE': 'SUSAN',
    'SUSIE': 'SUSAN',
    'SUZY': 'SUSAN',

    'PAT': 'PATRICIA',
    'PATTY': 'PATRICIA',
    'TRISH': 'PATRICIA',
    'TRICIA': 'PATRICIA',

    'JENNY': 'JENNIFER',
    'JEN': 'JENNIFER',

    'BECKY': 'REBECCA',
    'BECCA': 'REBECCA',

    'MAGGIE': 'MARGARET',
    'PEGGY': 'MARGARET',
    'MARGE': 'MARGARET',
    'MARGIE': 'MARGARET',
    'MEG': 'MARGARET',

    'DEBBIE': 'DEBORAH',
    'DEB': 'DEBORAH',
    'DEBRA': 'DEBORAH',

    'BARB': 'BARBARA',
    'BARBIE': 'BARBARA',

    'NANCY': 'ANN',
    'ANNIE': 'ANN',
    'ANNA': 'ANN',

    'ABBY': 'ABIGAIL',
    'GAIL': 'ABIGAIL',

    'ALEX': 'ALEXANDRA',
    'LEXI': 'ALEXANDRA',

    'SANDY': 'SANDRA',

    'VICKY': 'VICTORIA',
    'VIKKI': 'VICTORIA',

    'CINDY': 'CYNTHIA',

    'MANDY': 'AMANDA',

    'CHRIS': 'CHRISTINE',
    'CHRISTY': 'CHRISTINE',
    'TINA': 'CHRISTINE',

    'JACKIE': 'JACQUELINE',

    'JUDY': 'JUDITH',

    'CAROL': 'CAROLINE',

    'DOT': 'DOROTHY',
    'DOTTY': 'DOROTHY',

    'ERICA': 'ERIKA',

    'HEATHER': 'HEATHER',

    'KIM': 'KIMBERLY',
    'KIMMY': 'KIMBERLY',

    'LINDA': 'LINDA',

    'LISA': 'ELIZABETH',

    'MANDY': 'AMANDA',

    'MEL': 'MELANIE',

    'MISSY': 'MELISSA',

    'NICKI': 'NICOLE',

    'PAM': 'PAMELA',

    'SAM': 'SAMANTHA',

    'STEPH': 'STEPHANIE',

    'TAMMY': 'TAMARA',

    'TERRI': 'TERESA',
    'TERRY': 'TERESA',

    'TONI': 'ANTONIA',

    'WENDY': 'GWENDOLYN',
}

# Suffixes to remove
NAME_SUFFIXES = {'JR', 'SR', 'II', 'III', 'IV', 'V', 'ESQ', 'PHD', 'MD', 'DDS'}


def normalize_name(name: str) -> str:
    """
    Normalize a name for consistent matching.

    Normalizations applied:
    1. Convert to uppercase
    2. Remove suffixes (Jr, Sr, III, etc.)
    3. Remove punctuation
    4. Trim whitespace

    Args:
        name: Raw name

    Returns:
        Normalized name
    """
    if not name:
        return ''

    # Convert to uppercase and strip
    normalized = name.upper().strip()

    # Remove punctuation
    normalized = re.sub(r'[.,;:\'\"!?()-]', '', normalized)

    # Normalize whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    # Remove suffixes
    words = normalized.split()
    filtered_words = [w for w in words if w not in NAME_SUFFIXES]

    return ' '.join(filtered_words)


def get_canonical_name(name: str) -> str:
    """
    Get the canonical (full) form of a name.

    Maps nicknames to their full versions.

    Args:
        name: Name (possibly a nickname)

    Returns:
        Canonical name
    """
    normalized = normalize_name(name)

    # Check if it's a known nickname
    if normalized in NICKNAME_MAP:
        return NICKNAME_MAP[normalized]

    return normalized


def get_name_variants(name: str) -> list:
    """
    Get all variants of a name (canonical + nicknames).

    Args:
        name: Name to get variants for

    Returns:
        List of name variants
    """
    if not name:
        return []

    normalized = normalize_name(name)
    variants = [normalized]

    # If it's a nickname, add the canonical form
    if normalized in NICKNAME_MAP:
        variants.append(NICKNAME_MAP[normalized])

    # If it's a canonical name, add all known nicknames
    for nickname, canonical in NICKNAME_MAP.items():
        if canonical == normalized and nickname not in variants:
            variants.append(nickname)

    return variants


def names_match(name1: str, name2: str, use_nicknames: bool = True) -> bool:
    """
    Check if two names match (considering nicknames).

    Args:
        name1: First name
        name2: Second name
        use_nicknames: If True, consider nickname mappings

    Returns:
        True if names match
    """
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)

    # Exact match
    if norm1 == norm2:
        return True

    if use_nicknames:
        # Get canonical forms
        canonical1 = get_canonical_name(name1)
        canonical2 = get_canonical_name(name2)

        if canonical1 == canonical2:
            return True

        # Check all variants
        variants1 = set(get_name_variants(name1))
        variants2 = set(get_name_variants(name2))

        if variants1 & variants2:  # Any overlap
            return True

    return False
