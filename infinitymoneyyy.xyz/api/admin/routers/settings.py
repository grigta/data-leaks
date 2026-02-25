"""Admin router for global application settings."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict
import logging

from api.common.database import get_postgres_session
from api.common.models_postgres import AppSettings
from api.admin.dependencies import get_current_admin_user
from decimal import Decimal
from api.common.pricing import (
    VALID_SEARCH_FLOWS, DEFAULT_SEARCH_FLOW, invalidate_search_flow_cache,
    API_COST_KEYS, get_api_costs, invalidate_api_costs_cache,
    invalidate_searchbug_keys_cache
)
import os

logger = logging.getLogger(__name__)
router = APIRouter()


class SearchFlowResponse(BaseModel):
    search_flow: str
    updated_at: Optional[str] = None


class UpdateSearchFlowRequest(BaseModel):
    search_flow: str

    @field_validator('search_flow')
    @classmethod
    def validate_search_flow(cls, v):
        if v not in VALID_SEARCH_FLOWS:
            raise ValueError(
                f"Invalid search flow. Must be one of: {', '.join(VALID_SEARCH_FLOWS)}"
            )
        return v


class SearchFlowOption(BaseModel):
    value: str
    label: str
    description: str


@router.get("/search-flow", response_model=SearchFlowResponse)
async def get_search_flow_setting(
    db: AsyncSession = Depends(get_postgres_session),
    admin_user=Depends(get_current_admin_user),
):
    """Get current search flow setting."""
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "search_flow")
    )
    setting = result.scalar_one_or_none()

    return SearchFlowResponse(
        search_flow=setting.value if setting else DEFAULT_SEARCH_FLOW,
        updated_at=setting.updated_at.isoformat() if setting else None,
    )


@router.put("/search-flow", response_model=SearchFlowResponse)
async def update_search_flow_setting(
    request: UpdateSearchFlowRequest,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user=Depends(get_current_admin_user),
):
    """Update search flow setting."""
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "search_flow")
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = request.search_flow
    else:
        db.add(AppSettings(key="search_flow", value=request.search_flow))

    await db.commit()

    invalidate_search_flow_cache()

    logger.info(
        f"Admin {admin_user.username} updated search_flow to '{request.search_flow}'"
    )

    # Re-read to get updated_at
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "search_flow")
    )
    setting = result.scalar_one_or_none()

    return SearchFlowResponse(
        search_flow=setting.value,
        updated_at=setting.updated_at.isoformat() if setting else None,
    )


@router.get("/search-flow/options", response_model=Dict)
async def get_search_flow_options(
    admin_user=Depends(get_current_admin_user),
):
    """Get all available search flow options with descriptions."""
    options = [
        # {  # temporarily disabled
        #     "value": "wp_sb_manual",
        #     "label": "WhitePages → SearchBug → Manual",
        #     "description": "Full chain: WP first, then SB, then manual ticket",
        # },
        {
            "value": "sb_manual",
            "label": "SearchBug → Manual",
            "description": "Default: SB first, then manual ticket if not found",
        },
        # {  # temporarily disabled
        #     "value": "wp_manual",
        #     "label": "WhitePages → Manual",
        #     "description": "WP first, then manual ticket if not found",
        # },
        {
            "value": "manual",
            "label": "Manual only",
            "description": "Skip all APIs, create manual ticket immediately",
        },
        {
            "value": "sb",
            "label": "SearchBug only",
            "description": "SB only, no manual fallback",
        },
        # {  # temporarily disabled
        #     "value": "wp",
        #     "label": "WhitePages only",
        #     "description": "WP only, no manual fallback",
        # },
    ]
    return {"options": options}


# --- API Costs ---

API_COST_LABELS = {
    "api_cost_searchbug": "SearchBug (Instant SSN)",
    "api_cost_manual_ssn": "Manual SSN",
    # "api_cost_whitepages": "WhitePages",  # temporarily disabled
    "default_price_instant_ssn": "Instant SSN Price (Default)",
}


class ApiCostsResponse(BaseModel):
    costs: Dict[str, str]
    labels: Dict[str, str]


class UpdateApiCostsRequest(BaseModel):
    costs: Dict[str, str]

    @field_validator('costs')
    @classmethod
    def validate_costs(cls, v):
        for key, val in v.items():
            if key not in API_COST_KEYS:
                raise ValueError(f"Unknown cost key: {key}")
            try:
                d = Decimal(val)
                if d < 0:
                    raise ValueError(f"Cost cannot be negative: {key}={val}")
            except Exception:
                raise ValueError(f"Invalid decimal value for {key}: {val}")
        return v


@router.get("/api-costs", response_model=ApiCostsResponse)
async def get_api_costs_setting(
    db: AsyncSession = Depends(get_postgres_session),
    admin_user=Depends(get_current_admin_user),
):
    """Get current API cost settings."""
    costs = await get_api_costs(db)
    return ApiCostsResponse(
        costs={k: str(v) for k, v in costs.items()},
        labels=API_COST_LABELS,
    )


@router.put("/api-costs", response_model=ApiCostsResponse)
async def update_api_costs_setting(
    request: UpdateApiCostsRequest,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user=Depends(get_current_admin_user),
):
    """Update API cost settings."""
    for key, val in request.costs.items():
        result = await db.execute(
            select(AppSettings).where(AppSettings.key == key)
        )
        setting = result.scalar_one_or_none()

        if setting:
            setting.value = val
        else:
            db.add(AppSettings(key=key, value=val))

    await db.commit()
    invalidate_api_costs_cache()

    logger.info(
        f"Admin {admin_user.username} updated API costs: {request.costs}"
    )

    costs = await get_api_costs(db)
    return ApiCostsResponse(
        costs={k: str(v) for k, v in costs.items()},
        labels=API_COST_LABELS,
    )


# --- SearchBug API Keys ---

class SearchbugKeysResponse(BaseModel):
    co_code: str
    has_password: bool
    source: str  # "database" or "env"
    updated_at: Optional[str] = None


class UpdateSearchbugKeysRequest(BaseModel):
    co_code: Optional[str] = None
    password: Optional[str] = None

    @field_validator('co_code')
    @classmethod
    def validate_co_code(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError("CO_CODE cannot be empty")
        return v.strip() if v else v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if v is not None and len(v.strip()) == 0:
            raise ValueError("Password cannot be empty")
        return v.strip() if v else v


@router.get("/searchbug-keys", response_model=SearchbugKeysResponse)
async def get_searchbug_keys_setting(
    db: AsyncSession = Depends(get_postgres_session),
    admin_user=Depends(get_current_admin_user),
):
    """Get current SearchBug API key settings (masked)."""
    result = await db.execute(
        select(AppSettings).where(
            AppSettings.key.in_(("searchbug_co_code", "searchbug_password"))
        )
    )
    settings = {s.key: s for s in result.scalars().all()}

    if "searchbug_co_code" in settings:
        co_code_val = settings["searchbug_co_code"].value
        masked = "***" + co_code_val[-4:] if len(co_code_val) > 4 else "***"
        source = "database"
        updated_at = settings["searchbug_co_code"].updated_at.isoformat()
    else:
        env_co_code = os.getenv("SEARCHBUG_CO_CODE", "")
        masked = "***" + env_co_code[-4:] if len(env_co_code) > 4 else ("***" if env_co_code else "")
        source = "env"
        updated_at = None

    has_password = "searchbug_password" in settings or bool(os.getenv("SEARCHBUG_PASSWORD", ""))

    return SearchbugKeysResponse(
        co_code=masked,
        has_password=has_password,
        source=source,
        updated_at=updated_at,
    )


@router.put("/searchbug-keys", response_model=SearchbugKeysResponse)
async def update_searchbug_keys_setting(
    request: UpdateSearchbugKeysRequest,
    db: AsyncSession = Depends(get_postgres_session),
    admin_user=Depends(get_current_admin_user),
):
    """Update SearchBug API key settings."""
    if request.co_code is None and request.password is None:
        raise HTTPException(status_code=400, detail="At least one field must be provided")

    for field, key in [("co_code", "searchbug_co_code"), ("password", "searchbug_password")]:
        value = getattr(request, field)
        if value is not None:
            result = await db.execute(
                select(AppSettings).where(AppSettings.key == key)
            )
            setting = result.scalar_one_or_none()
            if setting:
                setting.value = value
            else:
                db.add(AppSettings(key=key, value=value))

    await db.commit()
    invalidate_searchbug_keys_cache()

    logger.info(
        f"Admin {admin_user.username} updated SearchBug API keys "
        f"(co_code={'yes' if request.co_code else 'no'}, "
        f"password={'yes' if request.password else 'no'})"
    )

    return await get_searchbug_keys_setting(db=db, admin_user=admin_user)
