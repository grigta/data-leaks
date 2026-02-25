"""
Search Engine Factory Module

This module provides a factory pattern for creating search engine instances.
Only ClickHouse is supported as the search backend.

Usage:
    from database.search_engine_factory import get_search_engine
    engine = get_search_engine()
    results = engine.search_by_ssn("123-45-6789")
"""

import json
import logging
from typing import Any, Dict, List, Optional

# Module logger
logger = logging.getLogger(__name__)


def get_search_engine():
    """
    Get a ClickHouse search engine instance.

    Returns:
        ClickHouseSearchEngine: Search engine instance

    Raises:
        ImportError: If ClickHouse client is not available
    """
    from database.clickhouse_search_engine import ClickHouseSearchEngine
    logger.info("Creating ClickHouse search engine")
    return ClickHouseSearchEngine()


def get_engine_info() -> Dict[str, Any]:
    """
    Get information about the current search engine configuration.

    Returns:
        dict: Engine configuration info
    """
    info = {
        'type': 'clickhouse',
        'clickhouse_available': False,
    }

    # Check ClickHouse availability
    try:
        from database.clickhouse_client import CLICKHOUSE_AVAILABLE, health_check
        info['clickhouse_available'] = CLICKHOUSE_AVAILABLE
        if CLICKHOUSE_AVAILABLE:
            is_healthy, message = health_check()
            info['clickhouse_healthy'] = is_healthy
            info['clickhouse_status'] = message
    except Exception as e:
        info['clickhouse_error'] = str(e)

    return info


# Convenience functions that use the factory

def search_by_ssn(ssn: str, limit: Optional[int] = None) -> str:
    """
    Convenience function to search by SSN using ClickHouse.

    Args:
        ssn: Social Security Number
        limit: Optional limit

    Returns:
        str: JSON string with results
    """
    engine = get_search_engine()
    return engine.search_by_ssn(ssn, limit=limit)


def search_by_name_zip(
    firstname: str,
    lastname: str,
    zip_code: str,
    limit: Optional[int] = None
) -> str:
    """
    Convenience function to search by name and ZIP using ClickHouse.

    Args:
        firstname: First name
        lastname: Last name
        zip_code: ZIP code
        limit: Optional limit

    Returns:
        str: JSON string with results
    """
    engine = get_search_engine()
    return engine.search_by_name_zip(firstname, lastname, zip_code, limit=limit)


def search_by_name_address(
    firstname: str,
    lastname: str,
    address: str,
    limit: Optional[int] = None
) -> str:
    """
    Convenience function to search by name and address using ClickHouse.

    Args:
        firstname: First name
        lastname: Last name
        address: Address
        limit: Optional limit

    Returns:
        str: JSON string with results
    """
    engine = get_search_engine()
    return engine.search_by_name_address(firstname, lastname, address, limit=limit)


if __name__ == '__main__':
    # Demo/test
    logging.basicConfig(level=logging.INFO)

    print("Search Engine Factory")
    print("=" * 50)

    # Get engine info
    info = get_engine_info()
    print(f"Engine configuration: {json.dumps(info, indent=2)}")

    # Create engine
    try:
        engine = get_search_engine()
        print(f"\nCreated engine: {type(engine).__name__}")

        # Test search
        print("\nTesting search_by_ssn...")
        result = engine.search_by_ssn("123-45-6789", limit=5)
        results = json.loads(result)
        print(f"Found {len(results)} results")

    except Exception as e:
        print(f"Error: {e}")
