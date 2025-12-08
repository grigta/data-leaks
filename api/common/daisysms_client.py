"""
DaisySMS API Client for phone number rentals.

API Documentation: https://daisysms.com/docs/api
"""
import os
import logging
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import httpx

from api.common.daisysms_services import SERVICE_CODE_TO_NAME


logger = logging.getLogger("daisysms_client")


# ============================================
# Exception Classes
# ============================================

class DaisySMSError(Exception):
    """Base exception for DaisySMS API errors."""

    def __init__(self, message: str, error_code: str = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class DaisySMSNoNumbersError(DaisySMSError):
    """Exception raised when no numbers are available."""
    pass


class DaisySMSBalanceError(DaisySMSError):
    """Exception raised when balance is insufficient."""
    pass


class DaisySMSBadServiceError(DaisySMSError):
    """Exception raised when service code is invalid."""
    pass


class DaisySMSBadKeyError(DaisySMSError):
    """Exception raised when API key is invalid."""
    pass


# ============================================
# DaisySMS Client
# ============================================

class DaisySMSClient:
    """
    Async client for DaisySMS API.

    Usage:
        async with create_daisysms_client() as client:
            phone_id, phone_number = await client.get_number("mc")
            # ... use phone number ...
            await client.cancel_number(phone_id)
    """

    BASE_URL = "https://daisysms.com/stubs/handler_api.php"

    # Class-level cache for services
    _services_cache: List[Dict[str, Any]] = []
    _cache_time: Optional[datetime] = None
    CACHE_TTL = 3600  # 1 hour

    def __init__(
        self,
        api_key: str,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize DaisySMS API client.

        Args:
            api_key: DaisySMS API key
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts

        Raises:
            ValueError: If api_key is empty
        """
        if not api_key or api_key.strip() == "":
            raise ValueError("DAISYSMS_API_KEY is required")

        self.api_key = api_key.strip()
        self.timeout = timeout
        self.max_retries = max_retries
        self.client: Optional[httpx.AsyncClient] = None

        logger.info("DaisySMSClient initialized")

    async def open(self):
        """Initialize HTTP client."""
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True
            )
        return self

    async def close(self):
        """Close HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    # ============================================
    # Core API Methods
    # ============================================

    async def _make_request(self, params: Dict[str, Any]) -> str:
        """
        Make HTTP GET request to DaisySMS API.

        Args:
            params: Query parameters

        Returns:
            Response text

        Raises:
            DaisySMSError: On API errors
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        # Add API key to params
        request_params = {
            "api_key": self.api_key,
            **params
        }

        # Mask API key for logging
        masked_params = {**request_params}
        masked_params["api_key"] = "***"
        logger.info(f"Making request to DaisySMS: {masked_params}")

        # Retry logic
        for attempt in range(self.max_retries):
            try:
                response = await self.client.get(self.BASE_URL, params=request_params)
                response_text = response.text.strip()

                logger.debug(f"DaisySMS response: {response_text}")

                # Check for common errors
                if response_text == "BAD_KEY":
                    raise DaisySMSBadKeyError("Invalid API key", "BAD_KEY")

                return response_text

            except httpx.NetworkError as e:
                backoff_delay = 2 ** attempt
                logger.warning(
                    f"Network error: {str(e)}. "
                    f"Retrying in {backoff_delay}s. Attempt {attempt + 1}/{self.max_retries}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(backoff_delay)
                    continue
                else:
                    raise DaisySMSError(
                        message=f"Network error after {self.max_retries} attempts: {str(e)}"
                    )

            except httpx.TimeoutException as e:
                logger.error(f"Request timeout: {str(e)}")
                raise DaisySMSError(message=f"Request timeout: {str(e)}")

        raise DaisySMSError(message="Max retries exceeded")

    async def get_balance(self) -> float:
        """
        Get current account balance.

        Returns:
            Balance in dollars

        Raises:
            DaisySMSError: On API errors
        """
        response = await self._make_request({"action": "getBalance"})

        # Response format: ACCESS_BALANCE:50.30
        if response.startswith("ACCESS_BALANCE:"):
            balance_str = response.split(":")[1]
            return float(balance_str)

        raise DaisySMSError(f"Unexpected balance response: {response}")

    async def get_number(
        self,
        service_code: str,
        country: str = "1",
        auto_renew: bool = False
    ) -> Tuple[str, str]:
        """
        Get a phone number for the specified service.

        Args:
            service_code: DaisySMS service code (e.g., "mc" for Mail.com)
            country: Country code (default "1" for USA)
            auto_renew: Enable auto-renewal for long-term rentals

        Returns:
            Tuple of (phone_id, phone_number)

        Raises:
            DaisySMSNoNumbersError: If no numbers available
            DaisySMSBalanceError: If insufficient balance
            DaisySMSBadServiceError: If service code is invalid
            DaisySMSError: For other errors
        """
        params = {
            "action": "getNumber",
            "service": service_code,
            "country": country
        }

        if auto_renew:
            params["auto_renew"] = "1"

        logger.info(f"Requesting number for service: {service_code}")

        response = await self._make_request(params)

        # Parse response
        if response.startswith("ACCESS_NUMBER:"):
            # Format: ACCESS_NUMBER:ID:PHONE_NUMBER
            parts = response.split(":")
            if len(parts) >= 3:
                phone_id = parts[1]
                phone_number = parts[2]
                logger.info(f"Got number: {phone_number} (ID: {phone_id})")
                return phone_id, phone_number

        # Handle error responses
        if response == "NO_NUMBERS":
            raise DaisySMSNoNumbersError(
                "No numbers available for this service",
                "NO_NUMBERS"
            )
        elif response == "NO_BALANCE":
            raise DaisySMSBalanceError(
                "Insufficient balance in DaisySMS account",
                "NO_BALANCE"
            )
        elif response == "BAD_SERVICE":
            raise DaisySMSBadServiceError(
                f"Invalid service code: {service_code}",
                "BAD_SERVICE"
            )
        elif response == "MAX_RENTALS":
            raise DaisySMSError(
                "Maximum active rentals limit reached (20)",
                "MAX_RENTALS"
            )
        else:
            raise DaisySMSError(f"Unknown response: {response}", response)

    async def get_status(self, phone_id: str) -> Tuple[str, Optional[str]]:
        """
        Get SMS status for a phone number rental.

        Args:
            phone_id: Phone rental ID

        Returns:
            Tuple of (status, sms_code or None)
            Status can be: "STATUS_WAIT_CODE", "STATUS_OK", "STATUS_CANCEL"

        Raises:
            DaisySMSError: On API errors
        """
        response = await self._make_request({
            "action": "getStatus",
            "id": phone_id
        })

        if response.startswith("STATUS_OK:"):
            # SMS received, format: STATUS_OK:123456
            code = response.split(":")[1]
            return "STATUS_OK", code
        elif response == "STATUS_WAIT_CODE":
            return "STATUS_WAIT_CODE", None
        elif response == "STATUS_CANCEL":
            return "STATUS_CANCEL", None
        else:
            return response, None

    async def set_status(self, phone_id: str, status: int) -> bool:
        """
        Set status for a phone number rental.

        Status codes:
            6 - Complete (finish rental, no refund)
            8 - Cancel (cancel and refund)

        Args:
            phone_id: Phone rental ID
            status: Status code

        Returns:
            True if successful
        """
        logger.info(f"Setting status {status} for phone ID: {phone_id}")

        response = await self._make_request({
            "action": "setStatus",
            "id": phone_id,
            "status": str(status)
        })

        if response in ("ACCESS_CANCEL", "ACCESS_ACTIVATION"):
            logger.info(f"Status set successfully: {response}")
            return True

        logger.warning(f"Unexpected status response: {response}")
        return False

    async def cancel_number(self, phone_id: str) -> bool:
        """
        Cancel phone number rental and get refund.

        Args:
            phone_id: Phone rental ID

        Returns:
            True if successful
        """
        return await self.set_status(phone_id, 8)

    async def finish_number(self, phone_id: str) -> bool:
        """
        Finish phone number rental (no refund).

        Args:
            phone_id: Phone rental ID

        Returns:
            True if successful
        """
        return await self.set_status(phone_id, 6)

    async def set_auto_renew(self, phone_id: str, enabled: bool) -> bool:
        """
        Enable or disable auto-renewal for a phone number rental.

        Args:
            phone_id: Phone rental ID
            enabled: Whether to enable auto-renewal

        Returns:
            True if successful
        """
        logger.info(f"Setting auto_renew={enabled} for phone ID: {phone_id}")

        response = await self._make_request({
            "action": "setAutoRenew",
            "id": phone_id,
            "value": "true" if enabled else "false"
        })

        if response == "ACCESS_AUTORENEW":
            logger.info(f"Auto-renew set successfully")
            return True

        logger.warning(f"Unexpected auto-renew response: {response}")
        return False

    async def get_extra_activation(self, phone_id: str, service_code: str) -> bool:
        """
        Get extra activation for an existing phone number rental.
        This extends the rental time.

        Args:
            phone_id: Phone rental ID
            service_code: Service code

        Returns:
            True if successful

        Raises:
            DaisySMSError: On API errors
        """
        logger.info(f"Getting extra activation for phone ID: {phone_id}")

        response = await self._make_request({
            "action": "getExtraActivation",
            "id": phone_id,
            "service": service_code
        })

        if response.startswith("ACCESS_EXTRA_ACTIVATION"):
            logger.info("Extra activation successful")
            return True
        elif response == "NO_BALANCE":
            raise DaisySMSBalanceError(
                "Insufficient balance for extra activation",
                "NO_BALANCE"
            )
        elif response == "NO_ACTIVATION":
            raise DaisySMSError(
                "Cannot get extra activation - rental may have expired",
                "NO_ACTIVATION"
            )
        else:
            raise DaisySMSError(f"Extra activation failed: {response}", response)

    async def get_services(self, country: str = "1") -> List[Dict[str, Any]]:
        """
        Get list of all available services with prices.

        Args:
            country: Country code (default "1" for USA)

        Returns:
            List of service dicts with code, name, price
        """
        # Check cache
        if self._services_cache and self._cache_time:
            cache_age = (datetime.now() - self._cache_time).total_seconds()
            if cache_age < self.CACHE_TTL:
                logger.debug("Returning cached services list")
                return self._services_cache

        logger.info(f"Fetching services list for country: {country}")

        response = await self._make_request({
            "action": "getPrices",
            "country": country
        })

        # Parse response (format: service_code:price,service_code:price,...)
        # API may include metadata fields like "count:N" which should be skipped
        METADATA_FIELDS = {"count", "total", "status", "error", "message"}

        services = []
        skipped_fields = []

        for item in response.split(","):
            item = item.strip()
            if ":" in item:
                parts = item.split(":")
                if len(parts) >= 2:
                    code = parts[0].strip().lower()

                    # Skip metadata/service fields
                    if code in METADATA_FIELDS:
                        skipped_fields.append(code)
                        continue

                    try:
                        price = float(parts[1].strip())
                    except ValueError:
                        continue

                    services.append({
                        "code": code,
                        "name": SERVICE_CODE_TO_NAME.get(code, code.title()),
                        "price": price
                    })

        if skipped_fields:
            logger.debug(f"Skipped metadata fields: {skipped_fields}")

        # Sort by name
        services.sort(key=lambda x: x["name"].lower())

        # Update cache
        DaisySMSClient._services_cache = services
        DaisySMSClient._cache_time = datetime.now()

        logger.info(f"Loaded {len(services)} services")
        return services


# ============================================
# Factory Function
# ============================================

def create_daisysms_client() -> DaisySMSClient:
    """
    Create DaisySMS client from environment variables.

    Returns:
        Configured DaisySMSClient instance

    Raises:
        ValueError: If DAISYSMS_API_KEY is not set
    """
    api_key = os.getenv("DAISYSMS_API_KEY", "")

    if not api_key:
        raise ValueError(
            "DAISYSMS_API_KEY environment variable is required. "
            "Please set it in your .env file."
        )

    return DaisySMSClient(api_key=api_key)
