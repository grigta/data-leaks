"""
Lookup router for Database Subscription search.

This router provides search functionality for users with active subscriptions
to search the local SSN database.
"""
import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.common.database import get_postgres_session, SQLITE_PATH
from api.common.models_postgres import User, Subscription
from api.public.dependencies import get_current_user
from database.search_engine import SearchEngine


logger = logging.getLogger(__name__)
router = APIRouter()


# Pydantic models
class LookupSearchRequest(BaseModel):
    firstname: str
    lastname: str
    street: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


class LookupSearchMatch(BaseModel):
    firstname: Optional[str] = None
    middlename: Optional[str] = None
    lastname: Optional[str] = None
    ssn: Optional[str] = None
    dob: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    phones: Optional[List[str]] = None
    emails: Optional[List[str]] = None
    addresses: Optional[List[dict]] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    matched_by: Optional[str] = None


class SearchMetadata(BaseModel):
    search_timestamp: str
    database_matches_count: int
    user_id: Optional[str] = None
    search_params: Optional[dict] = None


class LookupSearchResponse(BaseModel):
    database_matches: List[LookupSearchMatch]
    search_metadata: SearchMetadata


async def verify_subscription_access(
    current_user: User,
    db: AsyncSession
) -> bool:
    """Check if user has active subscription."""
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == current_user.id,
            Subscription.is_active == True,
            Subscription.end_date > datetime.utcnow()
        )
    )
    subscription = result.scalar_one_or_none()
    return subscription is not None


@router.post("/search", response_model=LookupSearchResponse)
async def search_database(
    request: LookupSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Search the local SSN database for matching records.

    Requires an active subscription.
    """
    # Check subscription access
    has_access = await verify_subscription_access(current_user, db)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active subscription required to search database"
        )

    # Initialize search engine with correct path from environment
    search_engine = SearchEngine(db_path=SQLITE_PATH)

    # Perform search based on available parameters
    results = []
    matched_by = None

    try:
        # Priority 1: Search by name + phone
        if request.phone:
            phones = [request.phone]
            results = search_engine._search_by_phone_match(
                request.firstname,
                request.lastname,
                phones,
                limit=50
            )
            if results:
                matched_by = "phone"

        # Priority 2: Search by name + address
        if not results and request.street:
            addresses = [request.street]
            results = search_engine._search_by_address_match(
                request.firstname,
                request.lastname,
                addresses,
                limit=50
            )
            if results:
                matched_by = "address"

        # Priority 3: Search by name + city/state
        if not results and (request.city or request.state):
            # Try name-only search and filter by city/state
            states = [request.state] if request.state else []
            if states:
                results = search_engine._search_by_state_match(
                    request.firstname,
                    request.lastname,
                    states,
                    limit=50
                )
                if results:
                    matched_by = "state"
                    # Further filter by city if provided
                    if request.city:
                        city_lower = request.city.lower()
                        results = [r for r in results if r.get('city', '').lower() == city_lower]

        # Fallback: Basic name search with address
        if not results and request.street:
            json_results = search_engine.search_by_name_address(
                request.firstname,
                request.lastname,
                request.street,
                limit=50
            )
            results = json.loads(json_results) if json_results else []
            if results:
                matched_by = "name_address"

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed"
        )

    # Convert results to response format
    matches = []
    for r in results:
        match = LookupSearchMatch(
            firstname=r.get('firstname'),
            lastname=r.get('lastname'),
            ssn=r.get('ssn'),
            dob=r.get('dob'),
            address=r.get('address'),
            city=r.get('city'),
            state=r.get('state'),
            zip=r.get('zip'),
            phones=[r.get('phone')] if r.get('phone') else None,
            emails=[r.get('email')] if r.get('email') else None,
            matched_by=matched_by
        )
        matches.append(match)

    logger.info(f"Lookup search by user {current_user.username}: {len(matches)} results")

    return LookupSearchResponse(
        database_matches=matches,
        search_metadata=SearchMetadata(
            search_timestamp=datetime.utcnow().isoformat(),
            database_matches_count=len(matches),
            user_id=str(current_user.id),
            search_params={
                "firstname": request.firstname,
                "lastname": request.lastname,
                "street": request.street,
                "city": request.city,
                "state": request.state,
                "phone": request.phone
            }
        )
    )
