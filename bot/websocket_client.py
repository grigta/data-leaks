"""WebSocket client for receiving ticket notifications from Public API."""
import asyncio
import logging
import json
import html
import random
from decimal import Decimal
from typing import Optional
from uuid import UUID

import aiohttp
from aiogram import Bot

from config import BotConfig
from db_operations import get_db_session, get_user_telegram_chats, get_message_reference
from utils.formatters import format_order_header, format_manual_ticket_completed
from bot.config.pricing import MANUAL_SSN_PRICE
from api.common.security_logger import SecurityEventLogger


logger = logging.getLogger(__name__)
# Security logger for WebSocket failure alerts
_ws_security_logger = SecurityEventLogger("telegram_bot")


class WebSocketClient:
    """WebSocket client for connecting to Public API and receiving ticket events."""

    def __init__(self, config: BotConfig, bot: Bot):
        """Initialize WebSocket client.

        Args:
            config: Bot configuration.
            bot: Telegram bot instance.
        """
        self.config = config
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.reconnect_delay: int = config.ws_reconnect_delay
        self.is_running: bool = False
        self.logger = logging.getLogger(f"{__name__}.WebSocketClient")

        # Track consecutive connection failures for alerting
        self._consecutive_failures: int = 0
        self._failure_alert_threshold: int = 5  # Alert after 5 consecutive failures

    async def start(self) -> None:
        """Start WebSocket client with automatic reconnection."""
        self.is_running = True
        self.logger.info("Starting WebSocket client...")

        # Create HTTP session
        self.session = aiohttp.ClientSession()

        # Main reconnection loop
        while self.is_running:
            try:
                await self._connect_and_listen()
                # If we get here, connection closed gracefully
                # Reset reconnect delay and failure counter
                self.reconnect_delay = self.config.ws_reconnect_delay
                self._consecutive_failures = 0
            except Exception as e:
                self.logger.error(f"WebSocket error: {e}", exc_info=True)

                # Track consecutive failures
                self._consecutive_failures += 1

                # Send alert if threshold exceeded
                if self._consecutive_failures >= self._failure_alert_threshold:
                    try:
                        await _ws_security_logger.log_server_error(
                            path="telegram_bot_websocket",
                            error_type=type(e).__name__,
                            client_ip="bot",
                            extra={
                                "consecutive_failures": self._consecutive_failures,
                                "error_message": str(e)[:200]
                            }
                        )
                    except Exception as alert_err:
                        self.logger.warning(f"Failed to send WebSocket failure alert: {alert_err}")

                if self.is_running:
                    # Add jitter to reconnect delay (±20%)
                    jitter_factor = random.uniform(0.8, 1.2)
                    delay_with_jitter = self.reconnect_delay * jitter_factor

                    self.logger.info(f"Reconnecting in {delay_with_jitter:.1f} seconds...")
                    await asyncio.sleep(delay_with_jitter)

                    # Exponential backoff (capped at max delay)
                    self.reconnect_delay = min(
                        self.reconnect_delay * 2,
                        self.config.ws_max_reconnect_delay
                    )

    async def stop(self) -> None:
        """Stop WebSocket client."""
        self.is_running = False
        self.logger.info("Stopping WebSocket client...")

        # Close WebSocket
        if self.ws and not self.ws.closed:
            await self.ws.close()

        # Close HTTP session
        if self.session and not self.session.closed:
            await self.session.close()

        self.logger.info("WebSocket client stopped")

    async def _connect_and_listen(self) -> None:
        """Connect to WebSocket and listen for messages."""
        # Log URL without sensitive query params (redacted)
        ws_url_safe = self.config.ws_url.split('?')[0]
        self.logger.info(f"Connecting to WebSocket: {ws_url_safe}")

        try:
            # Connect to WebSocket with API key in header
            headers = {
                'X-Bot-Api-Key': self.config.bot_api_key
            }
            self.ws = await self.session.ws_connect(
                self.config.ws_url,
                headers=headers,
                heartbeat=self.config.ws_heartbeat_interval
            )

            self.logger.info("WebSocket connected successfully")

            # Listen for messages
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        await self._handle_event(data)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Failed to parse WebSocket message: {e}")
                    except Exception as e:
                        self.logger.error(f"Error handling WebSocket event: {e}", exc_info=True)

                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    self.logger.info("WebSocket connection closed by server")
                    break

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error(f"WebSocket error: {self.ws.exception()}")
                    break

        except aiohttp.ClientError as e:
            self.logger.error(f"WebSocket connection error: {e}")
            raise
        finally:
            self.logger.info("WebSocket connection closed")

    async def _handle_event(self, event: dict) -> None:
        """Handle incoming WebSocket event.

        Args:
            event: Event data from WebSocket.
        """
        event_type = event.get('event_type')
        data = event.get('data', {})

        self.logger.info(f"Received WebSocket event: {event_type}")

        # Handle system events
        if event_type == 'connection_established':
            connection_id = data.get('connection_id', 'unknown')
            self.logger.info(f"Connection established: {connection_id}")
            return

        if event_type == 'heartbeat':
            self.logger.debug("Heartbeat received")
            return

        # Handle ticket events
        if event_type in ['ticket_created', 'ticket_updated', 'ticket_completed']:
            await self._handle_ticket_event(event_type, data)
        else:
            self.logger.warning(f"Unknown event type: {event_type}")

    async def _handle_ticket_event(self, event_type: str, ticket_data: dict) -> None:
        """Handle ticket creation or update event.

        Args:
            event_type: Type of event (ticket_created or ticket_updated).
            ticket_data: Ticket data from event.
        """
        user_id_str = ticket_data.get('user_id')

        if not user_id_str:
            self.logger.error(f"Ticket event missing user_id: {ticket_data}")
            return

        try:
            user_id = UUID(user_id_str)
        except ValueError:
            self.logger.error(f"Invalid user_id format: {user_id_str}")
            return

        self.logger.info(f"Processing {event_type} for user {user_id}")

        # Get ticket_id to check for message reference
        ticket_id_str = ticket_data.get('id')
        ticket_id = UUID(ticket_id_str) if ticket_id_str else None

        # Get all active Telegram chats for this user
        async with get_db_session() as session:
            chats = await get_user_telegram_chats(session, user_id)

            if not chats:
                self.logger.info(f"No active Telegram chats found for user {user_id}")
                return

            self.logger.info(f"Found {len(chats)} active chats for user {user_id}")

            # Get message reference if this is a manual ticket completion
            message_ref = None
            if ticket_id and event_type in ['ticket_completed', 'ticket_updated']:
                message_ref = await get_message_reference(session, ticket_id)

            # Get username from first chat (they all belong to same user)
            username = chats[0].user.username if chats and chats[0].user else "unknown"

            # Send notification to each chat
            for chat in chats:
                try:
                    message = self._format_ticket_message(
                        event_type,
                        ticket_data,
                        username,
                        ticket_id
                    )

                    # Try to reply to original message if reference exists
                    if message_ref and message_ref.chat_id == chat.chat_id:
                        try:
                            await self.bot.send_message(
                                chat.chat_id,
                                message,
                                reply_to_message_id=message_ref.message_id,
                                parse_mode='HTML'
                            )
                            self.logger.info(f"Sent {event_type} reply to chat {chat.chat_id}, message {message_ref.message_id}")
                        except Exception as reply_error:
                            # If reply fails (message deleted), send without reply
                            self.logger.warning(f"Failed to reply to message {message_ref.message_id}, sending without reply: {reply_error}")
                            await self.bot.send_message(
                                chat.chat_id,
                                message,
                                parse_mode='HTML'
                            )
                    else:
                        # No message reference, send normal message
                        await self.bot.send_message(
                            chat.chat_id,
                            message,
                            parse_mode='HTML'
                        )
                        self.logger.info(f"Sent {event_type} notification to chat {chat.chat_id}")

                except Exception as e:
                    self.logger.error(
                        f"Failed to send message to chat {chat.chat_id}: {e}",
                        exc_info=True
                    )

                    # Deactivate chat if bot was blocked or chat doesn't exist
                    if 'bot was blocked' in str(e).lower() or 'chat not found' in str(e).lower():
                        self.logger.warning(f"Deactivating chat {chat.chat_id} due to error")
                        chat.is_active = False
                        await session.commit()

    def _format_ticket_message(self, event_type: str, ticket_data: dict, username: str, ticket_id: Optional[UUID]) -> str:
        """Format ticket data into human-readable message.

        Args:
            event_type: Type of event (ticket_created, ticket_updated, or ticket_completed).
            ticket_data: Ticket data.
            username: User's username for header.
            ticket_id: Ticket UUID.

        Returns:
            Formatted message string.
        """
        firstname = ticket_data.get('firstname', '')
        lastname = ticket_data.get('lastname', '')
        address = ticket_data.get('address', '')
        status = ticket_data.get('status', 'unknown')
        response_data = ticket_data.get('response_data')

        # Validate and parse response_data if present
        if response_data:
            if isinstance(response_data, str):
                try:
                    response_data = json.loads(response_data)
                except json.JSONDecodeError:
                    self.logger.warning(f"Failed to parse response_data as JSON: {response_data}")
                    response_data = {}
            elif not isinstance(response_data, dict):
                response_data = {}
        else:
            response_data = {}

        if event_type == 'ticket_created':
            # Use simple format for creation (no header needed)
            ticket_id_display = str(ticket_id)[-8:] if ticket_id else 'unknown'
            return (
                "✅ <b>Тикет создан!</b>\n\n"
                f"ID: <code>{ticket_id_display}</code>\n"
                f"Имя: {html.escape(firstname)} {html.escape(lastname)}\n"
                f"Адрес: {html.escape(address)}\n"
                f"Статус: pending\n\n"
                "Вы получите уведомление когда тикет будет обработан."
            )

        elif event_type == 'ticket_updated' or (event_type == 'ticket_completed' and status == 'completed'):
            # For completed tickets, use formatted header and response
            if status == 'completed' and ticket_id:
                # Generate header
                header = format_order_header(
                    ticket_id,
                    username,
                    'manual_ssn',
                    MANUAL_SSN_PRICE
                )

                # Format complete message using formatter
                formatted_message = format_manual_ticket_completed(
                    header,
                    {
                        'firstname': firstname,
                        'lastname': lastname,
                        'address': address
                    },
                    response_data
                )

                # Add note about auto-adding to Orders
                formatted_message += "\n\n✅ Результат автоматически добавлен в раздел Orders."

                return formatted_message
            else:
                # Status update without completion
                ticket_id_display = str(ticket_id)[-8:] if ticket_id else 'unknown'
                message = (
                    "🔔 <b>Тикет обновлен!</b>\n\n"
                    f"ID: <code>{ticket_id_display}</code>\n"
                    f"Имя: {html.escape(firstname)} {html.escape(lastname)}\n"
                    f"Статус: {status}\n"
                )

                if status == 'failed':
                    message += "\n❌ Обработка тикета завершилась с ошибкой."

                return message

        ticket_id_display = str(ticket_id)[-8:] if ticket_id else 'unknown'
        return f"Событие: {event_type}\nТикет: {ticket_id_display}"
