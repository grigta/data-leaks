"""Centralized pricing constants and helper functions for API."""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, List, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging
import os
import time

logger = logging.getLogger(__name__)


# Search pricing constants
INSTANT_SSN_PRICE = Decimal("2.00")
MANUAL_SSN_PRICE = Decimal("3.00")
REVERSE_SSN_PRICE = Decimal("1.50")  # DEPRECATED: Used only for historical orders display

# External API costs (defaults, can be overridden via AppSettings)
SEARCHBUG_API_COST = Decimal("0.85")
INSTANT_SSN_ATTEMPT_COST = Decimal("0.85")  # Себестоимость за 1 попытку instant пробива
MANUAL_SSN_COST = Decimal("1.50")  # Себестоимость за 1 успешный ручной пробив
# WHITEPAGES_API_COST = Decimal("0.40")  # Себестоимость за 1 запрос WhitePages (temporarily disabled)

# Invitation/Referral bonuses (configurable via environment variables)
INVITATION_BONUS_INVITEE = Decimal(os.getenv("INVITATION_BONUS_INVITEE", "5.00"))  # Bonus for new user who registers with invitation code
INVITATION_BONUS_INVITER = Decimal(os.getenv("INVITATION_BONUS_INVITER", "3.00"))  # Bonus for user who invited someone

# SMS Service pricing
SMS_MARKUP = Decimal("1.20")  # 20% markup on DaisySMS prices


