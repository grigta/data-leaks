"""
Unit tests for bloom_key_generator module.

Run with:
    pytest tests/test_bloom_key_generator.py -v
"""

import pytest
import sys
import os

# Add shared directory to path
test_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(test_dir)
shared_dir = os.path.join(project_root, 'shared')
sys.path.insert(0, shared_dir)

from database.bloom_key_generator import (
    normalize_firstname_for_bloom,
    normalize_lastname_for_bloom,
    normalize_phone_for_bloom,
    parse_address_for_bloom,
    generate_bloom_key_phone,
    generate_bloom_key_address,
    generate_all_bloom_keys_from_record,
    generate_all_bloom_keys_from_searchbug,
)


class TestNormalizeFirstname:
    """Tests for normalize_firstname_for_bloom()"""

    def test_simple_name(self):
        assert normalize_firstname_for_bloom("John") == "j"
        assert normalize_firstname_for_bloom("jane") == "j"
        assert normalize_firstname_for_bloom("MARY") == "m"

    def test_name_with_prefix_mr(self):
        assert normalize_firstname_for_bloom("Mr. John") == "j"
        assert normalize_firstname_for_bloom("Mr John") == "j"

    def test_name_with_prefix_mrs(self):
        assert normalize_firstname_for_bloom("Mrs. Jane") == "j"
        assert normalize_firstname_for_bloom("Mrs Jane") == "j"

    def test_name_with_prefix_ms(self):
        assert normalize_firstname_for_bloom("Ms. Mary") == "m"
        assert normalize_firstname_for_bloom("Ms Mary") == "m"

    def test_name_with_prefix_miss(self):
        assert normalize_firstname_for_bloom("Miss Mary") == "m"

    def test_name_with_prefix_dr(self):
        assert normalize_firstname_for_bloom("Dr. Jane") == "j"
        assert normalize_firstname_for_bloom("Dr Jane") == "j"

    def test_name_with_initial(self):
        assert normalize_firstname_for_bloom("John M.") == "j"
        assert normalize_firstname_for_bloom("John A. R.") == "j"

    def test_empty_name(self):
        assert normalize_firstname_for_bloom("") is None
        assert normalize_firstname_for_bloom(None) is None

    def test_only_prefix(self):
        # Edge case: only prefix, no actual name
        assert normalize_firstname_for_bloom("Mr.") is None
        assert normalize_firstname_for_bloom("Dr") is None


class TestNormalizeLastname:
    """Tests for normalize_lastname_for_bloom()"""

    def test_simple_lastname(self):
        assert normalize_lastname_for_bloom("Wick") == "w"
        assert normalize_lastname_for_bloom("smith") == "s"
        assert normalize_lastname_for_bloom("JONES") == "j"

    def test_lastname_with_del(self):
        assert normalize_lastname_for_bloom("del Toro") == "t"
        assert normalize_lastname_for_bloom("Del Toro") == "t"

    def test_lastname_with_de(self):
        assert normalize_lastname_for_bloom("de Silva") == "s"
        assert normalize_lastname_for_bloom("De Silva") == "s"

    def test_lastname_with_de_la(self):
        assert normalize_lastname_for_bloom("de la Cruz") == "c"
        assert normalize_lastname_for_bloom("De La Cruz") == "c"

    def test_lastname_with_van(self):
        assert normalize_lastname_for_bloom("van Berg") == "b"
        assert normalize_lastname_for_bloom("Van Berg") == "b"

    def test_lastname_with_van_der(self):
        assert normalize_lastname_for_bloom("Van Der Berg") == "b"
        assert normalize_lastname_for_bloom("van der Berg") == "b"

    def test_lastname_with_von(self):
        assert normalize_lastname_for_bloom("von Trapp") == "t"
        assert normalize_lastname_for_bloom("Von Trapp") == "t"

    def test_lastname_with_o_apostrophe(self):
        assert normalize_lastname_for_bloom("O'Brien") == "b"
        assert normalize_lastname_for_bloom("O'Connor") == "c"

    def test_lastname_with_mc(self):
        assert normalize_lastname_for_bloom("McDonald") == "d"
        assert normalize_lastname_for_bloom("McArthur") == "a"

    def test_lastname_with_mac(self):
        assert normalize_lastname_for_bloom("MacArthur") == "a"
        assert normalize_lastname_for_bloom("MacDonald") == "d"

    def test_empty_lastname(self):
        assert normalize_lastname_for_bloom("") is None
        assert normalize_lastname_for_bloom(None) is None


