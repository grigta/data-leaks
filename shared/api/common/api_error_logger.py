"""
Helper for logging API errors (SearchBug, WhitePages) to PostgreSQL.
"""
import logging
from typing import Optional, Dict, Any
from api.common.database import async_session_maker
from api.common.models_postgres import ApiErrorLog

logger = logging.getLogger("api_error_logger")


async def log_api_error(
    api_name: str,
    method: str,
    error: Exception,
    status_code: Optional[int] = None,
    request_params: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log an API error to the database (fire-and-forget).

    Args:
        api_name: API identifier ('searchbug' or 'whitepages')
        method: Method name that failed (e.g. '_make_request')
        error: The exception that was raised
        status_code: HTTP status code if available
        request_params: Request parameters (sensitive data should be masked)
        request_params: Request parameters (sensitive data should be masked)
    """
    try:
        # Mask sensitive fields
        safe_params = None
        if request_params:
            safe_params = {k: v for k, v in request_params.items()}
            for key in ('PASS', 'password', 'api_key', 'X-Api-Key', 'CO_CODE'):
                if key in safe_params:
                    safe_params[key] = '***'

        error_log = ApiErrorLog(
            api_name=api_name,
            method=method,
            error_type=type(error).__name__,
            error_message=str(error)[:2000],
            status_code=status_code,
            request_params=safe_params,
        )

        async with async_session_maker() as session:
            session.add(error_log)
            await session.commit()

    except Exception as e:
        # Never let logging crash the main flow
        logger.error(f"Failed to log API error: {e}")