def round_price_to_5_cents(base_price: Decimal, markup: Decimal = SMS_MARKUP) -> Decimal:
    """
    Calculate price with markup and round to nearest 5 cents.

    Examples:
        - $0.40 * 1.20 = $0.48 → $0.50
        - $0.50 * 1.20 = $0.60 → $0.60
        - $0.73 * 1.20 = $0.876 → $0.90
        - $1.00 * 1.20 = $1.20 → $1.20

    Args:
        base_price: Base price from DaisySMS
        markup: Markup multiplier (default 1.20 = 20% markup)

    Returns:
        Decimal: Price rounded to nearest 0.05
    """
    price_with_markup = base_price * markup
    step = Decimal("0.05")
    rounded = (price_with_markup / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step
    return rounded.quantize(Decimal("0.01"))


async def get_user_price(
    db: AsyncSession,
    access_code: str,
    service_name: str,
    default_price: Decimal
) -> Decimal:
    """
    Get custom price for a user by access_code and service_name.
    Falls back to default_price if no custom pricing is found or if custom pricing is inactive.

    Note: This function queries by access_code for backward compatibility.
    For user_id-based queries, use get_user_price_by_id() or get_price_for_user().

    Args:
        db: Database session
        access_code: User's access code
        service_name: Service identifier ('instant_ssn', 'manual_ssn')
        default_price: Default price to use if no custom pricing found

    Returns:
        Decimal: Custom price or default price
    """
    try:
        # Import here to avoid circular import
        from api.common.models_postgres import CustomPricing

        result = await db.execute(
            select(CustomPricing)
            .where(
                CustomPricing.access_code == access_code,
                CustomPricing.service_name == service_name,
                CustomPricing.is_active == True
            )
        )
        custom_pricing = result.scalar_one_or_none()

        if custom_pricing:
            return custom_pricing.price

        return default_price
    except Exception as e:
        # Log the error with details
        logger.error(
            f"Error getting custom pricing: access_code={access_code}, "
            f"service_name={service_name}, default_price={default_price}, "
            f"error={e}",
            exc_info=True
        )
        # On any error, return default price
        return default_price


async def get_user_price_by_id(
    db: AsyncSession,
    user_id: UUID,
    service_name: str,
    default_price: Decimal
) -> Decimal:
    """
    Get custom price for a user by user_id and service_name.
    Falls back to default_price if no custom pricing is found or if custom pricing is inactive.

    Args:
        db: Database session
        user_id: User's UUID
        service_name: Service identifier ('instant_ssn', 'manual_ssn')
        default_price: Default price to use if no custom pricing found

    Returns:
        Decimal: Custom price or default price
    """
    try:
        # Import here to avoid circular import
        from api.common.models_postgres import CustomPricing

        result = await db.execute(
            select(CustomPricing)
            .where(
                CustomPricing.user_id == user_id,
                CustomPricing.service_name == service_name,
                CustomPricing.is_active == True
            )
        )
        custom_pricing = result.scalar_one_or_none()

        if custom_pricing:
            return custom_pricing.price

        return default_price
    except Exception as e:
        # Log the error with details
        logger.error(
            f"Error getting custom pricing by user_id: user_id={user_id}, "
            f"service_name={service_name}, default_price={default_price}, "
            f"error={e}",
            exc_info=True
        )
        # On any error, return default price
        return default_price


async def get_price_for_user(
    db: AsyncSession,
    service_name: str,
    default_price: Decimal,
    user_id: Optional[UUID] = None,
    access_code: Optional[str] = None
) -> Decimal:
    """
    Unified function to get custom price for a user.
    Queries by user_id if provided, otherwise by access_code.
    Falls back to default_price if no custom pricing is found or if custom pricing is inactive.

    Args:
        db: Database session
        service_name: Service identifier ('instant_ssn', 'manual_ssn')
        default_price: Default price to use if no custom pricing found
        user_id: Optional user's UUID
        access_code: Optional user's access code

    Returns:
        Decimal: Custom price or default price
    """
    if user_id:
        return await get_user_price_by_id(db, user_id, service_name, default_price)
    elif access_code:
        return await get_user_price(db, access_code, service_name, default_price)
    else:
        return default_price


async def check_maintenance_mode(
    db: AsyncSession,
    service_name: str
) -> tuple[bool, Optional[str]]:
    """
    Check if a service is in maintenance mode.

    Args:
        db: Database session
        service_name: Service identifier ('instant_ssn', 'manual_ssn')

    Returns:
        tuple: (is_maintenance, message) - True if in maintenance with optional message
    """
    try:
        # Import here to avoid circular import
        from api.common.models_postgres import MaintenanceMode

        result = await db.execute(
            select(MaintenanceMode)
            .where(MaintenanceMode.service_name == service_name)
        )
        maintenance = result.scalar_one_or_none()

        if maintenance and maintenance.is_active:
            return (True, maintenance.message)

        return (False, None)
    except Exception as e:
        # Log the error with details
        logger.error(
            f"Error checking maintenance mode: service_name={service_name}, "
            f"error={e}",
            exc_info=True
        )
        # On any error, assume not in maintenance
        return (False, None)


# --- Search Flow ---

VALID_SEARCH_FLOWS = [
    # "wp_sb_manual",  # temporarily disabled
    "sb_manual",
    # "wp_manual",  # temporarily disabled
    "manual",
    "sb",
    # "wp",  # temporarily disabled
]
DEFAULT_SEARCH_FLOW = "sb_manual"

_SEARCH_FLOW_MAPPING: Dict[str, Dict[str, Any]] = {
    # "wp_sb_manual": {"steps": ["wp", "sb"], "has_manual_fallback": True},  # temporarily disabled
    "sb_manual":    {"steps": ["sb"], "has_manual_fallback": True},
    # "wp_manual":    {"steps": ["wp"], "has_manual_fallback": True},  # temporarily disabled
    "manual":       {"steps": [], "has_manual_fallback": True},
    "sb":           {"steps": ["sb"], "has_manual_fallback": False},
    # "wp":           {"steps": ["wp"], "has_manual_fallback": False},  # temporarily disabled
}

# In-memory cache for search_flow (TTL 60 seconds)
_search_flow_cache: Dict[str, Any] = {"value": DEFAULT_SEARCH_FLOW, "expires_at": 0.0}
_SEARCH_FLOW_CACHE_TTL = 60


async def get_search_flow(db: AsyncSession) -> str:
    """Get current search flow from AppSettings with in-memory cache (60s TTL)."""
    global _search_flow_cache

    now = time.time()
    if _search_flow_cache["expires_at"] > now:
        return _search_flow_cache["value"]

    try:
        from api.common.models_postgres import AppSettings

        result = await db.execute(
            select(AppSettings).where(AppSettings.key == "search_flow")
        )
        setting = result.scalar_one_or_none()

        value = setting.value if setting else DEFAULT_SEARCH_FLOW
        if value not in VALID_SEARCH_FLOWS:
            value = DEFAULT_SEARCH_FLOW

        _search_flow_cache = {"value": value, "expires_at": now + _SEARCH_FLOW_CACHE_TTL}
        return value
    except Exception as e:
        logger.error(f"Error getting search_flow: {e}", exc_info=True)
        return DEFAULT_SEARCH_FLOW


def invalidate_search_flow_cache():
    """Invalidate the in-memory cache (call after admin updates setting)."""
    global _search_flow_cache
    _search_flow_cache = {"value": DEFAULT_SEARCH_FLOW, "expires_at": 0.0}


def parse_search_flow(flow: str) -> Dict[str, Any]:
    """Parse flow string into structured steps.

    Returns dict with:
        steps: list of provider names ("wp", "sb")
        has_manual_fallback: whether to create ManualSSNTicket on failure
    """
    return _SEARCH_FLOW_MAPPING.get(flow, _SEARCH_FLOW_MAPPING[DEFAULT_SEARCH_FLOW])


# --- API Costs (dynamic, stored in AppSettings) ---

API_COST_KEYS = {
    "api_cost_searchbug": SEARCHBUG_API_COST,
    "api_cost_manual_ssn": MANUAL_SSN_COST,
    # "api_cost_whitepages": WHITEPAGES_API_COST,  # temporarily disabled
    "default_price_instant_ssn": INSTANT_SSN_PRICE,
}

# In-memory cache for API costs (TTL 60 seconds)
_api_costs_cache: Dict[str, Any] = {"values": {}, "expires_at": 0.0}
_API_COSTS_CACHE_TTL = 60


async def get_api_costs(db: AsyncSession) -> Dict[str, Decimal]:
    """Get all API costs from AppSettings with in-memory cache (60s TTL).

    Returns dict with keys: api_cost_searchbug, api_cost_manual_ssn, api_cost_whitepages
    """
    global _api_costs_cache

    now = time.time()
    if _api_costs_cache["expires_at"] > now and _api_costs_cache["values"]:
        return _api_costs_cache["values"]

    try:
        from api.common.models_postgres import AppSettings

        result = await db.execute(
            select(AppSettings).where(AppSettings.key.in_(API_COST_KEYS.keys()))
        )
        settings = {s.key: s.value for s in result.scalars().all()}

        costs = {}
        for key, default in API_COST_KEYS.items():
            try:
                costs[key] = Decimal(settings[key]) if key in settings else default
            except Exception:
                costs[key] = default

        _api_costs_cache = {"values": costs, "expires_at": now + _API_COSTS_CACHE_TTL}
        return costs
    except Exception as e:
        logger.error(f"Error getting API costs: {e}", exc_info=True)
        return dict(API_COST_KEYS)


async def get_api_cost(db: AsyncSession, cost_key: str) -> Decimal:
    """Get a single API cost by key."""
    costs = await get_api_costs(db)
    return costs.get(cost_key, API_COST_KEYS.get(cost_key, Decimal("0")))


async def get_default_instant_ssn_price(db: AsyncSession) -> Decimal:
    """Get default Instant SSN price from AppSettings (or fallback to INSTANT_SSN_PRICE)."""
    return await get_api_cost(db, "default_price_instant_ssn")


def invalidate_api_costs_cache():
    """Invalidate the in-memory API costs cache."""
    global _api_costs_cache
    _api_costs_cache = {"values": {}, "expires_at": 0.0}


# --- SearchBug API Keys (dynamic, stored in AppSettings) ---

# In-memory cache for SearchBug API keys (TTL 60 seconds)
_searchbug_keys_cache: Dict[str, Any] = {"values": {}, "expires_at": 0.0}
_SEARCHBUG_KEYS_CACHE_TTL = 60


async def get_searchbug_keys(db: AsyncSession) -> Dict[str, str]:
    """Get SearchBug API keys from AppSettings with in-memory cache (60s TTL).

    Returns dict with keys: searchbug_co_code, searchbug_password.
    Falls back to environment variables if no DB setting exists.
    """
    global _searchbug_keys_cache

    now = time.time()
    if _searchbug_keys_cache["expires_at"] > now and _searchbug_keys_cache["values"]:
        return _searchbug_keys_cache["values"]

    try:
        from api.common.models_postgres import AppSettings

        result = await db.execute(
            select(AppSettings).where(
                AppSettings.key.in_(("searchbug_co_code", "searchbug_password"))
            )
        )
        settings = {s.key: s.value for s in result.scalars().all()}

        keys = {
            "searchbug_co_code": settings.get("searchbug_co_code") or os.getenv("SEARCHBUG_CO_CODE", ""),
            "searchbug_password": settings.get("searchbug_password") or os.getenv("SEARCHBUG_PASSWORD", ""),
        }

        _searchbug_keys_cache = {"values": keys, "expires_at": now + _SEARCHBUG_KEYS_CACHE_TTL}
        return keys
    except Exception as e:
        logger.error(f"Error getting SearchBug keys: {e}", exc_info=True)
        return {
            "searchbug_co_code": os.getenv("SEARCHBUG_CO_CODE", ""),
            "searchbug_password": os.getenv("SEARCHBUG_PASSWORD", ""),
        }


def invalidate_searchbug_keys_cache():
    """Invalidate the in-memory SearchBug keys cache."""
    global _searchbug_keys_cache
    _searchbug_keys_cache = {"values": {}, "expires_at": 0.0}