class TestNormalizePhone:
    """Tests for normalize_phone_for_bloom()"""

    def test_formatted_phone(self):
        assert normalize_phone_for_bloom("(555) 123-4567") == "5551234567"
        assert normalize_phone_for_bloom("555-123-4567") == "5551234567"

    def test_phone_with_country_code(self):
        assert normalize_phone_for_bloom("1-555-123-4567") == "5551234567"
        assert normalize_phone_for_bloom("+1 555 123 4567") == "5551234567"

    def test_phone_with_dots(self):
        assert normalize_phone_for_bloom("555.123.4567") == "5551234567"

    def test_plain_phone(self):
        assert normalize_phone_for_bloom("5551234567") == "5551234567"

    def test_invalid_phone_too_short(self):
        assert normalize_phone_for_bloom("555123456") is None
        assert normalize_phone_for_bloom("12345") is None

    def test_invalid_phone_too_long(self):
        assert normalize_phone_for_bloom("155512345678") is None

    def test_empty_phone(self):
        assert normalize_phone_for_bloom("") is None
        assert normalize_phone_for_bloom(None) is None


class TestParseAddress:
    """Tests for parse_address_for_bloom()"""

    def test_simple_address(self):
        assert parse_address_for_bloom("123 Main St") == ("123", "main")
        assert parse_address_for_bloom("456 Oak Ave") == ("456", "oak")

    def test_address_with_direction(self):
        assert parse_address_for_bloom("123 E Main St") == ("123", "main")
        assert parse_address_for_bloom("456 NW Oak Ave") == ("456", "oak")
        assert parse_address_for_bloom("789 S Broadway") == ("789", "broadway")

    def test_address_with_service_words(self):
        assert parse_address_for_bloom("123 Old Main St") == ("123", "main")
        assert parse_address_for_bloom("456 West Oak Ave") == ("456", "oak")
        assert parse_address_for_bloom("789 New Broadway") == ("789", "broadway")

    def test_address_with_via(self):
        assert parse_address_for_bloom("789 Via Roma") == ("789", "roma")

    def test_address_number_with_letter(self):
        assert parse_address_for_bloom("123A Main St") == ("123", "main")
        assert parse_address_for_bloom("456B Oak Ave") == ("456", "oak")

    def test_address_number_with_suffix(self):
        assert parse_address_for_bloom("123th Main St") == ("123", "main")

    def test_numeric_street(self):
        assert parse_address_for_bloom("100 1st St") == ("100", "1st")
        assert parse_address_for_bloom("200 2nd Ave") == ("200", "2nd")
        assert parse_address_for_bloom("300 3rd Blvd") == ("300", "3rd")
        assert parse_address_for_bloom("400 42nd Street") == ("400", "42nd")

    def test_po_box(self):
        assert parse_address_for_bloom("PO BOX 123") == ("pb", "123")
        assert parse_address_for_bloom("P.O. BOX 456") == ("pb", "456")
        assert parse_address_for_bloom("POST OFFICE BOX 789") == ("pb", "789")

    def test_rural_route_box(self):
        assert parse_address_for_bloom("RR 2 BOX 58") == ("rr2", "58")
        assert parse_address_for_bloom("RR2 BOX 100") == ("rr2", "100")

    def test_highway_contract_box(self):
        assert parse_address_for_bloom("HC 1 BOX 45") == ("hc1", "45")
        assert parse_address_for_bloom("HC1 BOX 99") == ("hc1", "99")

    def test_simple_box(self):
        assert parse_address_for_bloom("BOX 99") == ("bx", "99")

    def test_empty_address(self):
        assert parse_address_for_bloom("") == (None, None)
        assert parse_address_for_bloom(None) == (None, None)


class TestGenerateBloomKeyPhone:
    """Tests for generate_bloom_key_phone()"""

    def test_simple_case(self):
        assert generate_bloom_key_phone("John", "Wick", "5551234567") == "j:w:5551234567"

    def test_with_prefixes(self):
        assert generate_bloom_key_phone("Mr. John", "O'Brien", "1-555-123-4567") == "j:b:5551234567"

    def test_with_formatted_phone(self):
        assert generate_bloom_key_phone("Jane", "Doe", "(555) 123-4567") == "j:d:5551234567"

    def test_invalid_phone(self):
        assert generate_bloom_key_phone("John", "Wick", "12345") is None

    def test_missing_name(self):
        assert generate_bloom_key_phone("", "Wick", "5551234567") is None
        assert generate_bloom_key_phone("John", "", "5551234567") is None


class TestGenerateBloomKeyAddress:
    """Tests for generate_bloom_key_address()"""

    def test_simple_case(self):
        assert generate_bloom_key_address("John", "Wick", "123 Main St", "FL") == "j:w:123:main:fl"

    def test_with_prefixes(self):
        assert generate_bloom_key_address("Mr. John", "del Toro", "456 E Oak Ave", "CA") == "j:t:456:oak:ca"

    def test_with_direction(self):
        assert generate_bloom_key_address("Jane", "Doe", "789 NW Broadway", "NY") == "j:d:789:broadway:ny"

    def test_invalid_state(self):
        assert generate_bloom_key_address("John", "Wick", "123 Main St", "") is None
        assert generate_bloom_key_address("John", "Wick", "123 Main St", "ABC") is None

    def test_missing_name(self):
        assert generate_bloom_key_address("", "Wick", "123 Main St", "FL") is None
        assert generate_bloom_key_address("John", "", "123 Main St", "FL") is None


