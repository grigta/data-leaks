"""
ClickHouse Search Engine for SSN Data

This module provides the same search interface as the SQLite SearchEngine but uses
ClickHouse as the backend. It leverages Bloom filter indexes for fast filtering
and optimized queries for large datasets.

Main Features:
- Same interface as SQLite SearchEngine for easy migration
- Uses parameterized queries for SQL injection prevention
- Leverages Bloom filter indexes for fast SSN/name/address lookups
- Single table queries (no UNION ALL across 3 tables)
- Case-insensitive searches using lowerUTF8()

Usage:
    from database.clickhouse_search_engine import ClickHouseSearchEngine
    engine = ClickHouseSearchEngine()
    results = engine.search_by_ssn("123-45-6789")
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from database.clickhouse_client import (
    execute_query,
    get_connection,
    CLICKHOUSE_AVAILABLE,
)
from database.clickhouse_schema import (
    SSN_TABLE,
    SSN_MUTANTS_TABLE,
    ALL_SSN_TABLES,
    SSN_BLOOM_PHONE_LOOKUP,
    SSN_MUTANTS_BLOOM_PHONE_LOOKUP,
    SSN_BLOOM_ADDRESS_LOOKUP,
    SSN_MUTANTS_BLOOM_ADDRESS_LOOKUP,
)
from api.common.validators import (
    validate_limit,
    validate_ssn,
    validate_name,
    MAX_LIMIT_VALUE,
)
from api.common.sanitizers import (
    sanitize_name,
    sanitize_address,
    sanitize_string,
)
from database.bloom_key_generator import (
    generate_bloom_key_phone,
    generate_bloom_key_address,
    generate_all_bloom_keys_from_searchbug,
)
from database.search_key_generator import (
    generate_search_keys_from_searchbug,
    generate_query_keys_from_searchbug,
    generate_candidate_keys,
)


# =============================================================================
# Приоритет методов matching (меньше = выше приоритет)
# Используется для ранжирования результатов поиска
# =============================================================================
MATCH_METHOD_PRIORITY = {
    # FN (полное имя) — приоритет 1-8
    "FN+MN+LN+DOB+PHONE": 1,
    "FN+MN+LN+DOB+ADDR": 2,
    "FN+LN+DOB+PHONE": 3,
    "FN+LN+DOB+ADDR": 4,
    "FN+MN+LN+PHONE": 5,
    "FN+MN+LN+ADDR": 6,
    "FN+LN+ADDR": 7,
    "FN+LN+PHONE": 8,
    # FN1 (первая буква имени) — приоритет 9-16
    "FN1+MN+LN+DOB+PHONE": 9,
    "FN1+MN+LN+DOB+ADDR": 10,
    "FN1+LN+DOB+PHONE": 11,
    "FN1+LN+DOB+ADDR": 12,
    "FN1+MN+LN+PHONE": 13,
    "FN1+MN+LN+ADDR": 14,
    "FN1+LN+ADDR": 15,
    "FN1+LN+PHONE": 16,
}


def _get_best_match_priority(matched_keys: List[str]) -> int:
    """
    Возвращает лучший (наименьший) приоритет из списка matched_keys.

    matched_keys format: ["FN+LN+PHONE: john:wick:5551234567", ...]
    """
    best = 999
    for key in matched_keys:
        method = key.split(":")[0].strip()
        priority = MATCH_METHOD_PRIORITY.get(method, 999)
        best = min(best, priority)
    return best


def _normalize_address_for_match(address: str) -> str:
    """
    Извлекает номер дома + первое значимое слово улицы для сравнения адресов.

    Пропускает только однобуквенные направления (N, S, E, W).
    Пример: '4514 E Crossroads Dr' -> '4514:crossroads'
            '2786 Andrew Jackson Rd' -> '2786:andrew'
            'PO BOX 133' -> 'pb:133'
    """
    if not address:
        return ""
    addr = address.upper().strip()

    # PO BOX
    po_match = re.match(r'^PO\s+BOX\s+(\d+)', addr)
    if po_match:
        return f"pb:{po_match.group(1)}"

    # Regular address: extract house number
    num_match = re.match(r'^(\d+)', addr)
    if not num_match:
        return ""
    house_num = num_match.group(1)

    # Get remaining words after house number
    rest = addr[num_match.end():].strip().split()
    street_word = ""
    for word in rest:
        if len(word) == 1 and word in ('N', 'S', 'E', 'W'):
            continue
        street_word = word.lower()
        break

    return f"{house_num}:{street_word}" if street_word else house_num


def mark_input_address_match(candidates: List[Dict], input_address: str) -> None:
    """
    Помечает кандидатов, чей адрес совпадает с input address пользователя.
    Устанавливает поле '_input_addr_match' = True/False.
    """
    input_key = _normalize_address_for_match(input_address)
    if not input_key:
        return
    for candidate in candidates:
        candidate_addr = candidate.get('address', '')
        candidate_key = _normalize_address_for_match(candidate_addr)
        candidate['_input_addr_match'] = (candidate_key == input_key)


def mark_searchbug_primary_address_match(candidates: List[Dict], sb_primary_address: str) -> None:
    """
    Помечает кандидатов, чей адрес совпадает с primary address от SearchBug.
    Устанавливает поле '_sb_primary_addr_match' = True/False.

    SearchBug primary address — наиболее достоверный текущий адрес человека.
    Приоритетнее пользовательского input address в ранжировании.
    """
    sb_key = _normalize_address_for_match(sb_primary_address)
    if not sb_key:
        return
    for candidate in candidates:
        candidate_addr = candidate.get('address', '')
        candidate_key = _normalize_address_for_match(candidate_addr)
        candidate['_sb_primary_addr_match'] = (candidate_key == sb_key)


def _get_primary_mn_initial(searchbug_data: Dict) -> Optional[str]:
    """
    Извлекает первую букву middlename из primary записи SearchBug.

    Приоритет: names[0].middle_name -> searchbug_data.middlename
    """
    names_list = searchbug_data.get('names', []) or []
    if names_list and isinstance(names_list[0], dict):
        mn = names_list[0].get('middle_name', '') or ''
        if mn and mn[0].isalpha():
            return mn[0].lower()
    mn = searchbug_data.get('middlename', '') or ''
    if mn and mn[0].isalpha():
        return mn[0].lower()
    return None


def mark_middlename_match(candidates: List[Dict], primary_mn_initial: Optional[str]) -> None:
    """
    Помечает кандидатов, чей middlename initial совпадает с primary SearchBug middlename.
    Устанавливает поле '_mn_match' = True/False.

    Это помогает в случаях, когда SearchBug конфликтует разных людей с одинаковыми
    firstname+lastname но разными middlename (напр. JOHN E NAVARRE vs JOHN A NAVARRE).
    """
    if not primary_mn_initial:
        return
    for candidate in candidates:
        candidate_mn = candidate.get('middlename', '') or ''
        if candidate_mn and candidate_mn[0].isalpha():
            candidate['_mn_match'] = candidate_mn[0].lower() == primary_mn_initial
        else:
            candidate['_mn_match'] = False


def _rank_sort_key(record: Dict) -> tuple:
    """
    Sort key для ранжирования результатов.
    Quantity first: больше matched_keys = лучше, затем лучший приоритет метода.
    """
    matched_keys = record.get('matched_keys', [])
    return (-len(matched_keys), _get_best_match_priority(matched_keys))


class ClickHouseSearchEngine:
    """
    ClickHouseSearchEngine class for searching SSN data.

    This class provides the same search interface as the SQLite SearchEngine
    but uses ClickHouse for better performance on large datasets.

    All searches query a single unified table (ssn_data) instead of
    UNION ALL across 3 SQLite tables.
    """

    def __init__(self, include_mutants: bool = True):
        """
        Initialize ClickHouseSearchEngine.

        Args:
            include_mutants: Whether to search in ssn_mutants table as well (default True)
        """
        if not CLICKHOUSE_AVAILABLE:
            raise ImportError(
                "clickhouse-connect is not installed. "
                "Install with: pip install clickhouse-connect"
            )
        self.logger = logging.getLogger(self.__class__.__name__)
        self.table = SSN_TABLE
        self.mutants_table = SSN_MUTANTS_TABLE
        self.include_mutants = include_mutants

    def _safe_limit(self, limit) -> int:
        """
        Safely validate and process LIMIT parameter.

        Args:
            limit: Limit value to validate (int, str, or None)

        Returns:
            int: Safe limit value (default 100, max MAX_LIMIT_VALUE)
        """
        if limit is None:
            return 100

        is_valid, error = validate_limit(limit, max_limit=MAX_LIMIT_VALUE)
        if not is_valid:
            self.logger.warning(f"Invalid LIMIT value rejected: {limit} - {error}")
            return 100

        try:
            safe_limit = int(limit)
            return min(max(1, safe_limit), MAX_LIMIT_VALUE)
        except (ValueError, TypeError):
            return 100

    def _mask_ssn(self, ssn: str) -> str:
        """
        Mask SSN to show only last 4 digits.

        Args:
            ssn: Social Security Number string

        Returns:
            str: Masked SSN (e.g., "***-**-6789")
        """
        if not ssn or len(ssn) < 4:
            return "***"
        last_four = ''.join(c for c in ssn if c.isdigit())[-4:]
        return f"***-**-{last_four}"

    def _format_results_to_json(self, results: List[Dict], indent: int = 2) -> str:
        """
        Format search results as JSON string.

        Args:
            results: List of dictionaries to format
            indent: Number of spaces for JSON indentation (default: 2)

        Returns:
            str: JSON formatted string
        """
        try:
            return json.dumps(results, indent=indent, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as e:
            self.logger.error(f"JSON serialization error: {e}")
            return json.dumps({"error": "Failed to serialize results"})

    def _execute_search(self, query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Execute a ClickHouse search query with parameters.

        Args:
            query: SQL query with named parameters (e.g., {ssn:String})
            params: Dictionary of parameter values

        Returns:
            list: List of dictionaries containing search results

        Raises:
            Exception: If database query fails
        """
        try:
            results = execute_query(query, parameters=params)
            self.logger.info(f"Search completed. Found {len(results)} record(s)")
            return results

        except Exception as e:
            self.logger.error(f"Database error during search: {e}")
            raise

    def _search_by_last4_ssn(self, last4: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Search for records by last 4 digits of SSN.

        Args:
            last4: Last 4 digits of SSN
            limit: Optional maximum number of results

        Returns:
            list: List of matching records
        """
        if not last4 or not str(last4).isdigit() or len(str(last4)) != 4:
            self.logger.warning(f"Invalid last4 SSN format: {last4}")
            return []

        safe_limit = self._safe_limit(limit)

        if self.include_mutants:
            query = f"""
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {self.table}
            WHERE endsWith(ssn, {{last4:String}})
            UNION ALL
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {self.mutants_table}
            WHERE endsWith(ssn, {{last4:String}})
            LIMIT {{limit:UInt32}}
            """
        else:
            query = f"""
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {self.table}
            WHERE endsWith(ssn, {{last4:String}})
            LIMIT {{limit:UInt32}}
            """

        self.logger.info(f"Searching by last 4 digits of SSN: ***-**-{last4}")
        return self._execute_search(query, {"last4": f"-{last4}", "limit": safe_limit})

    def search_by_ssn(self, ssn: str, limit: Optional[int] = None) -> str:
        """
        Search for records by Social Security Number.

        Supports three formats:
        1. XXX-XX-XXXX (formatted with dashes)
        2. XXXXXXXXX (9 digits without dashes)
        3. XXXX (last 4 digits only)

        Args:
            ssn: Social Security Number (can include dashes and spaces)
            limit: Optional maximum number of results

        Returns:
            str: JSON string with matching records
        """
        is_valid, error = validate_ssn(str(ssn))
        if not is_valid:
            self.logger.warning(f"SSN validation failed: {error}")
            return self._format_results_to_json([])

        normalized_ssn = ''.join(c for c in str(ssn) if c.isdigit())

        if len(normalized_ssn) == 4:
            self.logger.info("Detected last 4 digits search")
            results = self._search_by_last4_ssn(normalized_ssn, limit=limit)
            return self._format_results_to_json(results)

        if len(normalized_ssn) != 9:
            self.logger.warning(f"Invalid SSN format: expected 9 or 4 digits, got {len(normalized_ssn)}")
            return self._format_results_to_json([])

        formatted_ssn = f"{normalized_ssn[:3]}-{normalized_ssn[3:5]}-{normalized_ssn[5:]}"
        safe_limit = self._safe_limit(limit)

        if self.include_mutants:
            query = f"""
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {self.table}
            WHERE ssn = {{ssn:String}}
            UNION ALL
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {self.mutants_table}
            WHERE ssn = {{ssn:String}}
            LIMIT {{limit:UInt32}}
            """
        else:
            query = f"""
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {self.table}
            WHERE ssn = {{ssn:String}}
            LIMIT {{limit:UInt32}}
            """

        self.logger.info(f"Searching by full SSN: {self._mask_ssn(formatted_ssn)}")
        results = self._execute_search(query, {"ssn": formatted_ssn, "limit": safe_limit})
        return self._format_results_to_json(results)

    def search_by_name_zip(self, firstname: str, lastname: str, zip_code: str, limit: Optional[int] = None) -> str:
        """
        Search for records by first name, last name, and ZIP code.

        Args:
            firstname: First name to search for
            lastname: Last name to search for
            zip_code: ZIP code to search for
            limit: Optional maximum number of results

        Returns:
            str: JSON string with matching records
        """
        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""
        zip_code = sanitize_string(str(zip_code).strip(), max_length=10) or ""

        if not firstname or not lastname:
            self.logger.warning("Firstname and lastname are required for name+zip search")
            return self._format_results_to_json([])

        is_valid, error = validate_name(firstname, "firstname")
        if not is_valid:
            self.logger.warning(f"Invalid firstname: {error}")
            return self._format_results_to_json([])

        is_valid, error = validate_name(lastname, "lastname")
        if not is_valid:
            self.logger.warning(f"Invalid lastname: {error}")
            return self._format_results_to_json([])

        safe_limit = self._safe_limit(limit)

        query = f"""
        SELECT
            id, firstname, lastname, middlename, address, city, state, zip,
            phone, ssn, dob, email, source_table
        FROM {self.table}
        WHERE lowerUTF8(firstname) = lowerUTF8({{firstname:String}})
          AND lowerUTF8(lastname) = lowerUTF8({{lastname:String}})
          AND zip = {{zip:String}}
        LIMIT {{limit:UInt32}}
        """

        self.logger.info("Searching by name+zip")
        results = self._execute_search(query, {
            "firstname": firstname,
            "lastname": lastname,
            "zip": zip_code,
            "limit": safe_limit
        })
        return self._format_results_to_json(results)

    def search_by_name_address(self, firstname: str, lastname: str, address: str, limit: Optional[int] = None) -> str:
        """
        Search for records by first name, last name, and address.

        Args:
            firstname: First name to search for
            lastname: Last name to search for
            address: Address to search for
            limit: Optional maximum number of results

        Returns:
            str: JSON string with matching records
        """
        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""
        address = sanitize_address(str(address).strip()) or ""

        if not firstname or not lastname:
            self.logger.warning("Firstname and lastname are required for name+address search")
            return self._format_results_to_json([])

        is_valid, error = validate_name(firstname, "firstname")
        if not is_valid:
            self.logger.warning(f"Invalid firstname: {error}")
            return self._format_results_to_json([])

        is_valid, error = validate_name(lastname, "lastname")
        if not is_valid:
            self.logger.warning(f"Invalid lastname: {error}")
            return self._format_results_to_json([])

        safe_limit = self._safe_limit(limit)

        query = f"""
        SELECT
            id, firstname, lastname, middlename, address, city, state, zip,
            phone, ssn, dob, email, source_table
        FROM {self.table}
        WHERE lowerUTF8(firstname) = lowerUTF8({{firstname:String}})
          AND lowerUTF8(lastname) = lowerUTF8({{lastname:String}})
          AND lowerUTF8(address) = lowerUTF8({{address:String}})
        LIMIT {{limit:UInt32}}
        """

        self.logger.info("Searching by name+address")
        results = self._execute_search(query, {
            "firstname": firstname,
            "lastname": lastname,
            "address": address,
            "limit": safe_limit
        })
        return self._format_results_to_json(results)

    def _search_by_bloom_key_phone(
        self,
        firstname: str,
        lastname: str,
        all_phones: List[str],
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Search for SSN records by bloom_key_phone (fastest method).

        Uses optimized lookup tables with ORDER BY (bloom_key_phone, id)
        for O(1) point query performance.
        Searches in both ssn_data and ssn_mutants lookup tables.

        Args:
            firstname: First name
            lastname: Last name
            all_phones: List of phone numbers
            limit: Optional limit

        Returns:
            list: Matching records
        """
        if not all_phones:
            return []

        # Generate bloom keys for all phones
        bloom_keys = []
        for phone in all_phones:
            key = generate_bloom_key_phone(firstname, lastname, phone)
            if key and key not in bloom_keys:
                bloom_keys.append(key)

        if not bloom_keys:
            return []

        safe_limit = self._safe_limit(limit)

        # Use optimized lookup tables with ORDER BY (bloom_key_phone, id)
        # These tables provide 5-6x faster point queries
        if self.include_mutants:
            query = f"""
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {SSN_BLOOM_PHONE_LOOKUP}
            WHERE bloom_key_phone IN {{keys:Array(String)}}
            UNION ALL
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {SSN_MUTANTS_BLOOM_PHONE_LOOKUP}
            WHERE bloom_key_phone IN {{keys:Array(String)}}
            LIMIT {{limit:UInt32}}
            """
        else:
            query = f"""
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {SSN_BLOOM_PHONE_LOOKUP}
            WHERE bloom_key_phone IN {{keys:Array(String)}}
            LIMIT {{limit:UInt32}}
            """

        self.logger.info(f"Priority 0: Searching by BLOOM KEY PHONE ({len(bloom_keys)} keys) using optimized lookup tables")
        return self._execute_search(query, {"keys": bloom_keys, "limit": safe_limit})

    def _search_by_bloom_key_address(
        self,
        firstname: str,
        lastname: str,
        all_addresses: List[Dict],
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Search for SSN records by bloom_key_address (fast method).

        Uses optimized lookup tables with ORDER BY (bloom_key_address, id)
        for O(1) point query performance.
        Searches in both ssn_data and ssn_mutants lookup tables.

        Args:
            firstname: First name
            lastname: Last name
            all_addresses: List of dicts with 'address' and 'state' keys
            limit: Optional limit

        Returns:
            list: Matching records
        """
        if not all_addresses:
            return []

        # Generate bloom keys for all addresses
        bloom_keys = []
        for addr_data in all_addresses:
            if isinstance(addr_data, dict):
                address = addr_data.get('address', '')
                state = addr_data.get('state', '')
                key = generate_bloom_key_address(firstname, lastname, address, state)
                if key and key not in bloom_keys:
                    bloom_keys.append(key)

        if not bloom_keys:
            return []

        safe_limit = self._safe_limit(limit)

        # Use optimized lookup tables with ORDER BY (bloom_key_address, id)
        # These tables provide faster point queries
        if self.include_mutants:
            query = f"""
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {SSN_BLOOM_ADDRESS_LOOKUP}
            WHERE bloom_key_address IN {{keys:Array(String)}}
            UNION ALL
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {SSN_MUTANTS_BLOOM_ADDRESS_LOOKUP}
            WHERE bloom_key_address IN {{keys:Array(String)}}
            LIMIT {{limit:UInt32}}
            """
        else:
            query = f"""
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {SSN_BLOOM_ADDRESS_LOOKUP}
            WHERE bloom_key_address IN {{keys:Array(String)}}
            LIMIT {{limit:UInt32}}
            """

        self.logger.info(f"Priority 1: Searching by BLOOM KEY ADDRESS ({len(bloom_keys)} keys) using optimized lookup tables")
        return self._execute_search(query, {"keys": bloom_keys, "limit": safe_limit})

    def search_by_bloom_keys(
        self,
        bloom_keys_phone: Optional[List[str]] = None,
        bloom_keys_address: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Direct search by pre-generated bloom keys.

        This is the lowest-level method for bloom key search.
        Useful when you've already generated the keys externally.
        Searches in both ssn_data and ssn_mutants tables.

        Args:
            bloom_keys_phone: List of phone bloom keys
            bloom_keys_address: List of address bloom keys
            limit: Optional limit

        Returns:
            list: Matching records
        """
        safe_limit = self._safe_limit(limit)

        # Try phone keys first
        if bloom_keys_phone:
            if self.include_mutants:
                query = f"""
                SELECT
                    id, firstname, lastname, middlename, address, city, state, zip,
                    phone, ssn, dob, email, source_table
                FROM {self.table}
                WHERE bloom_key_phone IN {{keys:Array(String)}}
                UNION ALL
                SELECT
                    id, firstname, lastname, middlename, address, city, state, zip,
                    phone, ssn, dob, email, source_table
                FROM {self.mutants_table}
                WHERE bloom_key_phone IN {{keys:Array(String)}}
                LIMIT {{limit:UInt32}}
                """
            else:
                query = f"""
                SELECT
                    id, firstname, lastname, middlename, address, city, state, zip,
                    phone, ssn, dob, email, source_table
                FROM {self.table}
                WHERE bloom_key_phone IN {{keys:Array(String)}}
                LIMIT {{limit:UInt32}}
                """
            self.logger.info(f"Searching by BLOOM KEY PHONE ({len(bloom_keys_phone)} keys)")
            results = self._execute_search(query, {"keys": bloom_keys_phone, "limit": safe_limit})
            if results:
                return results

        # Try address keys
        if bloom_keys_address:
            if self.include_mutants:
                query = f"""
                SELECT
                    id, firstname, lastname, middlename, address, city, state, zip,
                    phone, ssn, dob, email, source_table
                FROM {self.table}
                WHERE bloom_key_address IN {{keys:Array(String)}}
                UNION ALL
                SELECT
                    id, firstname, lastname, middlename, address, city, state, zip,
                    phone, ssn, dob, email, source_table
                FROM {self.mutants_table}
                WHERE bloom_key_address IN {{keys:Array(String)}}
                LIMIT {{limit:UInt32}}
                """
            else:
                query = f"""
                SELECT
                    id, firstname, lastname, middlename, address, city, state, zip,
                    phone, ssn, dob, email, source_table
                FROM {self.table}
                WHERE bloom_key_address IN {{keys:Array(String)}}
                LIMIT {{limit:UInt32}}
                """
            self.logger.info(f"Searching by BLOOM KEY ADDRESS ({len(bloom_keys_address)} keys)")
            results = self._execute_search(query, {"keys": bloom_keys_address, "limit": safe_limit})
            if results:
                return results

        return []

    def _search_by_phone_match(self, firstname: str, lastname: str, all_phones: List[str], limit: Optional[int] = None) -> List[Dict]:
        """
        Search for SSN records by firstname + lastname + phone.

        Args:
            firstname: First name
            lastname: Last name
            all_phones: List of phone numbers
            limit: Optional limit

        Returns:
            list: Matching records
        """
        if not all_phones:
            return []

        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""

        if not firstname or not lastname:
            return []

        normalized_phones = []
        for phone in all_phones:
            if phone:
                digits = ''.join(c for c in str(phone) if c.isdigit())
                if len(digits) == 10:
                    normalized_phones.append(digits)
                elif len(digits) == 11 and digits.startswith('1'):
                    normalized_phones.append(digits[1:])

        if not normalized_phones:
            return []

        safe_limit = self._safe_limit(limit)

        query = f"""
        SELECT
            id, firstname, lastname, middlename, address, city, state, zip,
            phone, ssn, dob, email, source_table
        FROM {self.table}
        WHERE lowerUTF8(firstname) = lowerUTF8({{firstname:String}})
          AND lowerUTF8(lastname) = lowerUTF8({{lastname:String}})
          AND replaceAll(replaceAll(replaceAll(phone, '(', ''), ')', ''), '-', '') IN {{phones:Array(String)}}
        LIMIT {{limit:UInt32}}
        """

        self.logger.info(f"Priority 1: Searching by phone ({len(normalized_phones)} numbers)")
        return self._execute_search(query, {
            "firstname": firstname,
            "lastname": lastname,
            "phones": normalized_phones,
            "limit": safe_limit
        })

    def _search_by_address_match(self, firstname: str, lastname: str, all_addresses: List[str], limit: Optional[int] = None) -> List[Dict]:
        """
        Search for SSN records by firstname + lastname + address.

        Uses LIKE for fuzzy matching with address variants.

        Args:
            firstname: First name
            lastname: Last name
            all_addresses: List of addresses
            limit: Optional limit

        Returns:
            list: Matching records
        """
        if not all_addresses:
            return []

        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""

        if not firstname or not lastname:
            return []

        normalized_addresses = []
        for addr in all_addresses:
            if addr and isinstance(addr, str):
                addr = sanitize_address(addr) or ""
                if addr:
                    normalized_addresses.append(addr.upper())

        if not normalized_addresses:
            return []

        safe_limit = self._safe_limit(limit)

        # Use positionCaseInsensitive for fuzzy matching
        query = f"""
        SELECT
            id, firstname, lastname, middlename, address, city, state, zip,
            phone, ssn, dob, email, source_table
        FROM {self.table}
        WHERE lowerUTF8(firstname) = lowerUTF8({{firstname:String}})
          AND lowerUTF8(lastname) = lowerUTF8({{lastname:String}})
          AND arrayExists(x -> positionCaseInsensitive(address, x) > 0, {{addresses:Array(String)}})
        LIMIT {{limit:UInt32}}
        """

        self.logger.info(f"Priority 2: Searching by address ({len(normalized_addresses)} addresses)")
        return self._execute_search(query, {
            "firstname": firstname,
            "lastname": lastname,
            "addresses": normalized_addresses,
            "limit": safe_limit
        })

    def _search_by_zip_match(self, firstname: str, lastname: str, all_zips: List[str], limit: Optional[int] = None) -> List[Dict]:
        """
        Search for SSN records by firstname + lastname + ZIP.

        Args:
            firstname: First name
            lastname: Last name
            all_zips: List of ZIP codes
            limit: Optional limit

        Returns:
            list: Matching records
        """
        if not all_zips:
            return []

        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""

        if not firstname or not lastname:
            return []

        normalized_zips = []
        for z in all_zips:
            if z:
                z_clean = sanitize_string(str(z).strip(), max_length=10)
                if z_clean:
                    normalized_zips.append(z_clean)

        if not normalized_zips:
            return []

        safe_limit = self._safe_limit(limit)

        query = f"""
        SELECT
            id, firstname, lastname, middlename, address, city, state, zip,
            phone, ssn, dob, email, source_table
        FROM {self.table}
        WHERE lowerUTF8(firstname) = lowerUTF8({{firstname:String}})
          AND lowerUTF8(lastname) = lowerUTF8({{lastname:String}})
          AND zip IN {{zips:Array(String)}}
        LIMIT {{limit:UInt32}}
        """

        self.logger.info(f"Priority 3: Searching by ZIP ({len(normalized_zips)} codes)")
        return self._execute_search(query, {
            "firstname": firstname,
            "lastname": lastname,
            "zips": normalized_zips,
            "limit": safe_limit
        })

    def _search_by_state_match(self, firstname: str, lastname: str, all_states: List[str], limit: Optional[int] = None) -> List[Dict]:
        """
        Search for SSN records by firstname + lastname + state.
        Priority 4 fallback - less precise but catches outdated addresses.

        Args:
            firstname: First name
            lastname: Last name
            all_states: List of state codes (2-letter)
            limit: Optional limit

        Returns:
            list: Matching records
        """
        if not all_states:
            return []

        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""

        if not firstname or not lastname:
            return []

        normalized_states = []
        for state in all_states:
            if state and isinstance(state, str):
                state_clean = state.upper().strip()
                if len(state_clean) == 2 and state_clean.isalpha():
                    normalized_states.append(state_clean)

        if not normalized_states:
            return []

        safe_limit = self._safe_limit(limit)

        query = f"""
        SELECT
            id, firstname, lastname, middlename, address, city, state, zip,
            phone, ssn, dob, email, source_table
        FROM {self.table}
        WHERE lowerUTF8(firstname) = lowerUTF8({{firstname:String}})
          AND lowerUTF8(lastname) = lowerUTF8({{lastname:String}})
          AND state IN {{states:Array(String)}}
        LIMIT {{limit:UInt32}}
        """

        self.logger.info(f"Priority 4: Searching by STATE ({len(normalized_states)} states: {normalized_states})")
        return self._execute_search(query, {
            "firstname": firstname,
            "lastname": lastname,
            "states": normalized_states,
            "limit": safe_limit
        })

    def _search_by_city_state_match(self, firstname: str, lastname: str, city: str, state: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Search for SSN records by firstname + lastname + city + state.

        Args:
            firstname: First name
            lastname: Last name
            city: City name
            state: State code (2-letter)
            limit: Optional limit

        Returns:
            list: Matching records
        """
        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""

        if not firstname or not lastname:
            return []

        city = sanitize_string(str(city).strip(), max_length=100) if city else ""
        state = state.upper().strip() if state and isinstance(state, str) else ""

        if not city or not state:
            return []

        if len(state) != 2 or not state.isalpha():
            self.logger.warning(f"Invalid state format: {state}")
            return []

        safe_limit = self._safe_limit(limit)

        query = f"""
        SELECT
            id, firstname, lastname, middlename, address, city, state, zip,
            phone, ssn, dob, email, source_table
        FROM {self.table}
        WHERE lowerUTF8(firstname) = lowerUTF8({{firstname:String}})
          AND lowerUTF8(lastname) = lowerUTF8({{lastname:String}})
          AND lowerUTF8(city) = lowerUTF8({{city:String}})
          AND state = {{state:String}}
        LIMIT {{limit:UInt32}}
        """

        self.logger.info(f"Searching by name+city+state: {city}, {state}")
        return self._execute_search(query, {
            "firstname": firstname,
            "lastname": lastname,
            "city": city,
            "state": state,
            "limit": safe_limit
        })

    def search_by_searchbug_data(
        self,
        firstname: str,
        lastname: str,
        all_zips: Optional[List[str]] = None,
        all_phones: Optional[List[str]] = None,
        all_addresses: Optional[List[str]] = None,
        all_addresses_with_state: Optional[List[Dict]] = None,
        all_states: Optional[List[str]] = None,
        limit: Optional[int] = None,
        use_bloom_keys: bool = True
    ) -> List[Dict]:
        """
        Search for SSN records matching external API data with priority-based matching.

        Priority order (stops at first match):
        0. [NEW] bloom_key_phone - composite Bloom key (fastest)
        1. [NEW] bloom_key_address - composite Bloom key (fast)
        2. firstname + lastname + phone (fallback if Bloom keys not populated)
        3. firstname + lastname + address (fuzzy match)
        4. firstname + lastname + ZIP
        5. firstname + lastname + state

        Args:
            firstname: First name to search for
            lastname: Last name to search for
            all_zips: List of ZIP codes (optional)
            all_phones: List of phone numbers (optional)
            all_addresses: List of addresses as strings (optional, for fuzzy match)
            all_addresses_with_state: List of dicts with 'address' and 'state' (for Bloom keys)
            all_states: List of state codes (optional)
            limit: Optional maximum number of results
            use_bloom_keys: Whether to try Bloom key search first (default True)

        Returns:
            list: List of matching records (as dicts, not JSON string)
        """
        firstname = sanitize_name(str(firstname).strip()) or ""
        lastname = sanitize_name(str(lastname).strip()) or ""

        if not firstname or not lastname:
            self.logger.warning("Firstname and lastname are required")
            return []

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
            f"addresses_with_state={len(all_addresses_with_state) if all_addresses_with_state else 0}, "
            f"zips={len(all_zips) if all_zips else 0}, "
            f"states={len(all_states) if all_states else 0}, "
            f"use_bloom_keys={use_bloom_keys}"
        )

        # Priority 0: Try Bloom key phone search (fastest)
        if use_bloom_keys and all_phones and len(all_phones) > 0:
            results = self._search_by_bloom_key_phone(firstname, lastname, all_phones, limit)
            if results:
                self.logger.info(f"Found {len(results)} match(es) by BLOOM KEY PHONE (Priority 0)")
                return results
            self.logger.info("No matches by bloom key phone, trying next priority")

        # Priority 1: Try Bloom key address search
        if use_bloom_keys and all_addresses_with_state and len(all_addresses_with_state) > 0:
            results = self._search_by_bloom_key_address(firstname, lastname, all_addresses_with_state, limit)
            if results:
                self.logger.info(f"Found {len(results)} match(es) by BLOOM KEY ADDRESS (Priority 1)")
                return results
            self.logger.info("No matches by bloom key address, trying next priority")

        # Priority 2: Try phone search (fallback to full-text if Bloom failed)
        if all_phones and len(all_phones) > 0:
            results = self._search_by_phone_match(firstname, lastname, all_phones, limit)
            if results:
                self.logger.info(f"Found {len(results)} match(es) by PHONE (Priority 2)")
                return results
            self.logger.info("No matches by phone, trying next priority")

        # Priority 3: Try address search (fuzzy)
        if all_addresses and len(all_addresses) > 0:
            results = self._search_by_address_match(firstname, lastname, all_addresses, limit)
            if results:
                self.logger.info(f"Found {len(results)} match(es) by ADDRESS (Priority 3)")
                return results
            self.logger.info("No matches by address, trying next priority")

        # Priority 4: Try ZIP search
        if all_zips and len(all_zips) > 0:
            results = self._search_by_zip_match(firstname, lastname, all_zips, limit)
            if results:
                self.logger.info(f"Found {len(results)} match(es) by ZIP (Priority 4)")
                return results
            self.logger.info("No matches by ZIP, trying next priority")

        # Priority 5: Try state search (fallback)
        if all_states and len(all_states) > 0:
            results = self._search_by_state_match(firstname, lastname, all_states, limit)
            if results:
                self.logger.info(f"Found {len(results)} match(es) by STATE (Priority 5)")
                return results
            self.logger.info("No matches by state")

        self.logger.info("No SSN matches found with any criteria")
        return []

    def search_by_searchbug_dict(
        self,
        searchbug_data: Dict,
        limit: Optional[int] = None,
        use_bloom_keys: bool = True
    ) -> List[Dict]:
        """
        Search for SSN records using SearchBug API response format.

        This is a convenience method that accepts the raw SearchBug format
        and automatically generates Bloom keys.

        Args:
            searchbug_data: Dict with SearchBug API format:
                - firstname: str
                - lastname: str
                - phones: List[str] (optional)
                - addresses: List[Dict] with 'address' and 'state' (optional)
            limit: Optional maximum number of results
            use_bloom_keys: Whether to try Bloom key search first (default True)

        Returns:
            list: List of matching records
        """
        firstname = searchbug_data.get('firstname', '')
        lastname = searchbug_data.get('lastname', '')
        phones = searchbug_data.get('phones', [])
        addresses = searchbug_data.get('addresses', [])

        # Extract states and address strings for fallback searches
        all_states = []
        all_addresses_str = []
        for addr in addresses:
            if isinstance(addr, dict):
                state = addr.get('state', '')
                if state and state not in all_states:
                    all_states.append(state)
                addr_str = addr.get('address', '')
                if addr_str:
                    all_addresses_str.append(addr_str)

        return self.search_by_searchbug_data(
            firstname=firstname,
            lastname=lastname,
            all_phones=phones,
            all_addresses=all_addresses_str,
            all_addresses_with_state=addresses,
            all_states=all_states,
            limit=limit,
            use_bloom_keys=use_bloom_keys
        )

    def _search_by_search_keys(
        self,
        search_keys: Dict[str, List[str]],
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Search for SSN records using Level 2 search keys (8 methods).

        Tries each key type in priority order (1-8) until a match is found.
        Searches in both ssn_data and ssn_mutants tables.

        Args:
            search_keys: Dict with search_keys_1 through search_keys_8
            limit: Optional limit

        Returns:
            list: Matching records
        """
        safe_limit = self._safe_limit(limit)

        # Try each key type in order (1-8)
        for key_num in range(1, 9):
            key_name = f'search_keys_{key_num}'
            keys = search_keys.get(key_name, [])

            if not keys:
                continue

            col_name = f'search_key_{key_num}'

            # Build query for both tables if include_mutants is True
            if self.include_mutants:
                query = f"""
                SELECT
                    id, firstname, lastname, middlename, address, city, state, zip,
                    phone, ssn, dob, email, source_table
                FROM {self.table}
                WHERE {col_name} IN {{keys:Array(String)}}
                UNION ALL
                SELECT
                    id, firstname, lastname, middlename, address, city, state, zip,
                    phone, ssn, dob, email, source_table
                FROM {self.mutants_table}
                WHERE {col_name} IN {{keys:Array(String)}}
                LIMIT {{limit:UInt32}}
                """
            else:
                query = f"""
                SELECT
                    id, firstname, lastname, middlename, address, city, state, zip,
                    phone, ssn, dob, email, source_table
                FROM {self.table}
                WHERE {col_name} IN {{keys:Array(String)}}
                LIMIT {{limit:UInt32}}
                """

            self.logger.info(f"Level 2 search: trying {col_name} ({len(keys)} keys)")
            results = self._execute_search(query, {"keys": keys, "limit": safe_limit})

            if results:
                self.logger.info(f"Level 2: Found {len(results)} match(es) by {col_name}")
                return results

        return []

    def _filter_candidates_by_search_keys(
        self,
        candidates: List[Dict],
        searchbug_data: Dict,
        input_address: str = "",
        searchbug_primary_address: str = ""
    ) -> List[Dict]:
        """
        Level 2: Фильтрация кандидатов по 8 методам runtime matching.

        Это ключевой метод двухуровневой системы поиска:
        1. Bloom-фильтрация (Level 1) уже отсеяла "точно нет" кандидатов
        2. Теперь для каждого кандидата генерируем ключи с данными SearchBug
        3. Сравниваем с ключами запроса (из SearchBug)
        4. Возвращаем только тех кандидатов, у которых есть совпадение

        ВАЖНО: MN и DOB_YEAR берутся из SearchBug, а не из кандидата!
        Это позволяет найти соответствия, даже если в локальной БД нет middlename/dob.

        8 типов ключей (все lowercase):
        1. FN:MN:LN:DOB_YEAR:PHONE
        2. FN:MN:LN:DOB_YEAR:ADDR#:STREET:STATE
        3. FN:LN:DOB_YEAR:PHONE
        4. FN:LN:DOB_YEAR:ADDR#:STREET:STATE
        5. FN:MN:LN:PHONE
        6. FN:MN:LN:ADDR#:STREET:STATE
        7. FN:LN:ADDR#:STREET:STATE
        8. FN:LN:PHONE

        Args:
            candidates: Список кандидатов из ClickHouse (после Bloom-фильтрации)
            searchbug_data: Данные от SearchBug API с полями:
                - firstname, middlename, lastname, dob
                - phones: List[str] или List[Dict]
                - addresses: List[Dict] с полями address, state

        Returns:
            list: Отфильтрованный список кандидатов с добавленным полем 'matched_keys'
        """
        if not candidates:
            return []

        self.logger.info(
            f"Level 2 runtime matching: {len(candidates)} candidates"
        )

        # Генерируем все ключи запроса (из SearchBug) - уже использует все имена
        query_keys = generate_query_keys_from_searchbug(searchbug_data)

        if not query_keys:
            self.logger.warning("Level 2: No query keys generated from SearchBug data")
            return []

        self.logger.info(f"Level 2: Generated {len(query_keys)} query keys from SearchBug")

        # Собираем всех совпавших кандидатов (с возможными дубликатами по SSN)
        all_matched = []
        for candidate in candidates:
            # Генерируем ключи кандидата только из данных самой записи БД
            candidate_keys = generate_candidate_keys(candidate)

            if not candidate_keys:
                continue

            # Проверяем пересечение по ключам
            matched_key_values = candidate_keys.keys() & query_keys.keys()

            if matched_key_values:
                candidate['matched_keys'] = [
                    f"{query_keys[k]}: {k}" for k in matched_key_values
                ]
                candidate['match_level'] = 2
                all_matched.append(candidate)

        # Дедупликация по SSN: объединяем matched_keys, оставляем лучшую запись
        # Приоритет: 1) совпадение адреса с SB primary/input, 2) кол-во заполненных полей
        ssn_best = {}
        ssn_all_matched_keys = {}

        # Нормализуем адреса для сравнения при дедупликации
        sb_key = _normalize_address_for_match(searchbug_primary_address) if searchbug_primary_address else ''
        input_key = _normalize_address_for_match(input_address) if input_address else ''

        def _dedup_addr_score(record):
            """Оценка записи по совпадению адреса: SB primary=2, input=1, нет=0"""
            addr_key = _normalize_address_for_match(record.get('address', ''))
            score = 0
            if sb_key and addr_key == sb_key:
                score += 2
            if input_key and addr_key == input_key:
                score += 1
            return score

        for record in all_matched:
            ssn = record.get('ssn')
            if not ssn:
                continue

            if ssn not in ssn_best:
                ssn_best[ssn] = record
                ssn_all_matched_keys[ssn] = set(record.get('matched_keys', []))
            else:
                # Объединяем matched_keys от всех записей с одним SSN
                ssn_all_matched_keys[ssn].update(record.get('matched_keys', []))
                # Выбираем лучшую запись: сначала по адресу, потом по кол-ву полей
                existing = ssn_best[ssn]
                existing_addr_score = _dedup_addr_score(existing)
                current_addr_score = _dedup_addr_score(record)
                if current_addr_score > existing_addr_score:
                    ssn_best[ssn] = record
                elif current_addr_score == existing_addr_score:
                    existing_fields = sum(1 for v in existing.values() if v and str(v).strip())
                    current_fields = sum(1 for v in record.values() if v and str(v).strip())
                    if current_fields > existing_fields:
                        ssn_best[ssn] = record

        # Применяем объединённые matched_keys
        for ssn, record in ssn_best.items():
            record['matched_keys'] = sorted(ssn_all_matched_keys[ssn])

        # Сортируем: quantity first (больше ключей = лучше), затем quality (меньше приоритет = лучше)
        filtered = sorted(ssn_best.values(), key=_rank_sort_key)

        self.logger.info(f"Level 2: {len(filtered)} unique SSN(s) passed runtime matching")
        if filtered:
            best = filtered[0]
            self.logger.info(
                f"Level 2 best match: SSN={best.get('ssn')}, "
                f"matched_keys_count={len(best.get('matched_keys', []))}, "
                f"best_priority={_get_best_match_priority(best.get('matched_keys', []))}"
            )

        return filtered

    def search_by_searchbug_two_level(
        self,
        searchbug_data: Dict,
        limit: Optional[int] = None,
        input_address: str = "",
        searchbug_primary_address: str = ""
    ) -> List[Dict]:
        """
        Two-level search for SSN matching using SearchBug data.

        Level 1: Bloom-фильтрация (быстро отсекаем "точно нет")
        - bloom_key_phone: {f}:{l}:{phone}
        - bloom_key_address: {f}:{l}:{addr#}:{street}:{state}

        Level 2: Runtime Matching по 8 методам
        Для каждого кандидата из Level 1:
        - Берём FN, LN, phone, address, state из ClickHouse
        - Берём MN, DOB_YEAR из SearchBug
        - Генерируем 8 ключей и сравниваем с ключами запроса

        8 типов ключей (все lowercase):
        1. FN:MN:LN:DOB_YEAR:PHONE
        2. FN:MN:LN:DOB_YEAR:ADDR#:STREET:STATE
        3. FN:LN:DOB_YEAR:PHONE
        4. FN:LN:DOB_YEAR:ADDR#:STREET:STATE
        5. FN:MN:LN:PHONE
        6. FN:MN:LN:ADDR#:STREET:STATE
        7. FN:LN:ADDR#:STREET:STATE
        8. FN:LN:PHONE

        Args:
            searchbug_data: Dict with SearchBug API format:
                - firstname: str
                - middlename: str (optional)
                - lastname: str
                - dob: str (optional)
                - phones: List[str] or List[Dict] (optional)
                - addresses: List[Dict] with 'address' and 'state' (optional)
            limit: Optional maximum number of results

        Returns:
            list: List of matching records with match_level and matched_keys info
        """
        firstname = searchbug_data.get('firstname', '')
        lastname = searchbug_data.get('lastname', '')

        if not firstname or not lastname:
            self.logger.warning("Firstname and lastname are required for two-level search")
            return []

        # Извлекаем телефоны для Bloom-поиска
        phones_raw = searchbug_data.get('phones', []) or []
        all_phones = []
        for p in phones_raw:
            if isinstance(p, dict):
                phone_num = p.get('phone_number', '')
            else:
                phone_num = str(p) if p else ''
            if phone_num:
                all_phones.append(phone_num)

        # Извлекаем адреса для Bloom-поиска
        addresses = searchbug_data.get('addresses', []) or []

        self.logger.info(
            f"Two-level search for: {firstname} {lastname}, "
            f"middlename={searchbug_data.get('middlename')}, "
            f"dob={searchbug_data.get('dob')}, "
            f"phones={len(all_phones)}, "
            f"addresses={len(addresses)}"
        )

        # =====================================================================
        # Level 1: Bloom-фильтрация (использует ВСЕ вариации имён от SearchBug)
        # =====================================================================
        self.logger.info("=== Level 1: Bloom Key Filtering ===")

        # Генерируем bloom-ключи для ВСЕХ вариаций имён (если есть names)
        bloom_results = generate_all_bloom_keys_from_searchbug(searchbug_data)
        bloom_keys_phone = bloom_results.get('bloom_keys_phone', [])
        bloom_keys_address = bloom_results.get('bloom_keys_address', [])

        candidates = []

        # Search by bloom key phone (using optimized lookup tables)
        if bloom_keys_phone:
            if self.include_mutants:
                query = f"""
                SELECT id, firstname, lastname, middlename, address, city, state, zip,
                       phone, ssn, dob, email, source_table
                FROM {SSN_BLOOM_PHONE_LOOKUP}
                WHERE bloom_key_phone IN {{keys:Array(String)}}
                UNION ALL
                SELECT id, firstname, lastname, middlename, address, city, state, zip,
                       phone, ssn, dob, email, source_table
                FROM {SSN_MUTANTS_BLOOM_PHONE_LOOKUP}
                WHERE bloom_key_phone IN {{keys:Array(String)}}
                LIMIT 500
                """
            else:
                query = f"""
                SELECT id, firstname, lastname, middlename, address, city, state, zip,
                       phone, ssn, dob, email, source_table
                FROM {SSN_BLOOM_PHONE_LOOKUP}
                WHERE bloom_key_phone IN {{keys:Array(String)}}
                LIMIT 500
                """
            phone_candidates = self._execute_search(query, {"keys": bloom_keys_phone})
            if phone_candidates:
                self.logger.info(f"Level 1: Found {len(phone_candidates)} candidates by BLOOM KEY PHONE ({len(bloom_keys_phone)} keys)")
                candidates.extend(phone_candidates)

        # Search by bloom key address (always, using optimized lookup tables)
        if bloom_keys_address:
            if self.include_mutants:
                query = f"""
                SELECT id, firstname, lastname, middlename, address, city, state, zip,
                       phone, ssn, dob, email, source_table
                FROM {SSN_BLOOM_ADDRESS_LOOKUP}
                WHERE bloom_key_address IN {{keys:Array(String)}}
                UNION ALL
                SELECT id, firstname, lastname, middlename, address, city, state, zip,
                       phone, ssn, dob, email, source_table
                FROM {SSN_MUTANTS_BLOOM_ADDRESS_LOOKUP}
                WHERE bloom_key_address IN {{keys:Array(String)}}
                LIMIT 500
                """
            else:
                query = f"""
                SELECT id, firstname, lastname, middlename, address, city, state, zip,
                       phone, ssn, dob, email, source_table
                FROM {SSN_BLOOM_ADDRESS_LOOKUP}
                WHERE bloom_key_address IN {{keys:Array(String)}}
                LIMIT 500
                """
            address_candidates = self._execute_search(query, {"keys": bloom_keys_address})
            if address_candidates:
                self.logger.info(f"Level 1: Found {len(address_candidates)} candidates by BLOOM KEY ADDRESS ({len(bloom_keys_address)} keys)")
                candidates.extend(address_candidates)

        if not candidates:
            self.logger.info("Level 1: No candidates found by Bloom keys")
            return []

        self.logger.info(f"Level 1: {len(candidates)} total candidates (before Level 2)")

        # =====================================================================
        # Level 2: Runtime Matching по 8 методам
        # =====================================================================
        self.logger.info("=== Level 2: Runtime Matching (8 methods) ===")

        # НЕ дедуплицируем до Level 2 — мутанты с тем же SSN могут не пройти
        # Level 2, а оригинальная запись — пройдёт. Дедупликация после matching.
        results = self._filter_candidates_by_search_keys(
            candidates, searchbug_data,
            input_address=input_address,
            searchbug_primary_address=searchbug_primary_address
        )

        if results:
            # Apply final limit
            safe_limit = self._safe_limit(limit)
            if len(results) > safe_limit:
                results = results[:safe_limit]
            self.logger.info(f"Two-level search: Returning {len(results)} final match(es)")
            return results

        self.logger.info("Two-level search: No matches passed Level 2 filtering")
        return []

    def search_by_fields(
        self,
        firstname: str,
        lastname: str,
        city: Optional[str] = None,
        state: Optional[str] = None,
        phone: Optional[str] = None,
        zip: Optional[str] = None,
        limit: Optional[int] = None
    ) -> str:
        """
        Search for SSN records by firstname + lastname with optional filters.

        Priority:
        1. firstname + lastname + phone (if provided)
        2. firstname + lastname + city + state (if both provided)
        3. firstname + lastname + zip (if provided)
        4. firstname + lastname + state (if provided, fallback)

        Args:
            firstname: First name (required)
            lastname: Last name (required)
            city: City name (optional)
            state: State code (optional)
            phone: Phone number (optional)
            zip: ZIP code (optional)
            limit: Optional maximum number of results

        Returns:
            str: JSON string with matching records
        """
        firstname = sanitize_name(str(firstname).strip()) if firstname else ""
        lastname = sanitize_name(str(lastname).strip()) if lastname else ""

        if not firstname or not lastname:
            self.logger.warning("Firstname and lastname are required for search_by_fields")
            return self._format_results_to_json([])

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
            if results:
                self.logger.info(f"Found {len(results)} match(es) by PHONE")
                return self._format_results_to_json(results)
            self.logger.info("No matches by phone")

        # Priority 2: Try city + state search if both provided
        if city and state:
            results = self._search_by_city_state_match(firstname, lastname, city, state, limit)
            if results:
                self.logger.info(f"Found {len(results)} match(es) by CITY+STATE")
                return self._format_results_to_json(results)
            self.logger.info("No matches by city+state")

        # Priority 3: Try ZIP search if provided
        if zip:
            results = self._search_by_zip_match(firstname, lastname, [zip], limit)
            if results:
                self.logger.info(f"Found {len(results)} match(es) by ZIP")
                return self._format_results_to_json(results)
            self.logger.info("No matches by ZIP")

        # Priority 4: Try state search (fallback)
        if state:
            results = self._search_by_state_match(firstname, lastname, [state], limit)
            if results:
                self.logger.info(f"Found {len(results)} match(es) by STATE")
                return self._format_results_to_json(results)
            self.logger.info("No matches by state")

        self.logger.info("No matches found with any criteria in search_by_fields")
        return self._format_results_to_json([])


# Convenience functions for simple API access

def search_by_ssn(ssn: str, limit: Optional[int] = None) -> str:
    """
    Convenience function to search by SSN.

    Args:
        ssn: Social Security Number
        limit: Optional maximum number of results

    Returns:
        str: JSON string with search results
    """
    engine = ClickHouseSearchEngine()
    return engine.search_by_ssn(ssn, limit=limit)


def search_by_name_zip(firstname: str, lastname: str, zip_code: str, limit: Optional[int] = None) -> str:
    """
    Convenience function to search by name and ZIP code.

    Args:
        firstname: First name
        lastname: Last name
        zip_code: ZIP code
        limit: Optional maximum number of results

    Returns:
        str: JSON string with search results
    """
    engine = ClickHouseSearchEngine()
    return engine.search_by_name_zip(firstname, lastname, zip_code, limit=limit)


def search_by_name_address(firstname: str, lastname: str, address: str, limit: Optional[int] = None) -> str:
    """
    Convenience function to search by name and address.

    Args:
        firstname: First name
        lastname: Last name
        address: Address
        limit: Optional maximum number of results

    Returns:
        str: JSON string with search results
    """
    engine = ClickHouseSearchEngine()
    return engine.search_by_name_address(firstname, lastname, address, limit=limit)


def search_by_searchbug_two_level(
    searchbug_data: Dict,
    limit: Optional[int] = None,
    input_address: str = "",
    searchbug_primary_address: str = ""
) -> List[Dict]:
    """
    Convenience function for two-level SearchBug search.

    Level 1: Bloom key filtering (fast elimination)
    Level 2: 8 exact matching methods

    Args:
        searchbug_data: Dict with SearchBug API format
        limit: Optional maximum number of results
        input_address: Original address from user input (for ranking boost)
        searchbug_primary_address: SearchBug primary address (for ranking boost, higher priority)

    Returns:
        list: List of matching records
    """
    engine = ClickHouseSearchEngine()
    return engine.search_by_searchbug_two_level(
        searchbug_data, limit=limit,
        input_address=input_address,
        searchbug_primary_address=searchbug_primary_address
    )


if __name__ == '__main__':
    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        engine = ClickHouseSearchEngine()

        print("\n" + "=" * 80)
        print("CLICKHOUSE SSN SEARCH ENGINE - DEMONSTRATION")
        print("=" * 80)

        # Demo 1: Search by SSN
        print("\n[1] SEARCH BY SSN")
        print("-" * 80)
        print("Searching for SSN: 123-45-6789")
        json_results = engine.search_by_ssn("123-45-6789")
        results = json.loads(json_results)
        print(f"Results found: {len(results)}")
        print(json_results[:500] + "..." if len(json_results) > 500 else json_results)

        # Demo 2: Search by Name and ZIP
        print("\n[2] SEARCH BY NAME AND ZIP")
        print("-" * 80)
        print("Searching for: John Doe, ZIP: 12345")
        json_results = engine.search_by_name_zip("John", "Doe", "12345")
        results = json.loads(json_results)
        print(f"Results found: {len(results)}")
        print(json_results[:500] + "..." if len(json_results) > 500 else json_results)

        print("\n" + "=" * 80)
        print("DEMONSTRATION COMPLETED")
        print("=" * 80 + "\n")

    except ImportError as e:
        print(f"\nClickHouse not available: {e}")
    except Exception as e:
        print(f"\nERROR: {e}")
