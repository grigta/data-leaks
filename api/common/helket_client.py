"""
Helket API Client for crypto payment processing.

This module provides integration with Helket API (heleket.com) for creating
crypto invoices and tracking cryptocurrency transactions.
"""

import os
import logging
import hmac
import hashlib
from typing import Optional, Dict, Any
from decimal import Decimal
import httpx


# Configure logging
logger = logging.getLogger("helket_client")


# ============================================
# Exception Classes
# ============================================

class HelketError(Exception):
    """Base exception for Helket API errors."""

    def __init__(self, message: str, status_code: int = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class HelketConnectionError(HelketError):
    """Exception raised when connection to API fails."""
    pass


# ============================================
# Helket API Client
# ============================================

class HelketClient:
    """
    Async client for Helket API integration.

    Provides methods for creating invoices and tracking transactions.
    """

    def __init__(
        self,
        api_key: str,
        merchant_uuid: str,
        webhook_secret: str,
        base_url: str = "https://api.heleket.com",
        timeout: int = 30
    ):
        """
        Initialize Helket client.

        Args:
            api_key: Helket API key
            merchant_uuid: Helket merchant UUID
            webhook_secret: Secret for webhook signature verification
            base_url: Base URL for Helket API
            timeout: Request timeout in seconds

        Raises:
            ValueError: If API key or merchant UUID is empty
        """
        if not api_key or api_key.strip() == "":
            raise ValueError("HELKET_API_KEY is required")
        if not merchant_uuid or merchant_uuid.strip() == "":
            raise ValueError("HELKET_MERCHANT_UUID is required")

        self.api_key = api_key.strip()
        self.merchant_uuid = merchant_uuid.strip()
        self.webhook_secret = webhook_secret.strip() if webhook_secret else ""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None

        logger.info(f"HelketClient initialized: base_url={self.base_url}")

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
        Make HTTP request to Helket API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request data (for POST body)
            params: Query parameters (for GET)

        Returns:
            Parsed JSON response

        Raises:
            HelketError: On API errors
            HelketConnectionError: On connection errors
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        # Build URL
        url = f"{self.base_url}{endpoint}"

        # Build headers
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Mask sensitive data for logging
        masked_headers = {**headers}
        if "Authorization" in masked_headers:
            masked_headers["Authorization"] = "Bearer ***MASKED***"
        masked_data = {**data} if data else {}

        logger.info(f"Making {method} request to {url} with params={params}")

        try:
            response = await self.client.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=headers
            )

            # Handle errors
            if response.status_code >= 400:
                error_message = f"API error {response.status_code}: {response.text}"
                logger.error(error_message)
                raise HelketError(
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
            raise HelketConnectionError(message=error_message)

        except httpx.TimeoutException as e:
            error_message = f"Request timeout: {str(e)}"
            logger.error(error_message)
            raise HelketConnectionError(message=error_message)

        except Exception as e:
            if isinstance(e, (HelketError, HelketConnectionError)):
                raise
            error_message = f"Unexpected error: {str(e)}"
            logger.error(error_message)
            raise HelketError(message=error_message)

    # ============================================
    # API Methods
    # ============================================

    async def create_invoice(
        self,
        currency: str,
        amount: Decimal,
        label: str,
        callback_url: str,
        network: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a crypto invoice using Helket API.

        Args:
            currency: Cryptocurrency code (e.g., "USDT", "BTC", "ETH")
            amount: Payment amount
            label: Transaction label (used to identify transaction in webhook)
            callback_url: Webhook callback URL
            network: Blockchain network (e.g., "TRC20", "ERC20", "MAINNET")

        Returns:
            Dict with fields:
                - address: Payment address
                - qr_code: QR code URL (optional)
                - invoice_id: Helket invoice ID
                - label: Transaction label

        Raises:
            HelketError: On API errors
        """
        logger.info(
            f"Creating Helket invoice: currency={currency}, network={network}, "
            f"amount={amount}, label={label}"
        )

        # Comprehensive mapping for cryptocurrencies and networks
        CRYPTO_CONFIG = {
            "USDT_TRC20": {"currency": "USDT", "network": "TRC20"},
            "USDT_ERC20": {"currency": "USDT", "network": "ERC20"},
            "USDT_BSC": {"currency": "USDT", "network": "BSC"},
            "ETH_MAINNET": {"currency": "ETH", "network": "MAINNET"},
            "ETH": {"currency": "ETH", "network": "MAINNET"},
            "BNB_MAINNET": {"currency": "BNB", "network": "BSC"},
            "BNB": {"currency": "BNB", "network": "BSC"},
            "BTC_MAINNET": {"currency": "BTC", "network": "MAINNET"},
            "BTC": {"currency": "BTC", "network": "MAINNET"},
            "LTC_MAINNET": {"currency": "LTC", "network": "MAINNET"},
            "LTC": {"currency": "LTC", "network": "MAINNET"},
            # Backward compatibility
            "USDT": {"currency": "USDT", "network": "TRC20"},
            "TRX": {"currency": "TRX", "network": "TRC20"}
        }

        # Determine the lookup key
        if network:
            lookup_key = f"{currency.upper()}_{network.upper()}"
        else:
            lookup_key = currency.upper()

        # Get crypto configuration
        config = CRYPTO_CONFIG.get(lookup_key)
        if not config:
            raise HelketError(
                f"Unsupported currency/network combination: {currency}/{network}"
            )

        crypto_currency = config["currency"]
        crypto_network = config["network"]

        # Build request payload
        payload = {
            "merchant_uuid": self.merchant_uuid,
            "currency": crypto_currency,
            "network": crypto_network,
            "amount": str(amount),
            "label": label,
            "callback_url": callback_url
        }

        # Create invoice
        endpoint = "/v1/invoices"
        result = await self._make_request("POST", endpoint, data=payload)

        # Extract response fields
        invoice_id = result.get("invoice_id") or result.get("id")
        address = result.get("address") or result.get("payment_address")
        qr_code = result.get("qr_code") or result.get("qr")

        if not address or not invoice_id:
            raise HelketError("Invalid response from Helket API: missing address or invoice_id")

        logger.info(
            f"Helket invoice created: {address[:10]}...{address[-4:]} "
            f"invoice_id={invoice_id}"
        )

        return {
            "address": address,
            "qr_code": qr_code,
            "invoice_id": invoice_id,
            "label": label
        }

    @staticmethod
    def verify_webhook_signature(payload: str, signature: str, secret: str) -> bool:
        """
        Verify Helket webhook signature.

        Args:
            payload: Raw webhook payload (JSON string)
            signature: Signature from webhook header (X-Signature or similar)
            secret: Webhook secret

        Returns:
            True if signature is valid, False otherwise
        """
        if not secret or not signature:
            logger.warning("Cannot verify webhook signature: missing secret or signature")
            return False

        try:
            # Helket typically uses HMAC-SHA256 for webhook signatures
            expected_signature = hmac.new(
                secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            is_valid = hmac.compare_digest(expected_signature, signature)

            if is_valid:
                logger.info("Webhook signature verified successfully")
            else:
                logger.warning("Webhook signature verification failed")

            return is_valid

        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False


# ============================================
# Factory Function
# ============================================

# Global client instance for reuse
_client_instance: Optional[HelketClient] = None


def get_helket_client() -> HelketClient:
    """
    Get or create Helket client from environment variables.

    This function caches the client instance for reuse across requests.

    Returns:
        Configured HelketClient instance

    Raises:
        ValueError: If required environment variables are missing

    Example:
        client = get_helket_client()
        async with client:
            result = await client.create_invoice(
                currency="USDT",
                amount=Decimal("50.00"),
                label="tx_123",
                callback_url="https://example.com/ipn/helket"
            )
    """
    global _client_instance

    if _client_instance is None:
        api_key = os.getenv("HELKET_API_KEY", "")
        merchant_uuid = os.getenv("HELKET_MERCHANT_UUID", "")
        webhook_secret = os.getenv("HELKET_WEBHOOK_SECRET", "")
        base_url = os.getenv("HELKET_API_URL", "https://api.heleket.com")

        if not api_key:
            raise ValueError(
                "HELKET_API_KEY environment variable is required. "
                "Please set it in your .env file."
            )
        if not merchant_uuid:
            raise ValueError(
                "HELKET_MERCHANT_UUID environment variable is required. "
                "Please set it in your .env file."
            )

        _client_instance = HelketClient(
            api_key=api_key,
            merchant_uuid=merchant_uuid,
            webhook_secret=webhook_secret,
            base_url=base_url
        )

    return _client_instance
