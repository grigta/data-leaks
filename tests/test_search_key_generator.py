"""
Unit tests for search_key_generator.py

Tests all parsing and key generation functions.
"""

import pytest
import sys
import os

# Add shared to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from database.search_key_generator import (
    parse_fullname,
    _parse_firstname_full,
    _parse_middlename,
    _parse_lastname_full,
    extract_dob_year,
    generate_search_keys,
    generate_search_keys_from_searchbug,
    generate_search_keys_for_record,
    generate_search_keys_batch,
)


# =============================================================================
# Тесты парсинга имён
# =============================================================================

class TestParseFullname:
    """Tests for parse_fullname function."""

    def test_simple_name(self):
        """Simple first + last name."""
        assert parse_fullname("John", None, "Wick") == ("john", None, "wick")

    def test_with_middlename_full(self):
        """First + middle (full) + last name."""
        assert parse_fullname("John", "Mike", "Wick") == ("john", "m", "wick")

    def test_with_middlename_initial(self):
        """First + middle (initial) + last name."""
        assert parse_fullname("John", "M", "Wick") == ("john", "m", "wick")

    def test_with_middlename_initial_dot(self):
        """First + middle (initial with dot) + last name."""
        assert parse_fullname("John", "M.", "Wick") == ("john", "m", "wick")

    def test_firstname_with_prefix_mr(self):
        """First name with Mr. prefix."""
        assert parse_fullname("Mr. John", None, "Wick") == ("john", None, "wick")

    def test_firstname_with_prefix_dr(self):
        """First name with Dr. prefix."""
        assert parse_fullname("Dr. Jane", None, "Doe") == ("jane", None, "doe")

    def test_lastname_del(self):
        """Last name with 'del' prefix."""
        assert parse_fullname("John", "M.", "del Toro") == ("john", "m", "toro")

    def test_lastname_de_la(self):
        """Last name with 'de la' prefix."""
        assert parse_fullname("Maria", None, "de la Cruz") == ("maria", None, "cruz")

    def test_lastname_van_der(self):
        """Last name with 'Van Der' prefix."""
        assert parse_fullname("John", None, "Van Der Berg") == ("john", None, "berg")

    def test_lastname_obrien(self):
        """Last name with O' prefix."""
        assert parse_fullname("John", "M", "O'Brien") == ("john", "m", "brien")

    def test_lastname_mcdonald(self):
        """Last name with Mc prefix."""
        assert parse_fullname("John", None, "McDonald") == ("john", None, "donald")

    def test_lastname_macarthur(self):
        """Last name with Mac prefix."""
        assert parse_fullname("John", None, "MacArthur") == ("john", None, "arthur")

    def test_lastname_with_initial_prefix(self):
        """Last name with single letter prefix (M. Smith)."""
        assert parse_fullname("John", "M", "M. Smith") == ("john", "m", "smith")

    def test_lastname_with_initial_a(self):
        """Last name with 'A.' prefix."""
        assert parse_fullname("John", None, "A. Johnson") == ("john", None, "johnson")

    def test_empty_firstname(self):
        """Empty first name returns None."""
        assert parse_fullname("", None, "Wick") == (None, None, None)

    def test_empty_lastname(self):
        """Empty last name returns None."""
        assert parse_fullname("John", None, "") == (None, None, None)

    def test_none_firstname(self):
        """None first name returns None."""
        assert parse_fullname(None, None, "Wick") == (None, None, None)


class TestParseFirstnameFull:
    """Tests for _parse_firstname_full function."""

    def test_simple_name(self):
        assert _parse_firstname_full("John") == "john"

    def test_with_mr_prefix(self):
        assert _parse_firstname_full("Mr. John") == "john"

    def test_with_mrs_prefix(self):
        assert _parse_firstname_full("Mrs. Jane") == "jane"

    def test_with_dr_prefix(self):
        assert _parse_firstname_full("Dr. James") == "james"

    def test_with_miss_prefix(self):
        assert _parse_firstname_full("Miss Mary") == "mary"

    def test_uppercase(self):
        assert _parse_firstname_full("JOHN") == "john"

    def test_mixed_case(self):
        assert _parse_firstname_full("JoHn") == "john"

    def test_empty_string(self):
        assert _parse_firstname_full("") is None

    def test_none(self):
        assert _parse_firstname_full(None) is None


