"""
CryptoCurrencyAPI Client for crypto payment processing.

This module provides integration with cryptocurrencyapi.net for creating
payment addresses and tracking cryptocurrency transactions.
"""

import os
import logging
from typing import Optional, Dict, Any
from decimal import Decimal
import httpx


# Configure logging
logger = logging.getLogger("cryptocurrencyapi_client")


# ============================================
# Exception Classes
# ============================================

class CryptoCurrencyAPIError(Exception):
    """Base exception for CryptoCurrencyAPI errors."""

    def __init__(self, message: str, status_code: int = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class CryptoCurrencyAPIConnectionError(CryptoCurrencyAPIError):
    """Exception raised when connection to API fails."""
    pass


# ============================================
# CryptoCurrencyAPI Client
# ============================================

class CryptoCurrencyAPIClient:
    """
    Async client for CryptoCurrencyAPI.net integration.

    Provides methods for creating payment addresses and tracking transactions.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://new.cryptocurrencyapi.net",
        timeout: int = 30
    ):
        """
        Initialize CryptoCurrencyAPI client.

        Args:
            api_key: CryptoCurrencyAPI API key
            base_url: Base URL for CryptoCurrencyAPI
            timeout: Request timeout in seconds

        Raises:
            ValueError: If API key is empty or invalid
        """
        if not api_key or api_key.strip() == "":
            raise ValueError("CRYPTOCURRENCYAPI_KEY is required")

        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None

        logger.info(f"CryptoCurrencyAPIClient initialized: base_url={self.base_url}")

    async def open(self):
        """
        Explicitly initialize the HTTP client.

        Use this method for manual client lifecycle management.
        """
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True
            )
        return self

    async def close(self):
        """
        Explicitly close the HTTP client.

        Use this method for manual client lifecycle management.
        """
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
    # Core HTTP Method
    # ============================================

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request to CryptoCurrencyAPI.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request data (for POST body)
            params: Query parameters (for GET)

        Returns:
            Parsed JSON response

        Raises:
            CryptoCurrencyAPIError: On API errors
            CryptoCurrencyAPIConnectionError: On connection errors
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        # Build URL
        url = f"{self.base_url}{endpoint}"

        # Mask sensitive data for logging
        masked_params = {**params} if params else {}
        if "key" in masked_params:
            masked_params["key"] = "***MASKED***"
        masked_data = {**data} if data else {}
        if "key" in masked_data:
            masked_data["key"] = "***MASKED***"

        logger.info(f"Making {method} request to {url} with params={masked_params} data={masked_data}")

        try:
            response = await self.client.request(
                method=method,
                url=url,
                data=data,
                params=params
            )

            # Handle errors
            if response.status_code >= 400:
                error_message = f"API error {response.status_code}: {response.text}"
                logger.error(error_message)
                raise CryptoCurrencyAPIError(
                    message=error_message,
                    status_code=response.status_code
                )

            # Success
            response.raise_for_status()
            result = response.json()
            logger.info(f"Request successful: {method} {url}")
            return result

        except httpx.NetworkError as e:
            error_message = f"Network error: {str(e)}"
            logger.error(error_message)
            raise CryptoCurrencyAPIConnectionError(message=error_message)

        except httpx.TimeoutException as e:
            error_message = f"Request timeout: {str(e)}"
            logger.error(error_message)
            raise CryptoCurrencyAPIConnectionError(message=error_message)

        except Exception as e:
            if isinstance(e, (CryptoCurrencyAPIError, CryptoCurrencyAPIConnectionError)):
                raise
            error_message = f"Unexpected error: {str(e)}"
            logger.error(error_message)
            raise CryptoCurrencyAPIError(message=error_message)

    # ============================================
    # API Methods
    # ============================================

    async def create_payment_address(
        self,
        currency: str,
        amount: Decimal,
        label: str,
        status_url: str,
        network: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a payment address using the 'give' method.

        Args:
            currency: Cryptocurrency code (e.g., "USDT", "BTC", "LTC")
            amount: Payment amount
            label: Transaction label (used to identify transaction in IPN)
            status_url: IPN callback URL
            network: Blockchain network (e.g., "TRC20", "ERC20", "BSC", "MAINNET")

        Returns:
            Dict with fields:
                - address: Payment address
                - qr_code: QR code URL (optional)
                - label: Transaction label

        Raises:
            CryptoCurrencyAPIError: On API errors
        """
        logger.info(
            f"Creating payment address: currency={currency}, network={network}, "
            f"amount={amount}, label={label}"
        )

        # Comprehensive mapping for cryptocurrencies and networks
        CRYPTO_CONFIG = {
            "USDT_TRC20": {"blockchain": "trx", "token": "USDT"},
            "USDT_ERC20": {"blockchain": "eth", "token": "USDT"},
            "USDT_BSC": {"blockchain": "bsc", "token": "USDT"},
            "ETH_MAINNET": {"blockchain": "eth", "token": None},
            "ETH": {"blockchain": "eth", "token": None},
            "BNB_MAINNET": {"blockchain": "bsc", "token": None},
            "BNB": {"blockchain": "bsc", "token": None},
            "BTC_MAINNET": {"blockchain": "btc", "token": None},
            "BTC": {"blockchain": "btc", "token": None},
            "LTC_MAINNET": {"blockchain": "ltc", "token": None},
            "LTC": {"blockchain": "ltc", "token": None},
            # Backward compatibility
            "USDT": {"blockchain": "trx", "token": "USDT"},
            "TRX": {"blockchain": "trx", "token": None},
            "DOGE": {"blockchain": "doge", "token": None},
            "BCH": {"blockchain": "bch", "token": None},
            "DASH": {"blockchain": "dash", "token": None}
        }

        # Determine the lookup key
        if network:
            lookup_key = f"{currency.upper()}_{network.upper()}"
        else:
            lookup_key = currency.upper()

        # Get blockchain configuration
        config = CRYPTO_CONFIG.get(lookup_key)
        if not config:
            raise CryptoCurrencyAPIError(
                f"Unsupported currency/network combination: {currency}/{network}"
            )

        blockchain = config["blockchain"]
        token = config.get("token")

        # Build query parameters
        params = {
            "key": self.api_key,
            "label": label,
            "statusURL": status_url,
            "qr": 1,  # Request QR code
            "amount": str(amount)  # Convert Decimal to string
        }

        # Add token parameter for ERC20/TRC20/BSC tokens (USDT)
        if token:
            params["currency"] = token

        # Build endpoint
        endpoint = f"/api/{blockchain}/.give"

        result = await self._make_request("GET", endpoint, params=params)

        # Extract response fields from nested result
        result_data = result.get("result", {})
        address = result_data.get("address")
        # API returns QR code in uppercase "QR" field
        qr_code = result_data.get("QR") or result_data.get("qr")
        returned_label = label

        if not address:
            raise CryptoCurrencyAPIError("No address returned from API")

        logger.info(
            f"Payment address created: {address[:10]}...{address[-4:]} "
            f"for {currency} on {network or 'default'} network"
        )

        return {
            "address": address,
            "qr_code": qr_code,
            "label": returned_label
        }

    async def track_address(
        self,
        address: str,
        label: str,
        status_url: str
    ) -> Dict[str, Any]:
        """
        Track an existing address using the 'track' method.

        Args:
            address: Cryptocurrency address to track
            label: Transaction label
            status_url: IPN callback URL

        Returns:
            Dict with tracking confirmation

        Raises:
            CryptoCurrencyAPIError: On API errors
        """
        logger.info(f"Tracking address: {address[:10]}...{address[-4:]}, label={label}")

        data = {
            "key": self.api_key,
            "address": address,
            "label": label,
            "statusURL": status_url
        }

        result = await self._make_request("POST", "/api/track", data=data)

        logger.info(f"Address tracking started for {label}")

        return result


# ============================================
# Factory Function
# ============================================

# Global client instance for reuse
_client_instance: Optional[CryptoCurrencyAPIClient] = None


def get_cryptocurrencyapi_client() -> CryptoCurrencyAPIClient:
    """
    Get or create CryptoCurrencyAPI client from environment variables.

    This function caches the client instance for reuse across requests.

    Returns:
        Configured CryptoCurrencyAPIClient instance

    Raises:
        ValueError: If required environment variables are missing

    Example:
        client = get_cryptocurrencyapi_client()
        async with client:
            result = await client.create_payment_address(
                currency="USDT",
                amount=Decimal("50.00"),
                label="tx_123",
                status_url="https://example.com/ipn"
            )
    """
    global _client_instance

    if _client_instance is None:
        api_key = os.getenv("CRYPTOCURRENCYAPI_KEY", "")
        base_url = os.getenv("CRYPTOCURRENCYAPI_URL", "https://new.cryptocurrencyapi.net")

        if not api_key:
            raise ValueError(
                "CRYPTOCURRENCYAPI_KEY environment variable is required. "
                "Please set it in your .env file."
            )

        _client_instance = CryptoCurrencyAPIClient(
            api_key=api_key,
            base_url=base_url
        )

    return _client_instance
