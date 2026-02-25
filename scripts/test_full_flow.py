#!/usr/bin/env python3
"""
Full flow test for two-level search
"""
import logging
logging.basicConfig(level=logging.WARNING)

import sys
sys.path.insert(0, '/app')

from database.clickhouse_search_engine import ClickHouseSearchEngine
from database.search_key_generator import (
    generate_query_keys_from_searchbug,
    generate_candidate_keys,
    extract_searchbug_mn_and_dob,
    parse_fullname,
    extract_dob_year
)
from database.bloom_key_generator import (
    generate_bloom_key_phone,
    generate_bloom_key_address
)


def show_full_flow(name, searchbug_data):
    print()
    print("=" * 80)
    print(f"FULL FLOW: {name}")
    print("=" * 80)

    firstname = searchbug_data.get('firstname', '')
    middlename = searchbug_data.get('middlename')
    lastname = searchbug_data.get('lastname', '')
    dob = searchbug_data.get('dob', '')
    phones = searchbug_data.get('phones', [])
    addresses = searchbug_data.get('addresses', [])

    print()
    print("[INPUT] SearchBug Data:")
    print(f"  firstname:  {firstname}")
    print(f"  middlename: {middlename}")
    print(f"  lastname:   {lastname}")
    print(f"  dob:        {dob}")
    print(f"  phones:     {phones}")
    print(f"  addresses:  {addresses}")

    # Парсинг данных
    print()
    print("[PARSE] Normalized Values:")
    fn, mn, ln = parse_fullname(firstname, middlename, lastname)
    dob_year = extract_dob_year(dob) if dob else None
    print(f"  FN (full):    {fn}")
    print(f"  MN (initial): {mn}")
    print(f"  LN (full):    {ln}")
    print(f"  DOB_YEAR:     {dob_year}")

    # Level 1: Bloom Keys
    print()
    print("[LEVEL 1] Bloom Key Generation:")
    bloom_phone_keys = []
    bloom_addr_keys = []

    for phone in phones:
        key = generate_bloom_key_phone(firstname, lastname, phone)
        if key:
            bloom_phone_keys.append(key)
            print(f"  bloom_key_phone:   {key}")

    for addr in addresses:
        if isinstance(addr, dict):
            key = generate_bloom_key_address(firstname, lastname, addr.get('address', ''), addr.get('state', ''))
            if key:
                bloom_addr_keys.append(key)
                print(f"  bloom_key_address: {key}")

    if not bloom_phone_keys and not bloom_addr_keys:
        print("  (no bloom keys generated)")

    # Level 2: Query Keys
    print()
    print("[LEVEL 2] Query Keys (8 methods from SearchBug):")
    query_keys = generate_query_keys_from_searchbug(searchbug_data)
    for key in sorted(query_keys):
        # Определяем тип ключа
        parts = key.split(':')
        if len(parts) == 3:
            key_type = "Key8 (FN:LN:PHONE)"
        elif len(parts) == 4:
            if parts[2].isdigit() and len(parts[2]) == 4:
                key_type = "Key3 (FN:LN:DOB:PHONE)"
            else:
                key_type = "Key5 (FN:MN:LN:PHONE)"
        elif len(parts) == 5:
            if parts[2].isdigit() and len(parts[2]) == 4:
                key_type = "Key1 (FN:MN:LN:DOB:PHONE)"
            else:
                key_type = "Key7 (FN:LN:ADDR:STREET:STATE)"
        elif len(parts) == 6:
            if parts[2].isdigit() and len(parts[2]) == 4:
                key_type = "Key4 (FN:LN:DOB:ADDR:STREET:STATE)"
            else:
                key_type = "Key6 (FN:MN:LN:ADDR:STREET:STATE)"
        elif len(parts) == 7:
            key_type = "Key2 (FN:MN:LN:DOB:ADDR:STREET:STATE)"
        else:
            key_type = "Unknown"

        print(f"  {key_type}: {key}")

    if not query_keys:
        print("  (no query keys generated)")

    # Execute Level 1 search
    print()
    print("[LEVEL 1 SEARCH] ClickHouse Bloom Lookup...")

    engine = ClickHouseSearchEngine()

    candidates = []
    if bloom_phone_keys:
        candidates = engine._search_by_bloom_key_phone(firstname, lastname, phones, limit=100)
        print(f"  Bloom phone query: SELECT ... WHERE bloom_key_phone IN {bloom_phone_keys}")
        print(f"  Result: {len(candidates)} candidate(s)")

    if not candidates and bloom_addr_keys:
        candidates = engine._search_by_bloom_key_address(firstname, lastname, addresses, limit=100)
        print(f"  Bloom address query: SELECT ... WHERE bloom_key_address IN {bloom_addr_keys}")
        print(f"  Result: {len(candidates)} candidate(s)")

    if not candidates:
        print("  No candidates found at Level 1")
        print()
        print("[RESULT] No matches - Level 1 (Bloom) filtered everything out")
        return []

    # Show candidates
    print()
    print("[CANDIDATES] From ClickHouse:")
    for i, c in enumerate(candidates[:5], 1):
        print(f"  #{i}:")
        print(f"      SSN:     {c.get('ssn')}")
        print(f"      Name:    {c.get('firstname')} {c.get('lastname')}")
        print(f"      Phone:   {c.get('phone')}")
        print(f"      Address: {c.get('address')}")
        print(f"      State:   {c.get('state')}")
        print(f"      DOB:     {c.get('dob')}")

    # Level 2: Generate candidate keys and match
    print()
    print("[LEVEL 2 MATCHING] Runtime Key Comparison:")

    sb_mn, sb_dob_year = extract_searchbug_mn_and_dob(searchbug_data)
    print(f"  Using SearchBug: MN={sb_mn}, DOB_YEAR={sb_dob_year}")
    print()

    filtered = []
    for c in candidates:
        candidate_keys = generate_candidate_keys(c, sb_mn, sb_dob_year)
        matched = query_keys & candidate_keys

        print(f"  Candidate: {c.get('firstname')} {c.get('lastname')} (SSN: {c.get('ssn')})")
        print(f"  Generated candidate keys (using MN={sb_mn}, DOB={sb_dob_year} from SearchBug):")
        for ck in sorted(candidate_keys):
            if ck in query_keys:
                print(f"    ✓ {ck}  <-- MATCHES query key!")
            else:
                print(f"    - {ck}")

        if matched:
            print(f"  → PASSED Level 2: {len(matched)} key(s) matched")
            c['matched_keys'] = list(matched)
            c['match_level'] = 2
            filtered.append(c)
        else:
            print(f"  → FILTERED OUT: No matching keys")
        print()

    print("[FINAL RESULT]")
    print(f"  Matches after Level 2: {len(filtered)}")

    if filtered:
        for r in filtered:
            print(f"  → SSN: {r.get('ssn')}")
            print(f"    Name: {r.get('firstname')} {r.get('lastname')}")
            print(f"    Matched keys: {r.get('matched_keys')}")

    return filtered


if __name__ == '__main__':
    # ============================================================================
    # TEST CASE 1: Thomas Trapp
    # ============================================================================
    show_full_flow('Thomas Trapp', {
        'firstname': 'Thomas',
        'middlename': None,
        'lastname': 'Trapp',
        'dob': '07/25/1941',
        'phones': ['9167831819'],
        'addresses': [{'address': '3080 Demartini Rd', 'state': 'CA'}]
    })

    # ============================================================================
    # TEST CASE 2: Andrew Austing
    # ============================================================================
    show_full_flow('Andrew Austing', {
        'firstname': 'Andrew',
        'middlename': None,
        'lastname': 'Austing',
        'dob': '05/09/1974',
        'phones': ['4104206898'],
        'addresses': []
    })

    # ============================================================================
    # TEST CASE 3: John Smith with middlename (example)
    # ============================================================================
    show_full_flow('John Michael Smith (with middlename)', {
        'firstname': 'John',
        'middlename': 'Michael',
        'lastname': 'Smith',
        'dob': '01/15/1985',
        'phones': ['5551234567'],
        'addresses': [{'address': '123 Main St', 'state': 'CA'}]
    })