class TestParseMiddlename:
    """Tests for _parse_middlename function."""

    def test_none(self):
        assert _parse_middlename(None) is None

    def test_empty_string(self):
        assert _parse_middlename("") is None

    def test_single_letter(self):
        assert _parse_middlename("M") == "m"

    def test_single_letter_with_dot(self):
        assert _parse_middlename("M.") == "m"

    def test_full_name(self):
        assert _parse_middlename("Mike") == "m"

    def test_full_name_uppercase(self):
        assert _parse_middlename("MICHAEL") == "m"

    def test_spaces(self):
        assert _parse_middlename("  M  ") == "m"


class TestParseLastnameFull:
    """Tests for _parse_lastname_full function."""

    def test_simple_name(self):
        assert _parse_lastname_full("Wick") == "wick"

    def test_del_prefix(self):
        assert _parse_lastname_full("del Toro") == "toro"

    def test_de_prefix(self):
        assert _parse_lastname_full("de Silva") == "silva"

    def test_de_la_prefix(self):
        assert _parse_lastname_full("de la Cruz") == "cruz"

    def test_van_prefix(self):
        assert _parse_lastname_full("van Gogh") == "gogh"

    def test_van_der_prefix(self):
        assert _parse_lastname_full("Van Der Berg") == "berg"

    def test_von_prefix(self):
        assert _parse_lastname_full("von Trapp") == "trapp"

    def test_obrien(self):
        assert _parse_lastname_full("O'Brien") == "brien"

    def test_oconnor(self):
        assert _parse_lastname_full("O'Connor") == "connor"

    def test_mcdonald(self):
        assert _parse_lastname_full("McDonald") == "donald"

    def test_macarthur(self):
        assert _parse_lastname_full("MacArthur") == "arthur"

    def test_initial_m_prefix(self):
        assert _parse_lastname_full("M. Smith") == "smith"

    def test_initial_a_prefix(self):
        assert _parse_lastname_full("A. Johnson") == "johnson"

    def test_initial_j_prefix(self):
        assert _parse_lastname_full("J. Williams") == "williams"

    def test_empty_string(self):
        assert _parse_lastname_full("") is None

    def test_none(self):
        assert _parse_lastname_full(None) is None


# =============================================================================
# Тесты парсинга DOB
# =============================================================================

class TestExtractDobYear:
    """Tests for extract_dob_year function."""

    def test_mm_dd_yyyy_slash(self):
        """MM/DD/YYYY format."""
        assert extract_dob_year("01/02/1990") == "1990"

    def test_mm_dd_yyyy_dash(self):
        """MM-DD-YYYY format."""
        assert extract_dob_year("01-02-1990") == "1990"

    def test_mmddyyyy(self):
        """MMDDYYYY format (no separators)."""
        assert extract_dob_year("01021990") == "1990"

    def test_yyyy_mm_dd_slash(self):
        """YYYY/MM/DD format."""
        assert extract_dob_year("1990/01/02") == "1990"

    def test_yyyy_mm_dd_dash(self):
        """YYYY-MM-DD format (ISO)."""
        assert extract_dob_year("1990-01-02") == "1990"

    def test_yyyymmdd(self):
        """YYYYMMDD format (no separators)."""
        assert extract_dob_year("19900102") == "1990"

    def test_year_only(self):
        """Year only."""
        assert extract_dob_year("1985") == "1985"

    def test_year_2000s(self):
        """Year in 2000s."""
        assert extract_dob_year("01/01/2005") == "2005"

    def test_empty_string(self):
        """Empty string."""
        assert extract_dob_year("") is None

    def test_none(self):
        """None value."""
        assert extract_dob_year(None) is None

    def test_invalid_date(self):
        """Invalid date with no 4-digit year."""
        assert extract_dob_year("01/02/90") is None

    def test_year_at_end(self):
        """Year at the end of string."""
        assert extract_dob_year("DOB: 1990") == "1990"


