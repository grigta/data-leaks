"""
ff.io (FixedFloat) API Client for crypto payment processing.

This module provides integration with ff.io (FixedFloat) for creating
crypto exchange orders and tracking cryptocurrency transactions.
"""

import os
import logging
import hmac
import hashlib
import json
from typing import Optional, Dict, Any
from decimal import Decimal
import httpx


# Configure logging
logger = logging.getLogger("ffio_client")


# ============================================
# Exception Classes
# ============================================

class FFIOError(Exception):
    """Base exception for ff.io API errors."""

    def __init__(self, message: str, status_code: int = None, code: str = None):
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(self.message)


class FFIOConnectionError(FFIOError):
    """Exception raised when connection to API fails."""
    pass


# ============================================
# ff.io API Client
# ============================================

class FFIOClient:
    """
    Async client for ff.io (FixedFloat) API integration.

    Provides methods for creating exchange orders and tracking transactions.
    Note: ff.io does not support webhooks - status must be checked via polling.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://ff.io",
        timeout: int = 30
    ):
        """
        Initialize ff.io client.

        Args:
            api_key: ff.io API key
            api_secret: ff.io API secret for HMAC signature
            base_url: Base URL for ff.io API
            timeout: Request timeout in seconds

        Raises:
            ValueError: If API key or secret is empty
        """
        if not api_key or api_key.strip() == "":
            raise ValueError("FFIO_API_KEY is required")
        if not api_secret or api_secret.strip() == "":
            raise ValueError("FFIO_API_SECRET is required")

        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None

        logger.info(f"FFIOClient initialized: base_url={self.base_url}")

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
    # Signature Generation
    # ============================================

    def _generate_signature(self, data: Dict[str, Any]) -> str:
        """
        Generate HMAC-SHA256 signature for ff.io API request.

        Args:
            data: Request data dictionary

        Returns:
            Hex-encoded HMAC-SHA256 signature
        """
        # Convert dict to JSON string (no spaces, sorted keys for consistency)
        json_string = json.dumps(data, separators=(',', ':'), sort_keys=True)

        # Generate HMAC-SHA256 signature
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            json_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return signature

    # ============================================
    # Core HTTP Method
    # ============================================

    async def _make_request(
        self,
        endpoint: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Make POST request to ff.io API with HMAC signature.

        All ff.io API requests are POST with JSON body and require signature.

        Args:
            endpoint: API endpoint path
            data: Request data dictionary

        Returns:
            Parsed JSON response

        Raises:
            FFIOError: On API errors
            FFIOConnectionError: On connection errors
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        # Build URL
        url = f"{self.base_url}{endpoint}"

        # Generate signature
        signature = self._generate_signature(data)

        # Build headers
        headers = {
            "X-API-KEY": self.api_key,
            "X-API-SIGN": signature,
            "Content-Type": "application/json"
        }

        # Mask sensitive data for logging
        masked_headers = {**headers}
        masked_headers["X-API-KEY"] = "***MASKED***"
        masked_headers["X-API-SIGN"] = "***MASKED***"

        logger.info(f"Making POST request to {url}")

        try:
            response = await self.client.post(
                url=url,
                json=data,
                headers=headers
            )

            # Parse response
            result = response.json()

            # Check for API errors in response
            if result.get("code") == 0:
                # Success
                logger.info(f"Request successful: POST {url}")
                return result
            else:
                # API error
                error_code = result.get("code")
                error_msg = result.get("msg", "Unknown error")
                error_message = f"ff.io API error {error_code}: {error_msg}"
                logger.error(error_message)
                raise FFIOError(
                    message=error_message,
                    status_code=response.status_code,
                    code=str(error_code)
                )

        except httpx.NetworkError as e:
            error_message = f"Network error: {str(e)}"
            logger.error(error_message)
            raise FFIOConnectionError(message=error_message)

        except httpx.TimeoutException as e:
            error_message = f"Request timeout: {str(e)}"
            logger.error(error_message)
            raise FFIOConnectionError(message=error_message)

        except Exception as e:
            if isinstance(e, (FFIOError, FFIOConnectionError)):
                raise
            error_message = f"Unexpected error: {str(e)}"
            logger.error(error_message)
            raise FFIOError(message=error_message)

    # ============================================
    # API Methods
    # ============================================

    async def get_currencies(self) -> Dict[str, Any]:
        """
        Get list of supported currencies.

        Returns:
            Dict with available currencies and their properties

        Raises:
            FFIOError: On API errors
        """
        logger.info("Fetching available currencies from ff.io")

        data = {}
        result = await self._make_request("/api/v2/ccies", data)

        logger.info("Successfully fetched currencies")
        return result

    async def get_price(
        self,
        from_ccy: str,
        to_ccy: str,
        amount: Decimal,
        direction: str = "from",
        type: str = "fixed"
    ) -> Dict[str, Any]:
        """
        Get exchange rate quote.

        Args:
            from_ccy: Source currency code
            to_ccy: Target currency code
            amount: Exchange amount
            direction: "from" or "to" (which amount is fixed)
            type: "fixed" or "float" exchange type

        Returns:
            Dict with exchange rate and amount information

        Raises:
            FFIOError: On API errors
        """
        logger.info(f"Getting price quote: {from_ccy} -> {to_ccy}, amount={amount}")

        data = {
            "fromCcy": from_ccy,
            "toCcy": to_ccy,
            "amount": str(amount),
            "direction": direction,
            "type": type
        }

        result = await self._make_request("/api/v2/price", data)

        logger.info(f"Price quote received: {result.get('data', {})}")
        return result

    async def create_order(
        self,
        from_ccy: str,
        to_ccy: str,
        amount: Decimal,
        direction: str,
        type: str,
        to_address: str,
        label: str
    ) -> Dict[str, Any]:
        """
        Create exchange order.

        Args:
            from_ccy: Source currency code (what user sends)
            to_ccy: Target currency code (what user receives - typically same as from for deposits)
            amount: Exchange amount
            direction: "from" or "to" (which amount is fixed)
            type: "fixed" or "float" exchange type
            to_address: Destination address for received funds
            label: Order label for identification

        Returns:
            Dict with fields:
                - order_id: ff.io order ID
                - deposit_address: Address where user should send funds
                - token: Token for checking order status
                - label: Order label

        Raises:
            FFIOError: On API errors
        """
        logger.info(
            f"Creating ff.io order: {from_ccy} -> {to_ccy}, "
            f"amount={amount}, label={label}"
        )

        data = {
            "fromCcy": from_ccy,
            "toCcy": to_ccy,
            "amount": str(amount),
            "direction": direction,
            "type": type,
            "toAddress": to_address,
            "tag": label  # ff.io uses 'tag' for custom labels
        }

        result = await self._make_request("/api/v2/create", data)

        # Extract response data
        order_data = result.get("data", {})
        order_id = order_data.get("id")
        deposit_address = order_data.get("from", {}).get("address")
        token = order_data.get("token")

        if not order_id or not deposit_address or not token:
            raise FFIOError("Invalid response from ff.io API: missing required fields")

        logger.info(
            f"ff.io order created: order_id={order_id}, "
            f"address={deposit_address[:10]}...{deposit_address[-4:]}"
        )

        return {
            "order_id": order_id,
            "deposit_address": deposit_address,
            "token": token,
            "label": label,
            "full_data": order_data  # Include full response for metadata
        }

    async def get_order_status(
        self,
        order_id: str,
        token: str
    ) -> Dict[str, Any]:
        """
        Get order status (for polling).

        Args:
            order_id: ff.io order ID
            token: Order token

        Returns:
            Dict with order status and details

        Raises:
            FFIOError: On API errors
        """
        logger.info(f"Checking order status: order_id={order_id}")

        data = {
            "id": order_id,
            "token": token
        }

        result = await self._make_request("/api/v2/order", data)

        order_data = result.get("data", {})
        status = order_data.get("status")

        logger.info(f"Order status: order_id={order_id}, status={status}")

        return result


# ============================================
# Crypto Configuration
# ============================================

# Mapping for cryptocurrency codes to ff.io format
CRYPTO_CONFIG = {
    "USDT_TRC20": {"code": "USDTTRC", "network": "TRC20"},
    "USDT_ERC20": {"code": "USDTETH", "network": "ERC20"},
    "USDT_BSC": {"code": "USDTBSC", "network": "BSC"},
    "ETH_MAINNET": {"code": "ETH", "network": "MAINNET"},
    "ETH": {"code": "ETH", "network": "MAINNET"},
    "BNB_MAINNET": {"code": "BNB", "network": "BSC"},
    "BNB": {"code": "BNB", "network": "BSC"},
    "BTC_MAINNET": {"code": "BTC", "network": "MAINNET"},
    "BTC": {"code": "BTC", "network": "MAINNET"},
    "LTC_MAINNET": {"code": "LTC", "network": "MAINNET"},
    "LTC": {"code": "LTC", "network": "MAINNET"},
    # Backward compatibility
    "USDT": {"code": "USDTTRC", "network": "TRC20"},
    "TRX": {"code": "TRX", "network": "TRC20"}
}


def get_ffio_currency_code(currency: str, network: Optional[str] = None) -> str:
    """
    Get ff.io currency code from our currency/network format.

    Args:
        currency: Currency code (e.g., "USDT", "BTC")
        network: Network name (e.g., "TRC20", "ERC20")

    Returns:
        ff.io currency code (e.g., "USDTTRC", "BTC")

    Raises:
        FFIOError: If currency/network combination is not supported
    """
    # Determine the lookup key
    if network:
        lookup_key = f"{currency.upper()}_{network.upper()}"
    else:
        lookup_key = currency.upper()

    # Get config
    config = CRYPTO_CONFIG.get(lookup_key)
    if not config:
        raise FFIOError(
            f"Unsupported currency/network combination for ff.io: {currency}/{network}"
        )

    return config["code"]


# ============================================
# Factory Function
# ============================================

# Global client instance for reuse
_client_instance: Optional[FFIOClient] = None


def get_ffio_client() -> FFIOClient:
    """
    Get or create ff.io client from environment variables.

    This function caches the client instance for reuse across requests.

    Returns:
        Configured FFIOClient instance

    Raises:
        ValueError: If required environment variables are missing

    Example:
        client = get_ffio_client()
        async with client:
            result = await client.create_order(
                from_ccy="USDTTRC",
                to_ccy="USDTTRC",
                amount=Decimal("50.00"),
                direction="from",
                type="fixed",
                to_address="TYourAddress...",
                label="tx_123"
            )
    """
    global _client_instance

    if _client_instance is None:
        api_key = os.getenv("FFIO_API_KEY", "")
        api_secret = os.getenv("FFIO_API_SECRET", "")
        base_url = os.getenv("FFIO_API_URL", "https://ff.io")

        if not api_key:
            raise ValueError(
                "FFIO_API_KEY environment variable is required. "
                "Please set it in your .env file."
            )
        if not api_secret:
            raise ValueError(
                "FFIO_API_SECRET environment variable is required. "
                "Please set it in your .env file."
            )

        _client_instance = FFIOClient(
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url
        )

    return _client_instance
