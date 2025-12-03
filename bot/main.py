"""Main bot entry point."""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher

from config import BotConfig
from handlers import register_handlers
from middlewares import setup_middlewares
from websocket_client import WebSocketClient
from api.common.database import async_engine
from api.common.logging_config import setup_logging, get_logger
from api.common.security_logger import SecurityEventLogger

# Bootstrap logger for use before structured logging is configured
# This is used only in the __main__ block for early errors
_bootstrap_logger = logging.getLogger("telegram_bot.bootstrap")


async def main():
    """Main bot function."""
    # Setup structured logging
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    json_enabled = os.getenv('LOG_JSON_ENABLED', 'true').lower() in ('true', '1', 'yes')
    setup_logging(service_name="telegram_bot", log_level=log_level, json_enabled=json_enabled)
    logger = get_logger(__name__)
    security_logger = SecurityEventLogger("telegram_bot")

    bot = None
    ws_client = None
    ws_task = None

    try:
        # Initialize configuration
        config = BotConfig()
        config.validate()
        logger.info("Configuration loaded successfully")

        # Create bot and dispatcher
        bot = Bot(token=config.bot_token)
        dp = Dispatcher()

        # Log bot info
        bot_info = await bot.get_me()
        logger.info(f"Bot started: @{bot_info.username} ({bot_info.id})")
        await security_logger.log_service_startup(
            version="1.0.0",
            config={
                "bot_id": bot_info.id,
                "username": bot_info.username,
                "log_level": log_level,
                "json_logging": json_enabled
            }
        )

        # Register middlewares
        setup_middlewares(dp)

        # Register handlers
        register_handlers(dp)

        # Initialize WebSocket client
        ws_client = WebSocketClient(config, bot)
        logger.info("WebSocket client initialized")

        # Start WebSocket client in background
        ws_task = asyncio.create_task(ws_client.start())
        logger.info("WebSocket client started in background")

        # Start polling
        logger.info("Bot started - listening for messages...")
        try:
            await dp.start_polling(bot, allowed_updates=['message', 'callback_query'])
        except asyncio.CancelledError:
            logger.info("Polling cancelled")

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)

        # Log fatal error for alerting
        try:
            await security_logger.log_server_error(
                path="telegram_bot_main",
                error_type=type(e).__name__,
                client_ip="bot"
            )
        except Exception as alert_err:
            logger.warning(f"Failed to log server error alert: {alert_err}")

        # Log database errors specifically
        error_str = str(e).lower()
        error_type = type(e).__name__.lower()
        if any(db_indicator in error_str or db_indicator in error_type
               for db_indicator in ['database', 'connection', 'pool', 'sqlalchemy', 'asyncpg', 'postgres']):
            await security_logger.log_db_connection_failure(e)
        raise

    finally:
        # Graceful shutdown
        await security_logger.log_service_shutdown("graceful")
        logger.info("Bot stopping...")

        # Stop WebSocket client
        if ws_client:
            logger.info("Stopping WebSocket client...")
            try:
                await ws_client.stop()
                logger.info("WebSocket client stopped")
            except Exception as e:
                logger.error(f"Error stopping WebSocket client: {e}")

        # Cancel WebSocket task
        if ws_task:
            ws_task.cancel()
            try:
                await ws_task
            except asyncio.CancelledError:
                logger.info("WebSocket task cancelled")
            except Exception as e:
                logger.error(f"Error cancelling WebSocket task: {e}")

        # Close bot session
        if bot:
            try:
                await bot.session.close()
            except Exception as e:
                logger.error(f"Error closing bot session: {e}")

        # Dispose database engine
        try:
            await async_engine.dispose()
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error disposing database engine: {e}")

        logger.info("Bot stopped")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _bootstrap_logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        _bootstrap_logger.error(f"Fatal error during startup: {e}", exc_info=True)
