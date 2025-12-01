"""Bot configuration package."""
from .bot_config import BotConfig
from .pricing import (
    INSTANT_SSN_PRICE,
    MANUAL_SSN_PRICE,
    REVERSE_SSN_PRICE,
    SEARCHBUG_API_COST
)

__all__ = [
    'BotConfig',
    'INSTANT_SSN_PRICE',
    'MANUAL_SSN_PRICE',
    'REVERSE_SSN_PRICE',
    'SEARCHBUG_API_COST'
]
