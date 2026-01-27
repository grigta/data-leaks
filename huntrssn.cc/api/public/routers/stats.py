from fastapi import APIRouter, Depends, Request, Response, Query
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from api.common.database import get_postgres_session
from api.common.models_postgres import Session, User
from api.public.dependencies import get_current_user, limiter


# Response Models
class StatsOnlineResponse(BaseModel):
    count: int
    timestamp: str


class StatsIPsResponse(BaseModel):
    unique_ips: int
    last_30_days: int


class StatsLoyaltyResponse(BaseModel):
    percentage: str
    tier: str


class ProxyDataItem(BaseModel):
    proxy_ip: str
    country: str
    city: str
    region: str
    isp: str
    zip: str
    speed: str  # "Fast" or "Moderate"
    type: str  # "Residential", "Mobile", or "Hosting"
    price: float


router = APIRouter()


@router.get("/online", response_model=StatsOnlineResponse)
@limiter.limit("100/hour")
async def get_online_users(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """Get the count of currently online users (active sessions)."""
    # Query active sessions where expires_at is in the future
    result = await db.execute(
        select(func.count()).select_from(Session).where(Session.expires_at > func.now())
    )
    count = result.scalar()

    return StatsOnlineResponse(
        count=count,
        timestamp=datetime.now().isoformat()
    )


@router.get("/ips", response_model=StatsIPsResponse)
@limiter.limit("100/hour")
async def get_ip_stats(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user)
):
    """Get unique IP statistics."""
    # TODO: Implement real IP tracking when analytics service is integrated
    return StatsIPsResponse(
        unique_ips=22521,
        last_30_days=18432
    )


@router.get("/loyalty", response_model=StatsLoyaltyResponse)
@limiter.limit("100/hour")
async def get_loyalty_info(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user)
):
    """Get user's loyalty program information."""
    # TODO: Calculate real loyalty tier based on user.balance or purchase history
    return StatsLoyaltyResponse(
        percentage="20% OFF",
        tier="Gold"
    )


@router.get("/data", response_model=List[ProxyDataItem])
@limiter.limit("100/hour")
async def get_proxy_data(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    country: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    zip_code: Optional[str] = Query(None, alias="zip"),
    proxy_type: Optional[str] = Query(None, alias="type"),
    speed: Optional[str] = None
):
    """Get proxy data for dashboard table with optional filtering."""
    # TODO: Replace with real proxy data from database when proxy service is integrated

    # Mock data matching reference image
    mock_data = [
        ProxyDataItem(
            proxy_ip="192.168.1.100",
            country="US",
            city="New York",
            region="NY",
            isp="Verizon",
            zip="10001",
            speed="Fast",
            type="Residential",
            price=12.99
        ),
        ProxyDataItem(
            proxy_ip="192.168.1.101",
            country="US",
            city="Los Angeles",
            region="CA",
            isp="Comcast",
            zip="90001",
            speed="Fast",
            type="Residential",
            price=11.99
        ),
        ProxyDataItem(
            proxy_ip="192.168.1.102",
            country="US",
            city="Chicago",
            region="IL",
            isp="AT&T",
            zip="60601",
            speed="Moderate",
            type="Mobile",
            price=8.99
        ),
        ProxyDataItem(
            proxy_ip="192.168.1.103",
            country="US",
            city="Miami",
            region="FL",
            isp="T-Mobile",
            zip="33101",
            speed="Fast",
            type="Mobile",
            price=9.99
        ),
        ProxyDataItem(
            proxy_ip="192.168.1.104",
            country="US",
            city="Dallas",
            region="TX",
            isp="AT&T",
            zip="75201",
            speed="Moderate",
            type="Residential",
            price=10.99
        ),
        ProxyDataItem(
            proxy_ip="192.168.2.100",
            country="UK",
            city="London",
            region="England",
            isp="Vodafone",
            zip="SW1A 1AA",
            speed="Fast",
            type="Residential",
            price=14.99
        ),
        ProxyDataItem(
            proxy_ip="192.168.2.101",
            country="UK",
            city="London",
            region="England",
            isp="BT",
            zip="EC1A 1BB",
            speed="Fast",
            type="Hosting",
            price=5.99
        ),
        ProxyDataItem(
            proxy_ip="192.168.3.100",
            country="DE",
            city="Berlin",
            region="Berlin",
            isp="Deutsche Telekom",
            zip="10115",
            speed="Fast",
            type="Residential",
            price=13.99
        ),
        ProxyDataItem(
            proxy_ip="192.168.3.101",
            country="DE",
            city="Munich",
            region="Bavaria",
            isp="Vodafone",
            zip="80331",
            speed="Moderate",
            type="Hosting",
            price=4.99
        ),
        ProxyDataItem(
            proxy_ip="192.168.4.100",
            country="FR",
            city="Paris",
            region="Île-de-France",
            isp="Orange",
            zip="75001",
            speed="Fast",
            type="Residential",
            price=12.99
        ),
        ProxyDataItem(
            proxy_ip="192.168.5.100",
            country="CA",
            city="Toronto",
            region="ON",
            isp="Rogers",
            zip="M5H 2N2",
            speed="Fast",
            type="Residential",
            price=11.99
        ),
        ProxyDataItem(
            proxy_ip="192.168.5.101",
            country="CA",
            city="Vancouver",
            region="BC",
            isp="Telus",
            zip="V6B 1A1",
            speed="Moderate",
            type="Mobile",
            price=7.99
        ),
        ProxyDataItem(
            proxy_ip="192.168.1.105",
            country="US",
            city="Seattle",
            region="WA",
            isp="Comcast",
            zip="98101",
            speed="Fast",
            type="Hosting",
            price=2.99
        ),
        ProxyDataItem(
            proxy_ip="192.168.1.106",
            country="US",
            city="Boston",
            region="MA",
            isp="Verizon",
            zip="02101",
            speed="Moderate",
            type="Residential",
            price=10.49
        ),
        ProxyDataItem(
            proxy_ip="192.168.4.101",
            country="FR",
            city="Lyon",
            region="Auvergne-Rhône-Alpes",
            isp="Free",
            zip="69001",
            speed="Moderate",
            type="Hosting",
            price=3.99
        ),
    ]

    # Apply filters
    filtered_data = mock_data

    if country:
        filtered_data = [item for item in filtered_data if item.country == country]

    if state:
        filtered_data = [item for item in filtered_data if item.region == state]

    if city:
        filtered_data = [item for item in filtered_data if item.city == city]

    if zip_code:
        filtered_data = [item for item in filtered_data if item.zip == zip_code]

    if proxy_type:
        filtered_data = [item for item in filtered_data if item.type == proxy_type]

    if speed:
        filtered_data = [item for item in filtered_data if item.speed == speed]

    return filtered_data