# =============================================================================
# Тесты генерации ключей
# =============================================================================

class TestGenerateSearchKeys:
    """Tests for generate_search_keys function."""

    def test_all_fields_present(self):
        """All fields provided."""
        keys = generate_search_keys(
            firstname="John",
            middlename="Mike",
            lastname="Wick",
            dob="01/02/1990",
            phone="5551234567",
            address="123 Main St",
            state="FL"
        )

        assert keys['search_key_1'] == "john:m:wick:1990:5551234567"
        assert keys['search_key_2'] == "john:m:wick:1990:123:main:fl"
        assert keys['search_key_3'] == "john:wick:1990:5551234567"
        assert keys['search_key_4'] == "john:wick:1990:123:main:fl"
        assert keys['search_key_5'] == "john:m:wick:5551234567"
        assert keys['search_key_6'] == "john:m:wick:123:main:fl"
        assert keys['search_key_7'] == "john:wick:123:main:fl"
        assert keys['search_key_8'] == "john:wick:5551234567"

    def test_no_middlename(self):
        """No middle name - keys requiring MN should be None."""
        keys = generate_search_keys(
            firstname="John",
            middlename=None,
            lastname="Wick",
            dob="01/02/1990",
            phone="5551234567",
            address="123 Main St",
            state="FL"
        )

        # Keys requiring MN should be None
        assert keys['search_key_1'] is None
        assert keys['search_key_2'] is None
        assert keys['search_key_5'] is None
        assert keys['search_key_6'] is None

        # Keys not requiring MN should be set
        assert keys['search_key_3'] == "john:wick:1990:5551234567"
        assert keys['search_key_4'] == "john:wick:1990:123:main:fl"
        assert keys['search_key_7'] == "john:wick:123:main:fl"
        assert keys['search_key_8'] == "john:wick:5551234567"

    def test_no_dob(self):
        """No DOB - keys requiring DOB should be None."""
        keys = generate_search_keys(
            firstname="John",
            middlename="Mike",
            lastname="Wick",
            dob=None,
            phone="5551234567",
            address="123 Main St",
            state="FL"
        )

        # Keys requiring DOB should be None
        assert keys['search_key_1'] is None
        assert keys['search_key_2'] is None
        assert keys['search_key_3'] is None
        assert keys['search_key_4'] is None

        # Keys not requiring DOB should be set
        assert keys['search_key_5'] == "john:m:wick:5551234567"
        assert keys['search_key_6'] == "john:m:wick:123:main:fl"
        assert keys['search_key_7'] == "john:wick:123:main:fl"
        assert keys['search_key_8'] == "john:wick:5551234567"

    def test_no_phone(self):
        """No phone - keys requiring phone should be None."""
        keys = generate_search_keys(
            firstname="John",
            middlename="Mike",
            lastname="Wick",
            dob="01/02/1990",
            phone=None,
            address="123 Main St",
            state="FL"
        )

        # Keys requiring phone should be None
        assert keys['search_key_1'] is None
        assert keys['search_key_3'] is None
        assert keys['search_key_5'] is None
        assert keys['search_key_8'] is None

        # Keys not requiring phone should be set
        assert keys['search_key_2'] == "john:m:wick:1990:123:main:fl"
        assert keys['search_key_4'] == "john:wick:1990:123:main:fl"
        assert keys['search_key_6'] == "john:m:wick:123:main:fl"
        assert keys['search_key_7'] == "john:wick:123:main:fl"

    def test_no_address(self):
        """No address - keys requiring address should be None."""
        keys = generate_search_keys(
            firstname="John",
            middlename="Mike",
            lastname="Wick",
            dob="01/02/1990",
            phone="5551234567",
            address=None,
            state="FL"
        )

        # Keys requiring address should be None
        assert keys['search_key_2'] is None
        assert keys['search_key_4'] is None
        assert keys['search_key_6'] is None
        assert keys['search_key_7'] is None

        # Keys not requiring address should be set
        assert keys['search_key_1'] == "john:m:wick:1990:5551234567"
        assert keys['search_key_3'] == "john:wick:1990:5551234567"
        assert keys['search_key_5'] == "john:m:wick:5551234567"
        assert keys['search_key_8'] == "john:wick:5551234567"

    def test_phone_with_formatting(self):
        """Phone with formatting should be normalized."""
        keys = generate_search_keys(
            firstname="John",
            middlename=None,
            lastname="Wick",
            dob=None,
            phone="(555) 123-4567",
            address=None,
            state=None
        )

        assert keys['search_key_8'] == "john:wick:5551234567"

    def test_phone_with_country_code(self):
        """Phone with country code should be normalized."""
        keys = generate_search_keys(
            firstname="John",
            middlename=None,
            lastname="Wick",
            dob=None,
            phone="1-555-123-4567",
            address=None,
            state=None
        )

        assert keys['search_key_8'] == "john:wick:5551234567"

    def test_address_with_direction(self):
        """Address with direction (E Main St)."""
        keys = generate_search_keys(
            firstname="John",
            middlename=None,
            lastname="Wick",
            dob=None,
            phone=None,
            address="123 E Main St",
            state="FL"
        )

        assert keys['search_key_7'] == "john:wick:123:main:fl"

    def test_po_box_address(self):
        """PO BOX address."""
        keys = generate_search_keys(
            firstname="John",
            middlename=None,
            lastname="Wick",
            dob=None,
            phone=None,
            address="PO BOX 123",
            state="FL"
        )

        assert keys['search_key_7'] == "john:wick:pb:123:fl"

    def test_empty_firstname(self):
        """Empty first name should return all None."""
        keys = generate_search_keys(
            firstname="",
            middlename="Mike",
            lastname="Wick",
            dob="01/02/1990",
            phone="5551234567",
            address="123 Main St",
            state="FL"
        )

        for i in range(1, 9):
            assert keys[f'search_key_{i}'] is None


