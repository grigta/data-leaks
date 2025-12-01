"""Centralized pricing constants for bot (imports from API common module)."""
import sys
from pathlib import Path

# Add API common module to Python path
api_path = Path(__file__).parent.parent.parent / "api"
sys.path.insert(0, str(api_path))

# Import pricing constants from API common module
from common.pricing import (
    INSTANT_SSN_PRICE,
    MANUAL_SSN_PRICE,
    REVERSE_SSN_PRICE,
    SEARCHBUG_API_COST
)
