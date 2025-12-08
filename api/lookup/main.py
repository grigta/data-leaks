"""
Lookup API - Database-only search service (requires subscription)
"""
import logging
import os
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.search_engine import SearchEngine
from api.common.database import SQLITE_PATH, get_postgres_session
from api.common.auth import decode_access_token
from api.common.models_postgres import User, Subscription

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Lookup API",
    version="2.0.0",
    description="Database-only search service for SSN lookup (requires subscription)"
)

# Configure CORS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth2 scheme for JWT authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/public/auth/login")


# Pydantic Models
class SearchRequest(BaseModel):
    """Request model for person search"""
    firstname: str = Field(..., description="First name of the person")
    lastname: str = Field(..., description="Last name of the person")
    street: Optional[str] = Field(None, description="Street address (optional)")
    city: Optional[str] = Field(None, description="City (optional)")
    state: Optional[str] = Field(None, description="State code, e.g., NY, CA (optional)")
    phone: Optional[str] = Field(None, description="Phone number (optional)")


class SearchResponse(BaseModel):
    """Response model for search results"""
    database_matches: List[Dict[str, Any]] = Field(default_factory=list, description="SSN matches from local database")
    search_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata about the search")


# Authentication dependency
async def get_current_user_with_subscription(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_postgres_session)
) -> User:
    """
    FastAPI dependency to get current user and verify active subscription.

    Args:
        token: JWT token from Authorization header
        db: PostgreSQL database session

    Returns:
        Current user with valid subscription

    Raises:
        HTTPException: If token is invalid, user not found, or no active subscription
    """
    # Decode JWT token
    try:
        payload = decode_access_token(token)
    except Exception as e:
        logger.warning(f"Invalid token: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract user_id from payload
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token: user_id missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Load user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check for active subscription
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.is_active == True,
            Subscription.end_date > datetime.utcnow()
        )
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=403,
            detail="Active subscription required. Please purchase a subscription to access this feature."
        )

    return user


# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "lookup_api",
        "timestamp": datetime.utcnow().isoformat(),
        "subscription_required": True
    }


@app.post("/search", response_model=SearchResponse)
async def search_person(
    request: SearchRequest,
    current_user: User = Depends(get_current_user_with_subscription)
):
    """
    Search for person information in local database (requires active subscription)

    This endpoint:
    1. Validates user has an active subscription
    2. Searches local database for SSN using firstname+lastname+city/state/phone
    3. Returns matching results
    """
    logger.info(f"Search request from user {current_user.username}: {request.firstname} {request.lastname}")

    # Validate input
    if not request.firstname or not request.lastname:
        raise HTTPException(status_code=400, detail="firstname and lastname are required")

    search_metadata = {
        "search_timestamp": datetime.utcnow().isoformat(),
        "user_id": str(current_user.id),
        "search_params": {
            "firstname": request.firstname,
            "lastname": request.lastname,
            "street": request.street,
            "city": request.city,
            "state": request.state,
            "phone": request.phone
        }
    }

    try:
        # Search local database
        database_matches = []
        search_engine = SearchEngine(db_path=SQLITE_PATH)

        # Search by firstname + lastname + city + state
        if request.city and request.state:
            try:
                logger.info(f"Searching database by name+city+state")
                result_json = search_engine.search_by_fields(
                    firstname=request.firstname,
                    lastname=request.lastname,
                    city=request.city,
                    state=request.state,
                    limit=100
                )
                if result_json:
                    results = json.loads(result_json)
                    for result in results:
                        result["matched_by"] = "city_state"
                        database_matches.append(result)
                    logger.info(f"Found {len(results)} matches by city+state")
            except Exception as e:
                logger.error(f"Database search error (city+state): {str(e)}")

        # Search by firstname + lastname + phone
        if request.phone:
            try:
                logger.info(f"Searching database by name+phone")
                result_json = search_engine.search_by_fields(
                    firstname=request.firstname,
                    lastname=request.lastname,
                    phone=request.phone,
                    limit=100
                )
                if result_json:
                    results = json.loads(result_json)
                    for result in results:
                        result["matched_by"] = "phone"
                        database_matches.append(result)
                    logger.info(f"Found {len(results)} matches by phone")
            except Exception as e:
                logger.error(f"Database search error (phone): {str(e)}")

        # Search by firstname + lastname + state only (broader search)
        if len(database_matches) == 0 and request.state:
            try:
                logger.info(f"Searching database by name+state only")
                result_json = search_engine.search_by_fields(
                    firstname=request.firstname,
                    lastname=request.lastname,
                    state=request.state,
                    limit=100
                )
                if result_json:
                    results = json.loads(result_json)
                    for result in results:
                        result["matched_by"] = "state"
                        database_matches.append(result)
                    logger.info(f"Found {len(results)} matches by state")
            except Exception as e:
                logger.error(f"Database search error (state): {str(e)}")

        # Remove duplicates based on SSN
        unique_matches = {}
        for match in database_matches:
            ssn = match.get("ssn")
            if ssn and ssn not in unique_matches:
                unique_matches[ssn] = match

        database_matches = list(unique_matches.values())
        search_metadata["database_matches_count"] = len(database_matches)

        logger.info(f"Found {len(database_matches)} unique SSN matches in database")

        # Return response
        return SearchResponse(
            database_matches=database_matches,
            search_metadata=search_metadata
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during search: {str(e)}"
        )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc),
            "path": str(request.url)
        }
    )


# Startup and Shutdown Events
@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    logger.info("=== Lookup API Starting ===")
    logger.info(f"SQLITE_PATH: {SQLITE_PATH}")
    logger.info(f"CORS Origins: {ALLOWED_ORIGINS}")
    logger.info("Subscription required for access: True")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler"""
    logger.info("=== Lookup API Shutting Down ===")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
