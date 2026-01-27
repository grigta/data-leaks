import json
import logging
import sqlite3
from database.db_schema import get_connection, close_connection, DEFAULT_DB_PATH
from database.normalizers import (
    normalize_address,
    generate_address_variants,
    extract_street_number,
    normalize_name,
    get_name_variants
)
from api.common.validators import (
    validate_limit,
    validate_ssn,
    validate_name,
    validate_address,
    validate_zip,
    safe_int,
    MAX_LIMIT_VALUE
)
from api.common.sanitizers import (
    sanitize_name,
    sanitize_address,
    sanitize_string
)


class SearchEngine:
    """
    SearchEngine class for searching SSN data across multiple database tables.

    This class provides three types of searches:
    1. Search by SSN
    2. Search by Name, Last Name and ZIP code
    3. Search by Name, Last Name and Address

    All searches query both ssn_1 and ssn_2 tables using UNION.
    """

    def __init__(self, db_path=None):
        """
        Initialize SearchEngine with database path.

        Args:
            db_path: Optional path to the database file. Defaults to DEFAULT_DB_PATH.
        """
        self.db_path = db_path if db_path is not None else DEFAULT_DB_PATH
        self.logger = logging.getLogger(self.__class__.__name__)

    def _safe_limit(self, limit) -> tuple:
        """
        Safely validate and process LIMIT parameter.

        Security:
            - Validates limit is a positive integer
            - Enforces maximum limit (1000)
            - Returns empty tuple for None (no limit)
            - Logs invalid limit attempts

        Args:
            limit: Limit value to validate (int, str, or None)

        Returns:
            Tuple: (limit_clause_str, limit_params_tuple)
            - For valid limit: (" LIMIT ?", (safe_limit,))
            - For None: ("", ())
        """
        if limit is None:
            return "", ()

        # Validate limit using centralized validator
        is_valid, error = validate_limit(limit, max_limit=MAX_LIMIT_VALUE)
        if not is_valid:
            self.logger.warning(f"Invalid LIMIT value rejected: {limit} - {error}")
            # Return default limit for safety
            return " LIMIT ?", (100,)

        safe_limit = safe_int(limit, default=100, max_value=MAX_LIMIT_VALUE)
        return " LIMIT ?", (safe_limit,)

    def _mask_ssn(self, ssn):
        """
        Mask SSN to show only last 4 digits.

        Args:
            ssn: Social Security Number string

        Returns:
            str: Masked SSN (e.g., "***-**-6789")
        """
        if not ssn or len(ssn) < 4:
            return "***"
        # Extract last 4 digits
        last_four = ''.join(c for c in ssn if c.isdigit())[-4:]
        return f"***-**-{last_four}"

    def _mask_email(self, email):
        """
        Mask email to show only first letter of local part and domain.

        Args:
            email: Email address string

        Returns:
            str: Masked email (e.g., "j***@example.com")
        """
        if not email or '@' not in email:
            return "***"
        local, domain = email.split('@', 1)
        if len(local) > 0:
            return f"{local[0]}***@{domain}"
        return f"***@{domain}"

    def _execute_search(self, query, params, limit_params=()):
        """
        Execute a SQL search query with parameters.

        Security:
            - Uses parameterized queries for all user input
            - LIMIT is passed as separate parameter tuple for safety

        Args:
            query: SQL query string with placeholders
            params: Tuple of parameters for the query
            limit_params: Tuple of LIMIT parameter(s) to append

        Returns:
            list: List of dictionaries containing search results

        Raises:
            sqlite3.Error: If database query fails
            FileNotFoundError: If database file doesn't exist
        """
        connection = None
        try:
            connection = get_connection(self.db_path)
            cursor = connection.cursor()

            # Combine params with limit_params for full parameterization
            all_params = params + limit_params
            cursor.execute(query, all_params)
            results = cursor.fetchall()

            # Convert sqlite3.Row objects to dictionaries
            result_dicts = [dict(row) for row in results]

            self.logger.info(f"Search completed. Found {len(result_dicts)} record(s)")
            return result_dicts

        except FileNotFoundError as e:
            self.logger.error(f"Database file not found: {e}")
            raise
        except sqlite3.Error as e:
            self.logger.error(f"Database error during search: {e}")
            raise
        finally:
            if connection:
                close_connection(connection)

    def _format_results_to_json(self, results, indent=2):
        """
        Format search results as JSON string.

        Args:
            results: List of dictionaries to format
            indent: Number of spaces for JSON indentation (default: 2)

        Returns:
            str: JSON formatted string
        """
        try:
            return json.dumps(results, indent=indent, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            self.logger.error(f"JSON serialization error: {e}")
            return json.dumps({"error": "Failed to serialize results"})

    def _search_by_last4_ssn(self, last4, limit=None):
        """
        Search for records by last 4 digits of SSN.

        Security:
            - Uses parameterized queries for all user input
            - LIMIT is validated and parameterized

        Args:
            last4: Last 4 digits of SSN
            limit: Optional maximum number of results to return

        Returns:
            list: List of matching records
        """
        # Validate last4 (should be exactly 4 digits)
        if not last4 or not str(last4).isdigit() or len(str(last4)) != 4:
            self.logger.warning(f"Invalid last4 SSN format: {last4}")
            return []

        # SSN pattern: ___-__-XXXX
        ssn_pattern = f"%-{last4}"

        # Get safe LIMIT clause and params
        limit_clause, limit_params = self._safe_limit(limit)

        query = f"""
        SELECT * FROM (
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_1' as source_table
            FROM ssn_1 WHERE ssn LIKE ?
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_2' as source_table
            FROM ssn_2 WHERE ssn LIKE ?
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_3' as source_table
            FROM ssn_3 WHERE ssn LIKE ?
        ){limit_clause}
        """

        self.logger.info(f"Searching by last 4 digits of SSN: ***-**-{last4}")
        return self._execute_search(query, (ssn_pattern, ssn_pattern, ssn_pattern), limit_params)

    def search_by_ssn(self, ssn, limit=None):
        """
        Search for records by Social Security Number.

        Security:
            - Validates SSN format before search
            - Uses parameterized queries
            - LIMIT is validated and parameterized

        Supports three formats:
        1. XXX-XX-XXXX (formatted with dashes)
        2. XXXXXXXXX (9 digits without dashes)
        3. XXXX (last 4 digits only)

        Args:
            ssn: Social Security Number (can include dashes and spaces)
            limit: Optional maximum number of results to return

        Returns:
            str: JSON string with matching records
        """
        # Validate SSN using centralized validator
        is_valid, error = validate_ssn(str(ssn))
        if not is_valid:
            self.logger.warning(f"SSN validation failed: {error}")
            return self._format_results_to_json([])

        # Normalize SSN: remove spaces and dashes, keep only digits
        normalized_ssn = ''.join(c for c in str(ssn) if c.isdigit())

        # Check if searching by last 4 digits
        if len(normalized_ssn) == 4:
            self.logger.info("Detected last 4 digits search")
            results = self._search_by_last4_ssn(normalized_ssn, limit=limit)
            return self._format_results_to_json(results)

        # Validate SSN: must be exactly 9 digits for full search
        if len(normalized_ssn) != 9:
            self.logger.warning(f"Invalid SSN format: expected 9 or 4 digits, got {len(normalized_ssn)}")
            return self._format_results_to_json([])

        # Format SSN as XXX-XX-XXXX for database search
        formatted_ssn = f"{normalized_ssn[:3]}-{normalized_ssn[3:5]}-{normalized_ssn[5:]}"

        # Get safe LIMIT clause and params
        limit_clause, limit_params = self._safe_limit(limit)

        query = f"""
        SELECT * FROM (
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_1' as source_table
            FROM ssn_1 WHERE ssn = ?
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_2' as source_table
            FROM ssn_2 WHERE ssn = ?
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_3' as source_table
            FROM ssn_3 WHERE ssn = ?
        ){limit_clause}
        """

        self.logger.info(f"Searching by full SSN: {self._mask_ssn(formatted_ssn)}")
        results = self._execute_search(query, (formatted_ssn, formatted_ssn, formatted_ssn), limit_params)

        return self._format_results_to_json(results)

    def search_by_name_zip(self, firstname, lastname, zip_code, limit=None):
        """
        Search for records by first name, last name, and ZIP code.

        Security:
            - Validates all input parameters
            - Sanitizes names before search
            - Uses parameterized queries
            - LIMIT is validated and parameterized

        Uses the composite index idx_{table}_name_zip for optimized performance.

        Args:
            firstname: First name to search for
            lastname: Last name to search for
            zip_code: ZIP code to search for
            limit: Optional maximum number of results to return

        Returns:
            str: JSON string with matching records
        """
        # Sanitize input data
        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""
        zip_code = sanitize_string(str(zip_code).strip(), max_length=10) or ""

        # Validate required fields
        if not firstname or not lastname:
            self.logger.warning("Firstname and lastname are required for name+zip search")
            return self._format_results_to_json([])

        # Validate names
        is_valid, error = validate_name(firstname, "firstname")
        if not is_valid:
            self.logger.warning(f"Invalid firstname: {error}")
            return self._format_results_to_json([])

        is_valid, error = validate_name(lastname, "lastname")
        if not is_valid:
            self.logger.warning(f"Invalid lastname: {error}")
            return self._format_results_to_json([])

        # Get safe LIMIT clause and params
        limit_clause, limit_params = self._safe_limit(limit)

        query = f"""
        SELECT * FROM (
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_1' as source_table
            FROM ssn_1 WHERE firstname = ? COLLATE NOCASE AND lastname = ? COLLATE NOCASE AND zip = ?
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_2' as source_table
            FROM ssn_2 WHERE firstname = ? COLLATE NOCASE AND lastname = ? COLLATE NOCASE AND zip = ?
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_3' as source_table
            FROM ssn_3 WHERE firstname = ? COLLATE NOCASE AND lastname = ? COLLATE NOCASE AND zip = ?
        ){limit_clause}
        """

        self.logger.info("Searching by name+zip")
        results = self._execute_search(
            query,
            (firstname, lastname, zip_code, firstname, lastname, zip_code, firstname, lastname, zip_code),
            limit_params
        )

        return self._format_results_to_json(results)

    def search_by_name_address(self, firstname, lastname, address, limit=None):
        """
        Search for records by first name, last name, and address.

        Security:
            - Validates all input parameters
            - Sanitizes names and address before search
            - Uses parameterized queries
            - LIMIT is validated and parameterized

        Uses the composite index idx_{table}_name_address for optimized performance.

        Args:
            firstname: First name to search for
            lastname: Last name to search for
            address: Address to search for
            limit: Optional maximum number of results to return

        Returns:
            str: JSON string with matching records
        """
        # Sanitize input data
        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""
        address = sanitize_address(str(address).strip()) or ""

        # Validate required fields
        if not firstname or not lastname:
            self.logger.warning("Firstname and lastname are required for name+address search")
            return self._format_results_to_json([])

        # Validate names
        is_valid, error = validate_name(firstname, "firstname")
        if not is_valid:
            self.logger.warning(f"Invalid firstname: {error}")
            return self._format_results_to_json([])

        is_valid, error = validate_name(lastname, "lastname")
        if not is_valid:
            self.logger.warning(f"Invalid lastname: {error}")
            return self._format_results_to_json([])

        # Get safe LIMIT clause and params
        limit_clause, limit_params = self._safe_limit(limit)

        query = f"""
        SELECT * FROM (
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_1' as source_table
            FROM ssn_1 WHERE firstname = ? COLLATE NOCASE AND lastname = ? COLLATE NOCASE AND address = ? COLLATE NOCASE
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_2' as source_table
            FROM ssn_2 WHERE firstname = ? COLLATE NOCASE AND lastname = ? COLLATE NOCASE AND address = ? COLLATE NOCASE
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_3' as source_table
            FROM ssn_3 WHERE firstname = ? COLLATE NOCASE AND lastname = ? COLLATE NOCASE AND address = ? COLLATE NOCASE
        ){limit_clause}
        """

        self.logger.info("Searching by name+address")
        results = self._execute_search(
            query,
            (firstname, lastname, address, firstname, lastname, address, firstname, lastname, address),
            limit_params
        )

        return self._format_results_to_json(results)

    def _search_by_phone_match(self, firstname, lastname, all_phones, limit=None):
        """
        Search for SSN records by firstname + lastname + phone.

        Security:
            - Sanitizes names before search
            - Phone numbers are normalized (digits only)
            - Uses parameterized queries
            - LIMIT is validated and parameterized

        Args:
            firstname: First name
            lastname: Last name
            all_phones: List of phone numbers
            limit: Optional limit

        Returns:
            list: Matching records
        """
        if not all_phones or len(all_phones) == 0:
            return []

        # Sanitize names
        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""

        if not firstname or not lastname:
            return []

        # Normalize phone numbers (remove formatting)
        normalized_phones = []
        for phone in all_phones:
            if phone:
                # Remove all non-digit characters
                digits = ''.join(c for c in str(phone) if c.isdigit())
                if len(digits) == 10:
                    # Format as XXXXXXXXXX for database matching
                    normalized_phones.append(digits)
                elif len(digits) == 11 and digits.startswith('1'):
                    # Remove leading 1
                    normalized_phones.append(digits[1:])

        if not normalized_phones:
            return []

        # Get safe LIMIT clause and params
        limit_clause, limit_params = self._safe_limit(limit)

        # Build query
        phone_placeholders = ','.join(['?'] * len(normalized_phones))
        query = f"""
        SELECT * FROM (
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_1' as source_table
            FROM ssn_1
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND REPLACE(REPLACE(REPLACE(phone, '(', ''), ')', ''), '-', '') IN ({phone_placeholders})
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_2' as source_table
            FROM ssn_2
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND REPLACE(REPLACE(REPLACE(phone, '(', ''), ')', ''), '-', '') IN ({phone_placeholders})
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_3' as source_table
            FROM ssn_3
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND REPLACE(REPLACE(REPLACE(phone, '(', ''), ')', ''), '-', '') IN ({phone_placeholders})
        ){limit_clause}
        """

        params = [firstname, lastname] + normalized_phones + [firstname, lastname] + normalized_phones + [firstname, lastname] + normalized_phones

        self.logger.info(f"Priority 1: Searching by phone ({len(normalized_phones)} numbers)")
        return self._execute_search(query, tuple(params), limit_params)

    def _search_by_address_match(self, firstname, lastname, all_addresses, limit=None):
        """
        Search for SSN records by firstname + lastname + address.

        Security:
            - Sanitizes names before search
            - Address patterns are normalized
            - Uses parameterized queries
            - LIMIT is validated and parameterized

        Uses address normalization to match different formats:
        - "5800 N COLRAIN AVE" matches "5800 NORTH COLRAIN AVENUE"
        - Street number extraction for fuzzy matching

        Args:
            firstname: First name
            lastname: Last name
            all_addresses: List of addresses (full_street values)
            limit: Optional limit

        Returns:
            list: Matching records
        """
        if not all_addresses or len(all_addresses) == 0:
            return []

        # Sanitize names
        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""

        if not firstname or not lastname:
            return []

        # Generate multiple variants of each address for better matching
        all_search_patterns = []
        seen_patterns = set()

        for addr in all_addresses:
            if not addr or not isinstance(addr, str):
                continue

            # Sanitize address
            addr = sanitize_address(addr) or ""
            if not addr:
                continue

            # Generate normalized variants
            variants = generate_address_variants(addr)
            for variant in variants:
                if variant and variant not in seen_patterns:
                    seen_patterns.add(variant)
                    all_search_patterns.append(f"%{variant}%")

            # Also add original normalized form
            normalized = normalize_address(addr)
            if normalized and normalized not in seen_patterns:
                seen_patterns.add(normalized)
                all_search_patterns.append(f"%{normalized}%")

            # Extract street number for more specific matching
            street_num = extract_street_number(addr)
            if street_num:
                # Pattern: "5800 %" - matches any address starting with this number
                num_pattern = f"{street_num} %"
                if num_pattern not in seen_patterns:
                    seen_patterns.add(num_pattern)
                    all_search_patterns.append(num_pattern)

        if not all_search_patterns:
            return []

        self.logger.info(f"Priority 2: Searching by address ({len(all_addresses)} addresses -> {len(all_search_patterns)} patterns)")

        # Get safe LIMIT clause and params
        limit_clause, limit_params = self._safe_limit(limit)

        # Build query with LIKE conditions
        address_conditions = []
        for _ in all_search_patterns:
            address_conditions.append("address LIKE ? COLLATE NOCASE")

        address_clause = " OR ".join(address_conditions)

        query = f"""
        SELECT * FROM (
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_1' as source_table
            FROM ssn_1
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND ({address_clause})
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_2' as source_table
            FROM ssn_2
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND ({address_clause})
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_3' as source_table
            FROM ssn_3
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND ({address_clause})
        ){limit_clause}
        """

        params = [firstname, lastname] + all_search_patterns + [firstname, lastname] + all_search_patterns + [firstname, lastname] + all_search_patterns

        return self._execute_search(query, tuple(params), limit_params)

    def _search_by_zip_match(self, firstname, lastname, all_zips, limit=None):
        """
        Search for SSN records by firstname + lastname + ZIP.

        Security:
            - Sanitizes names before search
            - ZIP codes are normalized
            - Uses parameterized queries
            - LIMIT is validated and parameterized

        Args:
            firstname: First name
            lastname: Last name
            all_zips: List of ZIP codes
            limit: Optional limit

        Returns:
            list: Matching records
        """
        if not all_zips or len(all_zips) == 0:
            return []

        # Sanitize names
        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""

        if not firstname or not lastname:
            return []

        # Normalize ZIP codes (keep only valid ones)
        normalized_zips = []
        for z in all_zips:
            if z:
                z_clean = sanitize_string(str(z).strip(), max_length=10)
                if z_clean:
                    normalized_zips.append(z_clean)

        if not normalized_zips:
            return []

        # Get safe LIMIT clause and params
        limit_clause, limit_params = self._safe_limit(limit)

        # Build query
        zip_placeholders = ','.join(['?'] * len(normalized_zips))
        query = f"""
        SELECT * FROM (
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_1' as source_table
            FROM ssn_1
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND zip IN ({zip_placeholders})
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_2' as source_table
            FROM ssn_2
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND zip IN ({zip_placeholders})
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_3' as source_table
            FROM ssn_3
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND zip IN ({zip_placeholders})
        ){limit_clause}
        """

        params = [firstname, lastname] + normalized_zips + [firstname, lastname] + normalized_zips + [firstname, lastname] + normalized_zips

        self.logger.info(f"Priority 3: Searching by ZIP ({len(normalized_zips)} codes)")
        return self._execute_search(query, tuple(params), limit_params)

    def _search_by_state_match(self, firstname, lastname, all_states, limit=None):
        """
        Search for SSN records by firstname + lastname + state.
        Priority 4 fallback - less precise but catches outdated addresses.

        Security:
            - Sanitizes names before search
            - State codes are validated (2 uppercase letters)
            - Uses parameterized queries
            - LIMIT is validated and parameterized

        Args:
            firstname: First name
            lastname: Last name
            all_states: List of state codes (2-letter)
            limit: Optional limit

        Returns:
            list: Matching records
        """
        if not all_states or len(all_states) == 0:
            return []

        # Sanitize names
        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""

        if not firstname or not lastname:
            return []

        # Normalize states (uppercase, 2 letters only)
        normalized_states = []
        for state in all_states:
            if state and isinstance(state, str):
                state_clean = state.upper().strip()
                if len(state_clean) == 2 and state_clean.isalpha():
                    normalized_states.append(state_clean)

        if not normalized_states:
            return []

        # Get safe LIMIT clause and params
        limit_clause, limit_params = self._safe_limit(limit)

        # Build query
        state_placeholders = ','.join(['?'] * len(normalized_states))
        query = f"""
        SELECT * FROM (
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_1' as source_table
            FROM ssn_1
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND state IN ({state_placeholders})
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_2' as source_table
            FROM ssn_2
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND state IN ({state_placeholders})
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_3' as source_table
            FROM ssn_3
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND state IN ({state_placeholders})
        ){limit_clause}
        """

        params = [firstname, lastname] + normalized_states + [firstname, lastname] + normalized_states + [firstname, lastname] + normalized_states

        self.logger.info(f"Priority 4: Searching by STATE ({len(normalized_states)} states: {normalized_states})")
        return self._execute_search(query, tuple(params), limit_params)

    def search_by_searchbug_data(self, firstname, lastname, all_zips=None, all_phones=None, all_addresses=None, all_states=None, limit=None):
        """
        Search for SSN records matching external API data with priority-based matching.

        Security:
            - Validates and sanitizes all input parameters
            - Uses parameterized queries throughout
            - LIMIT is validated and parameterized

        Priority order (stops at first match):
        1. firstname + lastname + phone (if phones provided)
        2. firstname + lastname + address (if addresses provided) - with normalization
        3. firstname + lastname + ZIP (if zips provided)
        4. firstname + lastname + state (if states provided) - fallback for outdated data
        5. name variants + phone/address/ZIP - tries nicknames (Bob->Robert, Mike->Michael)

        Args:
            firstname: First name to search for
            lastname: Last name to search for
            all_zips: List of ZIP codes (optional)
            all_phones: List of phone numbers (optional)
            all_addresses: List of addresses (full_street) (optional)
            all_states: List of state codes (optional)
            limit: Optional maximum number of results to return

        Returns:
            list: List of matching records (as dicts, not JSON string)
        """
        # Sanitize and normalize input data
        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""

        # Validate required fields
        if not firstname or not lastname:
            self.logger.warning("Firstname and lastname are required")
            return []

        # Validate names
        is_valid, error = validate_name(firstname, "firstname")
        if not is_valid:
            self.logger.warning(f"Invalid firstname in searchbug data: {error}")
            return []

        is_valid, error = validate_name(lastname, "lastname")
        if not is_valid:
            self.logger.warning(f"Invalid lastname in searchbug data: {error}")
            return []

        self.logger.info(
            f"Searching by external API data: {firstname} {lastname}, "
            f"phones={len(all_phones) if all_phones else 0}, "
            f"addresses={len(all_addresses) if all_addresses else 0}, "
            f"zips={len(all_zips) if all_zips else 0}, "
            f"states={len(all_states) if all_states else 0}"
        )

        # Priority 1: Try phone search first
        if all_phones and len(all_phones) > 0:
            results = self._search_by_phone_match(firstname, lastname, all_phones, limit)
            if results and len(results) > 0:
                self.logger.info(f"✓ Found {len(results)} match(es) by PHONE (Priority 1)")
                return results
            self.logger.info("✗ No matches by phone, trying next priority")

        # Priority 2: Try address search
        if all_addresses and len(all_addresses) > 0:
            results = self._search_by_address_match(firstname, lastname, all_addresses, limit)
            if results and len(results) > 0:
                self.logger.info(f"✓ Found {len(results)} match(es) by ADDRESS (Priority 2)")
                return results
            self.logger.info("✗ No matches by address, trying next priority")

        # Priority 3: Try ZIP search
        if all_zips and len(all_zips) > 0:
            results = self._search_by_zip_match(firstname, lastname, all_zips, limit)
            if results and len(results) > 0:
                self.logger.info(f"✓ Found {len(results)} match(es) by ZIP (Priority 3)")
                return results
            self.logger.info("✗ No matches by ZIP, trying next priority")

        # Priority 4: Try state search (fallback for outdated address data)
        if all_states and len(all_states) > 0:
            results = self._search_by_state_match(firstname, lastname, all_states, limit)
            if results and len(results) > 0:
                self.logger.info(f"✓ Found {len(results)} match(es) by STATE (Priority 4)")
                return results
            self.logger.info("✗ No matches by state")

        # Priority 5: Try with name variants (nicknames)
        # Only try if we have specific search criteria (phones or addresses)
        firstname_variants = get_name_variants(firstname)
        if len(firstname_variants) > 1:  # Has alternative names
            self.logger.info(f"Priority 5: Trying name variants for '{firstname}': {firstname_variants}")

            for variant in firstname_variants:
                if variant.upper() == firstname.upper():
                    continue  # Skip the original name

                # Try phone search with variant name
                if all_phones and len(all_phones) > 0:
                    results = self._search_by_phone_match(variant, lastname, all_phones, limit)
                    if results and len(results) > 0:
                        self.logger.info(f"✓ Found {len(results)} match(es) by PHONE with name variant '{variant}' (Priority 5)")
                        return results

                # Try address search with variant name
                if all_addresses and len(all_addresses) > 0:
                    results = self._search_by_address_match(variant, lastname, all_addresses, limit)
                    if results and len(results) > 0:
                        self.logger.info(f"✓ Found {len(results)} match(es) by ADDRESS with name variant '{variant}' (Priority 5)")
                        return results

                # Try ZIP search with variant name
                if all_zips and len(all_zips) > 0:
                    results = self._search_by_zip_match(variant, lastname, all_zips, limit)
                    if results and len(results) > 0:
                        self.logger.info(f"✓ Found {len(results)} match(es) by ZIP with name variant '{variant}' (Priority 5)")
                        return results

            self.logger.info("✗ No matches with name variants")

        # No matches found
        self.logger.info("No SSN matches found with any criteria")
        return []

    def search_by_fields(self, firstname, lastname, city=None, state=None, phone=None, zip=None, limit=None):
        """
        Search for SSN records by firstname + lastname with optional filters.

        This is a flexible search method that accepts various optional parameters
        and uses priority-based matching:
        1. firstname + lastname + phone (if provided)
        2. firstname + lastname + city + state (if both provided)
        3. firstname + lastname + zip (if provided)
        4. firstname + lastname + state (if provided, fallback)

        Security:
            - Validates and sanitizes all input parameters
            - Uses parameterized queries throughout
            - LIMIT is validated and parameterized

        Args:
            firstname: First name to search for (required)
            lastname: Last name to search for (required)
            city: City name (optional)
            state: State code, 2 letters (optional)
            phone: Phone number (optional)
            zip: ZIP code (optional)
            limit: Optional maximum number of results to return

        Returns:
            str: JSON string with matching records
        """
        # Sanitize and normalize required fields
        firstname = sanitize_name(str(firstname).strip()) if firstname else ""
        lastname = sanitize_name(str(lastname).strip()) if lastname else ""

        # Validate required fields
        if not firstname or not lastname:
            self.logger.warning("Firstname and lastname are required for search_by_fields")
            return self._format_results_to_json([])

        # Validate names
        is_valid, error = validate_name(firstname, "firstname")
        if not is_valid:
            self.logger.warning(f"Invalid firstname in search_by_fields: {error}")
            return self._format_results_to_json([])

        is_valid, error = validate_name(lastname, "lastname")
        if not is_valid:
            self.logger.warning(f"Invalid lastname in search_by_fields: {error}")
            return self._format_results_to_json([])

        self.logger.info(
            f"search_by_fields: {firstname} {lastname}, "
            f"city={city}, state={state}, phone={phone}, zip={zip}"
        )

        # Priority 1: Try phone search if provided
        if phone:
            results = self._search_by_phone_match(firstname, lastname, [phone], limit)
            if results and len(results) > 0:
                self.logger.info(f"✓ Found {len(results)} match(es) by PHONE")
                return self._format_results_to_json(results)
            self.logger.info("✗ No matches by phone")

        # Priority 2: Try city + state search if both provided
        if city and state:
            results = self._search_by_city_state_match(firstname, lastname, city, state, limit)
            if results and len(results) > 0:
                self.logger.info(f"✓ Found {len(results)} match(es) by CITY+STATE")
                return self._format_results_to_json(results)
            self.logger.info("✗ No matches by city+state")

        # Priority 3: Try ZIP search if provided
        if zip:
            results = self._search_by_zip_match(firstname, lastname, [zip], limit)
            if results and len(results) > 0:
                self.logger.info(f"✓ Found {len(results)} match(es) by ZIP")
                return self._format_results_to_json(results)
            self.logger.info("✗ No matches by ZIP")

        # Priority 4: Try state search (fallback)
        if state:
            results = self._search_by_state_match(firstname, lastname, [state], limit)
            if results and len(results) > 0:
                self.logger.info(f"✓ Found {len(results)} match(es) by STATE")
                return self._format_results_to_json(results)
            self.logger.info("✗ No matches by state")

        # No matches found
        self.logger.info("No matches found with any criteria in search_by_fields")
        return self._format_results_to_json([])

    def _search_by_city_state_match(self, firstname, lastname, city, state, limit=None):
        """
        Search for SSN records by firstname + lastname + city + state.

        Security:
            - Sanitizes names, city and state before search
            - Uses parameterized queries
            - LIMIT is validated and parameterized

        Args:
            firstname: First name
            lastname: Last name
            city: City name
            state: State code (2-letter)
            limit: Optional limit

        Returns:
            list: Matching records
        """
        # Sanitize names
        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""

        if not firstname or not lastname:
            return []

        # Sanitize city and state
        city = sanitize_string(str(city).strip(), max_length=100) if city else ""
        state = state.upper().strip() if state and isinstance(state, str) else ""

        if not city or not state:
            return []

        # Validate state format (2 uppercase letters)
        if len(state) != 2 or not state.isalpha():
            self.logger.warning(f"Invalid state format: {state}")
            return []

        # Get safe LIMIT clause and params
        limit_clause, limit_params = self._safe_limit(limit)

        query = f"""
        SELECT * FROM (
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_1' as source_table
            FROM ssn_1
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND city = ? COLLATE NOCASE
              AND state = ?
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_2' as source_table
            FROM ssn_2
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND city = ? COLLATE NOCASE
              AND state = ?
            UNION ALL
            SELECT id, firstname, lastname, address, city, state, zip, phone, ssn, dob, email, 'ssn_3' as source_table
            FROM ssn_3
            WHERE firstname = ? COLLATE NOCASE
              AND lastname = ? COLLATE NOCASE
              AND city = ? COLLATE NOCASE
              AND state = ?
        ){limit_clause}
        """

        params = (firstname, lastname, city, state) * 3

        self.logger.info(f"Searching by name+city+state: {city}, {state}")
        return self._execute_search(query, params, limit_params)

    def search_by_address_dob_firstname(self, addresses, dob, firstname, limit=None):
        """
        Fallback search method: find records by exact address + DOB + firstname (without lastname).

        Security:
            - Sanitizes firstname and addresses
            - Validates DOB format
            - Uses parameterized queries
            - LIMIT is validated and parameterized

        This method is useful when external API and local database have different last names
        for the same person (e.g., maiden name vs married name).

        Strategy:
        - Searches for exact address match + exact DOB match + firstname match
        - Returns only if exactly 1 match found (to avoid ambiguity)
        - Used as fallback when primary search (firstname + lastname) fails

        Args:
            addresses: List of addresses (full_street)
            dob: Date of birth (YYYYMMDD format)
            firstname: First name to match
            limit: Optional maximum number of results to return

        Returns:
            list: List of matching records (empty if 0 or 2+ matches found)
        """
        if not addresses or not dob or not firstname:
            self.logger.debug("Missing required fields for address+DOB+firstname search")
            return []

        # Sanitize and normalize firstname
        firstname = sanitize_name(str(firstname).strip()) or ""
        if not firstname:
            self.logger.warning("Empty firstname after sanitization")
            return []
        firstname = firstname.upper()

        # Sanitize DOB (max length protection against DoS)
        dob = sanitize_string(str(dob).strip(), max_length=20) or ""
        if not dob:
            self.logger.warning("Empty DOB after sanitization")
            return []

        # Convert DOB to YYYYMMDD format if needed (from MM/DD/YYYY)
        if '/' in dob:
            try:
                from datetime import datetime as dt
                dob_obj = dt.strptime(dob, '%m/%d/%Y')
                dob = dob_obj.strftime('%Y%m%d')
                self.logger.debug(f"Converted DOB from MM/DD/YYYY to YYYYMMDD: {dob}")
            except ValueError:
                self.logger.warning(f"Failed to convert DOB format: {dob}")

        self.logger.info(
            f"Fallback search by address+DOB+firstname: {firstname}, DOB={dob}, "
            f"{len(addresses)} address(es)"
        )

        # Get safe LIMIT clause and params
        limit_clause, limit_params = self._safe_limit(limit)

        all_matches = []

        # Try each address
        for address in addresses:
            if not address:
                continue

            # Sanitize address
            address = sanitize_address(str(address).strip()) or ""
            if not address:
                continue

            # Normalize address
            normalized_address = normalize_address(address)
            address_variants = generate_address_variants(address)

            # Build query for both tables
            query_parts = []
            params = []

            for table in ['ssn_1', 'ssn_2', 'ssn_3']:
                # Build address conditions (match any variant)
                address_conditions = []
                for variant in address_variants:
                    address_conditions.append("UPPER(address) = ?")
                    params.append(variant.upper())

                # Build query part for this table
                query_part = f"""
                    SELECT *, '{table}' as source_table
                    FROM {table}
                    WHERE UPPER(firstname) = ?
                      AND dob = ?
                      AND ({' OR '.join(address_conditions)})
                """
                query_parts.append(query_part)

                # Add firstname and DOB parameters for this table
                params.insert(-len(address_variants), firstname)
                params.insert(-len(address_variants), dob)

            # Combine queries with UNION
            query = ' UNION '.join(query_parts)

            # Add parameterized LIMIT
            query += limit_clause

            try:
                matches = self._execute_search(query, tuple(params), limit_params)
                if matches:
                    all_matches.extend(matches)
                    self.logger.info(
                        f"Found {len(matches)} match(es) for address '{address}' + DOB + firstname"
                    )
            except Exception as e:
                self.logger.error(f"Error searching by address+DOB+firstname: {e}")
                continue

        # Security check: only return if exactly 1 match found
        if len(all_matches) == 0:
            self.logger.info("No matches found by address+DOB+firstname")
            return []
        elif len(all_matches) == 1:
            self.logger.info(
                f"✓ Found exactly 1 match by address+DOB+firstname (fallback successful): "
                f"SSN={all_matches[0].get('ssn')}, Name={all_matches[0].get('firstname')} "
                f"{all_matches[0].get('lastname')}"
            )
            return all_matches
        else:
            # Multiple matches - ambiguous, don't return
            self.logger.warning(
                f"Found {len(all_matches)} matches by address+DOB+firstname - ambiguous, rejecting"
            )
            return []


# Convenience functions for simple API access

def search_by_ssn(ssn, db_path=None, limit=None):
    """
    Convenience function to search by SSN.

    Args:
        ssn: Social Security Number
        db_path: Optional database path
        limit: Optional maximum number of results to return

    Returns:
        str: JSON string with search results
    """
    engine = SearchEngine(db_path)
    return engine.search_by_ssn(ssn, limit=limit)


def search_by_name_zip(firstname, lastname, zip_code, db_path=None, limit=None):
    """
    Convenience function to search by name and ZIP code.

    Args:
        firstname: First name
        lastname: Last name
        zip_code: ZIP code
        db_path: Optional database path
        limit: Optional maximum number of results to return

    Returns:
        str: JSON string with search results
    """
    engine = SearchEngine(db_path)
    return engine.search_by_name_zip(firstname, lastname, zip_code, limit=limit)


def search_by_name_address(firstname, lastname, address, db_path=None, limit=None):
    """
    Convenience function to search by name and address.

    Args:
        firstname: First name
        lastname: Last name
        address: Address
        db_path: Optional database path
        limit: Optional maximum number of results to return

    Returns:
        str: JSON string with search results
    """
    engine = SearchEngine(db_path)
    return engine.search_by_name_address(firstname, lastname, address, limit=limit)


if __name__ == '__main__':
    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        # Create SearchEngine instance
        engine = SearchEngine()

        print("\n" + "="*80)
        print("SSN SEARCH ENGINE - DEMONSTRATION")
        print("="*80)

        # Demo 1: Search by SSN
        print("\n[1] SEARCH BY SSN")
        print("-" * 80)
        print("Searching for SSN: 123-45-6789")
        json_results = engine.search_by_ssn("123-45-6789")
        results = json.loads(json_results)
        print(f"Results found: {len(results)}")
        print(json_results)

        # Demo 2: Search by Name and ZIP
        print("\n[2] SEARCH BY NAME AND ZIP")
        print("-" * 80)
        print("Searching for: John Doe, ZIP: 12345")
        json_results = engine.search_by_name_zip("John", "Doe", "12345")
        results = json.loads(json_results)
        print(f"Results found: {len(results)}")
        print(json_results)

        # Demo 3: Search by Name and Address
        print("\n[3] SEARCH BY NAME AND ADDRESS")
        print("-" * 80)
        print("Searching for: Jane Smith, Address: 123 Main St")
        json_results = engine.search_by_name_address("Jane", "Smith", "123 Main St")
        results = json.loads(json_results)
        print(f"Results found: {len(results)}")
        print(json_results)

        print("\n" + "="*80)
        print("DEMONSTRATION COMPLETED")
        print("="*80 + "\n")

    except FileNotFoundError:
        print("\nERROR: Database file not found. Please initialize the database first.")
        print("Run: python db_schema.py")
    except sqlite3.Error as e:
        print(f"\nDATABASE ERROR: {e}")
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {e}")