class TestGenerateSearchKeysFromSearchbug:
    """Tests for generate_search_keys_from_searchbug function."""

    def test_basic_searchbug_data(self):
        """Basic SearchBug data with phones and addresses."""
        data = {
            "firstname": "John",
            "middlename": "Mike",
            "lastname": "Wick",
            "dob": "01/02/1990",
            "phones": ["5551234567", "5559876543"],
            "addresses": [
                {"address": "123 Main St", "state": "FL"},
                {"address": "456 Oak Ave", "state": "CA"}
            ]
        }

        result = generate_search_keys_from_searchbug(data)

        # Should have 2 phone keys (2 phones)
        assert len(result['search_keys_1']) == 2
        assert "john:m:wick:1990:5551234567" in result['search_keys_1']
        assert "john:m:wick:1990:5559876543" in result['search_keys_1']

        # Should have 2 address keys (2 addresses)
        assert len(result['search_keys_2']) == 2
        assert "john:m:wick:1990:123:main:fl" in result['search_keys_2']
        assert "john:m:wick:1990:456:oak:ca" in result['search_keys_2']

    def test_no_middlename_in_searchbug(self):
        """SearchBug data without middle name."""
        data = {
            "firstname": "John",
            "lastname": "Wick",
            "phones": ["5551234567"]
        }

        result = generate_search_keys_from_searchbug(data)

        # Keys requiring MN should be empty
        assert len(result['search_keys_1']) == 0
        assert len(result['search_keys_5']) == 0

        # Keys not requiring MN should be populated
        assert len(result['search_keys_8']) == 1
        assert "john:wick:5551234567" in result['search_keys_8']

    def test_multiple_dobs(self):
        """SearchBug data with multiple DOBs (list)."""
        data = {
            "firstname": "John",
            "middlename": "M",
            "lastname": "Wick",
            "dob": ["01/02/1990", "01/02/1991"],
            "phones": ["5551234567"]
        }

        result = generate_search_keys_from_searchbug(data)

        # Should have 2 keys for key_1 (2 DOBs x 1 phone)
        assert len(result['search_keys_1']) == 2
        assert "john:m:wick:1990:5551234567" in result['search_keys_1']
        assert "john:m:wick:1991:5551234567" in result['search_keys_1']

    def test_empty_firstname(self):
        """SearchBug data with empty firstname returns empty lists."""
        data = {
            "firstname": "",
            "lastname": "Wick",
            "phones": ["5551234567"]
        }

        result = generate_search_keys_from_searchbug(data)

        for i in range(1, 9):
            assert len(result[f'search_keys_{i}']) == 0

    def test_empty_phones_and_addresses(self):
        """SearchBug data without phones and addresses."""
        data = {
            "firstname": "John",
            "lastname": "Wick",
            "dob": "01/02/1990"
        }

        result = generate_search_keys_from_searchbug(data)

        # All lists should be empty since no phones or addresses
        for i in range(1, 9):
            assert len(result[f'search_keys_{i}']) == 0


