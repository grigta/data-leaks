"""Bot configuration module."""
import os
import logging
from typing import Optional


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BotConfig:
    """Bot configuration class."""

    def __init__(self):
        """Initialize bot configuration from environment variables."""
        self.bot_token: Optional[str] = os.getenv('TELEGRAM_BOT_TOKEN')
        self.log_level: str = os.getenv('LOG_LEVEL', 'INFO')

        # WebSocket configuration
        self.public_api_url: str = os.getenv('PUBLIC_API_URL', 'http://public_api:8000')
        self.bot_api_key: Optional[str] = os.getenv('BOT_API_KEY')
        self.ws_reconnect_delay: int = int(os.getenv('WS_RECONNECT_DELAY', '5'))
        self.ws_max_reconnect_delay: int = int(os.getenv('WS_MAX_RECONNECT_DELAY', '300'))
        self.ws_heartbeat_interval: int = int(os.getenv('WS_HEARTBEAT_INTERVAL', '30'))

        # Apply log level
        logging.getLogger().setLevel(getattr(logging, self.log_level.upper()))

    @property
    def ws_url(self) -> str:
        """Get WebSocket URL for bot connection.

        Returns:
            WebSocket URL (authentication via header).
        """
        # Convert http:// to ws:// or https:// to wss://
        ws_scheme = 'wss' if self.public_api_url.startswith('https') else 'ws'
        base_url = self.public_api_url.replace('http://', '').replace('https://', '')
        return f"{ws_scheme}://{base_url}/ws/bot"

    def validate(self) -> None:
        """Validate required configuration parameters.

        Raises:
            ValueError: If required parameters are missing.
        """
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

        if not self.bot_api_key:
            raise ValueError("BOT_API_KEY environment variable is required")

        logger.info("Configuration validated successfully")
        logger.info(f"Public API URL: {self.public_api_url}")
        logger.info(f"WebSocket reconnect delay: {self.ws_reconnect_delay}s")
        logger.info(f"WebSocket max reconnect delay: {self.ws_max_reconnect_delay}s")
