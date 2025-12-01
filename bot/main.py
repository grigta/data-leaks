"""Main bot entry point."""
import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import BotConfig
from handlers import register_handlers
from middlewares import setup_middlewares
from websocket_client import WebSocketClient
from api.common.database import async_engine


logger = logging.getLogger(__name__)


async def main():
    """Main bot function."""
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
        raise

    finally:
        # Graceful shutdown
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
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
