"""
Enrichment API FastAPI application.
"""
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from api.enrichment.routers import records_router
from api.common.security import get_api_key
from datetime import datetime
import logging
import os
from pathlib import Path


# Configure logging
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="SSN Enrichment API",
    version="1.0.0",
    description="Internal API for SSN data enrichment"
)

# Include routers with global API key dependency
app.include_router(
    records_router,
    tags=["Enrichment"],
    dependencies=[Depends(get_api_key)]
)


# Health check endpoint (no authentication required)
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    # Check if SQLite database exists
    sqlite_path = os.getenv('SQLITE_PATH', '/root/soft/data/ssn_database.db')
    db_exists = Path(sqlite_path).exists()

    return {
        "status": "healthy" if db_exists else "degraded",
        "timestamp": datetime.now().isoformat(),
        "service": "enrichment_api",
        "database_exists": db_exists
    }


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "timestamp": datetime.now().isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "timestamp": datetime.now().isoformat()
        }
    )


# Startup/shutdown events
@app.on_event("startup")
async def startup_event():
    """Startup event handler."""
    logger.info("Enrichment API starting up...")

    # Check if SQLite database exists
    sqlite_path = os.getenv('SQLITE_PATH', '/root/soft/data/ssn_database.db')
    if not Path(sqlite_path).exists():
        logger.warning(f"SQLite database not found at {sqlite_path}")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    logger.info("Enrichment API shutting down...")
