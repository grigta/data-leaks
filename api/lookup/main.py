"""
Lookup API - Fast search service combining SearchBug API and local database
"""
import logging
import os
import json
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.common.searchbug_client import (
    SearchbugClient,
    SearchbugAPIError,
    SearchbugNotFoundError
)
from database.search_engine import SearchEngine
from api.common.database import SQLITE_PATH

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Lookup API",
    version="1.0.0",
    description="Fast search service combining SearchBug API and local SSN database"
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
    searchbug_data: Dict[str, Any] = Field(default_factory=dict, description="Raw data from SearchBug API")
    searchbug_candidates: List[Dict[str, Any]] = Field(default_factory=list, description="Candidates from SearchBug API")
    database_matches: List[Dict[str, Any]] = Field(default_factory=list, description="SSN matches from local database")
    combined_results: List[Dict[str, Any]] = Field(default_factory=list, description="Combined data from both sources")
    search_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata about the search")


# Helper Functions
def extract_zip_codes(addresses: List[Dict[str, Any]]) -> List[str]:
    """Extract unique ZIP codes from address list"""
    zip_codes = set()
    for addr in addresses:
        if isinstance(addr, dict):
            # Try different possible field names
            zip_code = addr.get('zip_code') or addr.get('postal_code') or addr.get('zip')
            if zip_code:
                # Clean ZIP code (remove +4 if present)
                zip_clean = str(zip_code).split('-')[0].strip()
                if zip_clean and len(zip_clean) == 5:
                    zip_codes.add(zip_clean)
    return list(zip_codes)


def extract_phone_numbers(phones: List[Dict[str, Any]]) -> List[str]:
    """Extract unique phone numbers from phone list"""
    phone_numbers = set()
    for phone in phones:
        if isinstance(phone, dict):
            # Try different possible field names
            number = phone.get('number') or phone.get('phone_number') or phone.get('line_number')
            if number:
                # Clean phone number (remove non-digits)
                phone_clean = ''.join(filter(str.isdigit, str(number)))
                if phone_clean and len(phone_clean) >= 10:
                    phone_numbers.add(phone_clean)
    return list(phone_numbers)


def merge_results(searchbug_person: Dict[str, Any], db_record: Dict[str, Any]) -> Dict[str, Any]:
    """Merge SearchBug data with database record"""
    # Extract first name from names array
    names = searchbug_person.get("names", [])
    first_name = names[0].get("first_name") if names and len(names) > 0 else None
    last_name = names[0].get("last_name") if names and len(names) > 0 else None

    merged = {
        # From database (SSN)
        "ssn": db_record.get("ssn"),
        "source": db_record.get("source"),

        # From SearchBug (primary info)
        "report_token": searchbug_person.get("report_token"),
        "firstname": db_record.get("firstname") or first_name,
        "middlename": db_record.get("middlename"),
        "lastname": db_record.get("lastname") or last_name,

        # Contact information
        "phones": searchbug_person.get("phones", []),
        "emails": searchbug_person.get("emails", []),
        "addresses": searchbug_person.get("addresses", []),

        # Additional data
        "dob": searchbug_person.get("dob") or db_record.get("dob"),
        "age": db_record.get("age"),
        "gender": db_record.get("gender"),

        # Database fields
        "city": db_record.get("city"),
        "state": db_record.get("state"),
        "zip": db_record.get("zip"),
        "phone": db_record.get("phone"),
        "email": db_record.get("email"),

        # Metadata
        "match_score": db_record.get("match_score", 0.0),
        "matched_by": db_record.get("matched_by", "unknown")
    }
    return merged


# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "lookup_api",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/search", response_model=SearchResponse)
async def search_person(request: SearchRequest):
    """
    Search for person information across SearchBug API and local database

    This endpoint:
    1. Searches SearchBug API for all matching candidates
    2. Extracts ZIP codes and phone numbers from results
    3. Searches local database for SSN using firstname+lastname+zip/phone
    4. Returns combined results
    """
    logger.info(f"Search request received: {request.firstname} {request.lastname}")

    # Validate input
    if not request.firstname or not request.lastname:
        raise HTTPException(status_code=400, detail="firstname and lastname are required")

    search_metadata = {
        "search_timestamp": datetime.utcnow().isoformat(),
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
        # Step 1: Search SearchBug API
        searchbug_co_code = os.getenv("SEARCHBUG_CO_CODE")
        searchbug_password = os.getenv("SEARCHBUG_PASSWORD")
        searchbug_api_url = os.getenv("SEARCHBUG_API_URL", "https://data.searchbug.com/api/search.aspx")

        if not searchbug_co_code or not searchbug_password:
            logger.warning("SEARCHBUG_CO_CODE or SEARCHBUG_PASSWORD not configured")
            search_metadata["searchbug_status"] = "api_credentials_missing"
            searchbug_data = {}
            all_candidates = []
        else:
            # Use async context manager to ensure proper client initialization and cleanup
            async with SearchbugClient(co_code=searchbug_co_code, password=searchbug_password, api_url=searchbug_api_url) as searchbug_client:
                all_candidates = []
                searchbug_data = {}

                try:
                    # Try primary search: Name + Address with all available parameters
                    logger.info(f"Searching SearchBug by name+address: {request.firstname} {request.lastname}, {request.city or 'N/A'}, {request.state or 'N/A'}")
                    searchbug_result = await searchbug_client.search_person_by_name_address(
                        firstname=request.firstname,
                        lastname=request.lastname,
                        address=request.street,
                        city=request.city,
                        state=request.state
                    )

                    # SearchBug returns a single person dict or None
                    if searchbug_result:
                        all_candidates = [searchbug_result]
                    else:
                        all_candidates = []

                    searchbug_data = {
                        "response_type": "dict" if searchbug_result else "none",
                        "candidates_count": len(all_candidates),
                        "search_method": "name_address"
                    }
                    search_metadata["searchbug_status"] = "success"
                    search_metadata["searchbug_candidates_count"] = len(all_candidates)
                    logger.info(f"SearchBug (name+address) returned {len(all_candidates)} candidates")

                except SearchbugNotFoundError:
                    logger.info("No results found in SearchBug API by name+address")
                    search_metadata["searchbug_status"] = "not_found_address"

                except SearchbugAPIError as e:
                    logger.error(f"SearchBug API error (name+address): {str(e)}", exc_info=True)
                    searchbug_data = {"error": str(e), "search_method": "name_address"}
                    search_metadata["searchbug_status"] = "api_error_address"

                # Fallback: If no results and phone is provided, try search by phone
                if len(all_candidates) == 0 and request.phone:
                    try:
                        logger.info(f"Trying fallback search by phone: {request.phone}")
                        phone_result = await searchbug_client.search_person_by_phone(phone=request.phone)

                        # SearchBug returns a single person dict or None
                        if phone_result:
                            # Filter to match name if possible
                            names = phone_result.get("names", [])
                            if names and len(names) > 0:
                                first_name = (names[0].get("first_name") or "").lower()
                                last_name = (names[0].get("last_name") or "").lower()

                                if (request.firstname.lower() in first_name and
                                    request.lastname.lower() in last_name):
                                    all_candidates = [phone_result]
                                    filtered = True
                                else:
                                    # Name doesn't match, but still include
                                    all_candidates = [phone_result]
                                    filtered = False
                            else:
                                all_candidates = [phone_result]
                                filtered = False

                            searchbug_data = {
                                "response_type": "phone_search",
                                "candidates_count": len(all_candidates),
                                "search_method": "phone",
                                "phone_filtered": filtered
                            }
                            search_metadata["searchbug_status"] = "success_phone"
                            search_metadata["searchbug_candidates_count"] = len(all_candidates)
                            logger.info(f"SearchBug (phone) returned {len(all_candidates)} candidates")

                    except SearchbugNotFoundError:
                        logger.info("No results found in SearchBug API by phone")
                        search_metadata["searchbug_status"] = "not_found_phone"

                    except SearchbugAPIError as e:
                        logger.error(f"SearchBug API error (phone): {str(e)}", exc_info=True)
                        searchbug_data["phone_error"] = str(e)
                        search_metadata["searchbug_status"] = "api_error_phone"

        # Step 2: Extract ZIP codes and phone numbers
        all_zip_codes = set()
        all_phone_numbers = set()

        for candidate in all_candidates:
            # Extract ZIP codes from addresses
            addresses = candidate.get("addresses", [])
            for addr in addresses:
                if isinstance(addr, dict):
                    zip_code = addr.get('zip_code')
                    if zip_code:
                        zip_clean = str(zip_code).split('-')[0].strip()
                        if zip_clean and len(zip_clean) == 5:
                            all_zip_codes.add(zip_clean)

            # Extract phone numbers
            phones = candidate.get("phones", [])
            for phone in phones:
                if isinstance(phone, dict):
                    number = phone.get('phone_number')
                    if number:
                        phone_clean = ''.join(filter(str.isdigit, str(number)))
                        if phone_clean and len(phone_clean) >= 10:
                            all_phone_numbers.add(phone_clean)

        search_metadata["extracted_zips"] = list(all_zip_codes)
        search_metadata["extracted_phones"] = list(all_phone_numbers)

        logger.info(f"Extracted {len(all_zip_codes)} unique ZIP codes and {len(all_phone_numbers)} unique phone numbers")

        # Step 3: Search local database
        database_matches = []
        search_engine = SearchEngine(db_path=SQLITE_PATH)

        # Search by firstname + lastname + ZIP
        for zip_code in all_zip_codes:
            try:
                result_json = search_engine.search_by_fields(
                    firstname=request.firstname,
                    lastname=request.lastname,
                    zip=zip_code
                )

                if result_json:
                    results = json.loads(result_json)
                    for result in results:
                        result["matched_by"] = f"zip:{zip_code}"
                        database_matches.append(result)

            except Exception as e:
                logger.error(f"Database search error for ZIP {zip_code}: {str(e)}")

        # Search by firstname + lastname + phone
        for phone_number in all_phone_numbers:
            try:
                result_json = search_engine.search_by_fields(
                    firstname=request.firstname,
                    lastname=request.lastname,
                    phone=phone_number
                )

                if result_json:
                    results = json.loads(result_json)
                    for result in results:
                        result["matched_by"] = f"phone:{phone_number}"
                        database_matches.append(result)

            except Exception as e:
                logger.error(f"Database search error for phone {phone_number}: {str(e)}")

        # Remove duplicates based on SSN
        unique_matches = {}
        for match in database_matches:
            ssn = match.get("ssn")
            if ssn and ssn not in unique_matches:
                unique_matches[ssn] = match

        database_matches = list(unique_matches.values())
        search_metadata["database_matches_count"] = len(database_matches)

        logger.info(f"Found {len(database_matches)} unique SSN matches in database")

        # Step 3.5: Fallback database search if no matches from Whitepages extraction
        if len(database_matches) == 0:
            logger.info("No database matches from Whitepages data, trying fallback search")

            # Try search by city+state if provided
            if request.city and request.state:
                try:
                    logger.info(f"Fallback: searching database by name+city+state")
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
                            result["matched_by"] = "fallback:city_state"
                            database_matches.append(result)
                        logger.info(f"Fallback (city+state): found {len(results)} matches")
                except Exception as e:
                    logger.error(f"Fallback database search error (city+state): {str(e)}")

            # Try search by phone if provided and still no matches
            if len(database_matches) == 0 and request.phone:
                try:
                    logger.info(f"Fallback: searching database by name+phone")
                    result_json = search_engine.search_by_fields(
                        firstname=request.firstname,
                        lastname=request.lastname,
                        phone=request.phone,
                        limit=100
                    )
                    if result_json:
                        results = json.loads(result_json)
                        for result in results:
                            result["matched_by"] = "fallback:phone"
                            database_matches.append(result)
                        logger.info(f"Fallback (phone): found {len(results)} matches")
                except Exception as e:
                    logger.error(f"Fallback database search error (phone): {str(e)}")

            # Last resort: search by state only if provided and still no matches
            if len(database_matches) == 0 and request.state:
                try:
                    logger.info(f"Fallback: searching database by name+state only")
                    result_json = search_engine.search_by_fields(
                        firstname=request.firstname,
                        lastname=request.lastname,
                        state=request.state,
                        limit=100
                    )
                    if result_json:
                        results = json.loads(result_json)
                        for result in results:
                            result["matched_by"] = "fallback:state"
                            database_matches.append(result)
                        logger.info(f"Fallback (state): found {len(results)} matches")
                except Exception as e:
                    logger.error(f"Fallback database search error (state): {str(e)}")

            # Update metadata
            if len(database_matches) > 0:
                search_metadata["database_matches_count"] = len(database_matches)
                search_metadata["database_search_method"] = "fallback"
                logger.info(f"Fallback search found {len(database_matches)} total matches")

        # Step 4: Combine results - use first SearchBug result with all database matches
        combined_results = []

        if all_candidates and database_matches:
            # Use the SearchBug result with all database records
            searchbug_result = all_candidates[0]  # We only have one result from SearchBug
            for db_record in database_matches:
                merged = merge_results(searchbug_result, db_record)
                combined_results.append(merged)
        elif database_matches:
            # Only database matches, no SearchBug data
            combined_results = database_matches
        elif all_candidates:
            # Only SearchBug data, no SSN
            combined_results = all_candidates

        search_metadata["combined_results_count"] = len(combined_results)

        # Return response
        return SearchResponse(
            searchbug_data=searchbug_data,
            searchbug_candidates=all_candidates,
            database_matches=database_matches,
            combined_results=combined_results,
            search_metadata=search_metadata
        )

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
    logger.info(f"SEARCHBUG_CO_CODE configured: {bool(os.getenv('SEARCHBUG_CO_CODE'))}")
    logger.info(f"SEARCHBUG_PASSWORD configured: {bool(os.getenv('SEARCHBUG_PASSWORD'))}")
    logger.info(f"CORS Origins: {ALLOWED_ORIGINS}")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler"""
    logger.info("=== Lookup API Shutting Down ===")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