class TestGenerateAllBloomKeysFromRecord:
    """Tests for generate_all_bloom_keys_from_record()"""

    def test_full_record(self):
        result = generate_all_bloom_keys_from_record(
            firstname="John",
            lastname="Wick",
            phone="5551234567",
            address="123 Main St",
            state="FL"
        )
        assert result['bloom_key_phone'] == "j:w:5551234567"
        assert result['bloom_key_address'] == "j:w:123:main:fl"

    def test_phone_only(self):
        result = generate_all_bloom_keys_from_record(
            firstname="John",
            lastname="Wick",
            phone="5551234567"
        )
        assert result['bloom_key_phone'] == "j:w:5551234567"
        assert result['bloom_key_address'] is None

    def test_address_only(self):
        result = generate_all_bloom_keys_from_record(
            firstname="John",
            lastname="Wick",
            address="123 Main St",
            state="FL"
        )
        assert result['bloom_key_phone'] is None
        assert result['bloom_key_address'] == "j:w:123:main:fl"

    def test_minimal_record(self):
        result = generate_all_bloom_keys_from_record(
            firstname="John",
            lastname="Wick"
        )
        assert result['bloom_key_phone'] is None
        assert result['bloom_key_address'] is None


class TestGenerateAllBloomKeysFromSearchbug:
    """Tests for generate_all_bloom_keys_from_searchbug()"""

    def test_full_searchbug_data(self):
        data = {
            "firstname": "John",
            "lastname": "Wick",
            "phones": ["5551234567", "5559876543"],
            "addresses": [
                {"address": "123 Main St", "state": "FL"},
                {"address": "456 Oak Ave", "state": "CA"}
            ]
        }
        result = generate_all_bloom_keys_from_searchbug(data)

        assert len(result['bloom_keys_phone']) == 2
        assert "j:w:5551234567" in result['bloom_keys_phone']
        assert "j:w:5559876543" in result['bloom_keys_phone']

        assert len(result['bloom_keys_address']) == 2
        assert "j:w:123:main:fl" in result['bloom_keys_address']
        assert "j:w:456:oak:ca" in result['bloom_keys_address']

    def test_phones_only(self):
        data = {
            "firstname": "John",
            "lastname": "Wick",
            "phones": ["5551234567"]
        }
        result = generate_all_bloom_keys_from_searchbug(data)

        assert result['bloom_keys_phone'] == ["j:w:5551234567"]
        assert result['bloom_keys_address'] == []

    def test_addresses_only(self):
        data = {
            "firstname": "John",
            "lastname": "Wick",
            "addresses": [{"address": "123 Main St", "state": "FL"}]
        }
        result = generate_all_bloom_keys_from_searchbug(data)

        assert result['bloom_keys_phone'] == []
        assert result['bloom_keys_address'] == ["j:w:123:main:fl"]

    def test_empty_data(self):
        result = generate_all_bloom_keys_from_searchbug({})
        assert result['bloom_keys_phone'] == []
        assert result['bloom_keys_address'] == []

    def test_missing_name(self):
        data = {
            "phones": ["5551234567"]
        }
        result = generate_all_bloom_keys_from_searchbug(data)
        assert result['bloom_keys_phone'] == []
        assert result['bloom_keys_address'] == []

    def test_duplicate_phones(self):
        data = {
            "firstname": "John",
            "lastname": "Wick",
            "phones": ["5551234567", "5551234567", "(555) 123-4567"]
        }
        result = generate_all_bloom_keys_from_searchbug(data)
        # Should deduplicate
        assert len(result['bloom_keys_phone']) == 1
        assert result['bloom_keys_phone'] == ["j:w:5551234567"]


class TestEdgeCases:
    """Edge case tests"""

    def test_unicode_names(self):
        # Should handle unicode gracefully
        assert normalize_firstname_for_bloom("José") == "j"
        assert normalize_lastname_for_bloom("García") == "g"

    def test_extra_whitespace(self):
        assert normalize_firstname_for_bloom("  John  ") == "j"
        assert normalize_lastname_for_bloom("  Wick  ") == "w"

    def test_mixed_case(self):
        assert generate_bloom_key_phone("JOHN", "WICK", "5551234567") == "j:w:5551234567"
        assert generate_bloom_key_address("john", "wick", "123 MAIN ST", "fl") == "j:w:123:main:fl"

    def test_address_with_apt(self):
        # Apartment numbers should be ignored (street name is extracted)
        result = parse_address_for_bloom("123 Main St Apt 4B")
        assert result[0] == "123"
        assert result[1] == "main"

    def test_address_with_unit(self):
        result = parse_address_for_bloom("123 Main St Unit 5")
        assert result[0] == "123"
        assert result[1] == "main"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