class TestGenerateSearchKeysForRecord:
    """Tests for generate_search_keys_for_record function."""

    def test_basic_record(self):
        """Basic database record."""
        record = {
            'id': 1,
            'firstname': 'John',
            'middlename': 'Mike',
            'lastname': 'Wick',
            'dob': '01/02/1990',
            'phone': '5551234567',
            'address': '123 Main St',
            'state': 'FL'
        }

        keys = generate_search_keys_for_record(record)

        assert keys['search_key_1'] == 'john:m:wick:1990:5551234567'
        assert keys['search_key_8'] == 'john:wick:5551234567'


class TestGenerateSearchKeysBatch:
    """Tests for generate_search_keys_batch function."""

    def test_batch_processing(self):
        """Process multiple records in batch."""
        records = [
            {
                'id': 1,
                'firstname': 'John',
                'middlename': 'Mike',
                'lastname': 'Wick',
                'dob': '01/02/1990',
                'phone': '5551234567',
                'address': '123 Main St',
                'state': 'FL'
            },
            {
                'id': 2,
                'firstname': 'Jane',
                'lastname': 'Doe',
                'phone': '5559876543',
            }
        ]

        results = generate_search_keys_batch(records)

        assert len(results) == 2

        # First record
        id1, keys1 = results[0]
        assert id1 == 1
        assert keys1['search_key_1'] == 'john:m:wick:1990:5551234567'

        # Second record (no middlename, no dob)
        id2, keys2 = results[1]
        assert id2 == 2
        assert keys2['search_key_1'] is None  # No middlename
        assert keys2['search_key_8'] == 'jane:doe:5559876543'


# =============================================================================
# Интеграционные тесты
# =============================================================================

class TestIntegration:
    """Integration tests for search key generation."""

    def test_complex_name_with_prefixes(self):
        """Complex name with multiple prefixes and special characters."""
        keys = generate_search_keys(
            firstname="Mr. John",
            middlename="Michael",
            lastname="Van Der O'Brien",
            dob="1985-03-15",
            phone="(800) 555-1212",
            address="456 NW Oak Boulevard",
            state="ca"
        )

        # Should handle all the special cases
        assert keys['search_key_8'] is not None
        assert ":8005551212" in keys['search_key_8']  # Phone normalized
        assert "john:" in keys['search_key_8']  # Firstname without prefix

    def test_special_address_formats(self):
        """Special address formats like RR BOX, HC BOX."""
        # RR BOX
        keys_rr = generate_search_keys(
            firstname="John",
            middlename=None,
            lastname="Wick",
            dob=None,
            phone=None,
            address="RR 2 BOX 58",
            state="TX"
        )
        assert keys_rr['search_key_7'] == "john:wick:rr2:58:tx"

        # HC BOX
        keys_hc = generate_search_keys(
            firstname="John",
            middlename=None,
            lastname="Wick",
            dob=None,
            phone=None,
            address="HC 1 BOX 45",
            state="TX"
        )
        assert keys_hc['search_key_7'] == "john:wick:hc1:45:tx"

    def test_numeric_street_names(self):
        """Numeric street names (1st, 2nd, 42nd)."""
        keys = generate_search_keys(
            firstname="John",
            middlename=None,
            lastname="Wick",
            dob=None,
            phone=None,
            address="100 42nd Street",
            state="NY"
        )

        assert keys['search_key_7'] == "john:wick:100:42nd:ny"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
