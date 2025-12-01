#!/usr/bin/env python3
"""
Test script to verify the new enrichment search order:
1. First attempt: Name + Address
2. Second attempt: Name + Phone
"""
import asyncio
import sys
from api.common.whitepages_client import WhitepagesClient

async def test_search_order():
    """Test that the search order is Name+Address first, then Name+Phone"""

    # Create test data that has both phone and address
    test_record = {
        'firstname': 'John',
        'lastname': 'Doe',
        'phone': '(212) 555-1234',
        'street': '123 Main St',
        'city': 'New York',
        'state': 'NY',
        'zipcode': '10001'
    }

    # Initialize client (mock API key for testing)
    client = WhitepagesClient(
        api_key="test_api_key",
        base_url="https://api.whitepages.com"
    )

    # Mock the search methods to track which was called first
    call_order = []

    original_search_by_name_address = client.search_person_by_name_address
    original_search_by_phone = client.search_person_by_phone

    async def mock_search_by_name_address(*args, **kwargs):
        call_order.append('Name+Address')
        print("Called: Name + Address search")
        # Return empty to simulate no results and trigger second attempt
        return []

    async def mock_search_by_phone(*args, **kwargs):
        call_order.append('Name+Phone')
        print("Called: Name + Phone search")
        # Return a mock result
        return [{
            'id': 'P1234567890',
            'name': 'John Doe',
            'phones': [{'number': '2125551234', 'score': 95}]
        }]

    # Replace methods with mocks
    client.search_person_by_name_address = mock_search_by_name_address
    client.search_person_by_phone = mock_search_by_phone

    # Manually open the client
    await client.open()

    try:
        # Call the targeted search method
        result = await client._search_with_targeted_criteria(
            phone=test_record['phone'],
            firstname=test_record['firstname'],
            lastname=test_record['lastname'],
            street=test_record['street'],
            city=test_record['city'],
            state_code=test_record['state'],
            zipcode=test_record['zipcode'],
            return_all=True
        )

        print(f"\nSearch order: {' -> '.join(call_order)}")

        # Verify the order
        if len(call_order) >= 1 and call_order[0] == 'Name+Address':
            print("✅ SUCCESS: Name+Address is called FIRST (new order)")
        else:
            print("❌ FAILURE: Name+Address is NOT called first")

        if len(call_order) >= 2 and call_order[1] == 'Name+Phone':
            print("✅ SUCCESS: Name+Phone is called SECOND (new order)")

        print(f"\nResult found: {bool(result)}")

    finally:
        await client.close()

if __name__ == "__main__":
    print("Testing enrichment search order...")
    print("Expected: Name+Address first, then Name+Phone\n")
    asyncio.run(test_search_order())