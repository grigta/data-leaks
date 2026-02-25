"""
WebSocket manager for real-time user notifications.
Handles ticket updates for regular users.
"""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict
import logging
from datetime import datetime


# Logger setup
logger = logging.getLogger(__name__)


class WebSocketEventType:
    """Event type constants for WebSocket messages."""
    TICKET_CREATED = "ticket_created"
    TICKET_UPDATED = "ticket_updated"
    TICKET_COMPLETED = "ticket_completed"
    # Support thread events
    THREAD_CREATED = "thread_created"
    THREAD_MESSAGE_ADDED = "thread_message_added"
    THREAD_STATUS_UPDATED = "thread_status_updated"
    THREAD_MESSAGES_READ = "thread_messages_read"
    # Contact thread events
    CONTACT_THREAD_CREATED = "contact_thread_created"
    CONTACT_THREAD_MESSAGE_ADDED = "contact_thread_message_added"
    CONTACT_THREAD_STATUS_UPDATED = "contact_thread_status_updated"
    CONTACT_THREAD_MESSAGES_READ = "contact_thread_messages_read"
    # Balance events
    BALANCE_UPDATED = "balance_updated"
    # DEPRECATED: Old support message events (kept for backward compatibility)
    SUPPORT_MESSAGE_CREATED = "support_message_created"
    SUPPORT_MESSAGE_ANSWERED = "support_message_answered"
    # DEPRECATED: Old contact message events (kept for backward compatibility)
    CONTACT_MESSAGE_CREATED = "contact_message_created"
    CONTACT_MESSAGE_ANSWERED = "contact_message_answered"


class PublicWebSocketManager:
    """
    Manages WebSocket connections for regular users.

    Users receive real-time updates for their own tickets only.
    """

    def __init__(self):
        """Initialize the WebSocket manager with empty connection pool."""
        self.user_connections: Dict[str, WebSocket] = {}
        self.user_metadata: Dict[str, dict] = {}
        self.bot_connections: Dict[str, WebSocket] = {}
        self.bot_metadata: Dict[str, dict] = {}

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        username: str
    ) -> None:
        """
        Accept a WebSocket connection and register the user.

        Args:
            websocket: The WebSocket connection
            user_id: User's unique identifier
            username: User's username for logging
        """
        # Check for existing connection and close it
        if user_id in self.user_connections:
            existing_websocket = self.user_connections[user_id]
            logger.info(f"Closing existing connection for user {username} (reconnection)")
            try:
                await existing_websocket.close()
            except Exception as e:
                logger.warning(f"Error closing existing connection for user {username}: {e}")
            self.disconnect(user_id)

        # Accept the WebSocket connection
        await websocket.accept()

        # Store user metadata
        self.user_metadata[user_id] = {
            "username": username,
            "connected_at": datetime.utcnow().isoformat()
        }

        # Add to connection pool
        self.user_connections[user_id] = websocket
        logger.info(f"WebSocket connected: user={username} (user_id={user_id})")

        # Send welcome message
        welcome_message = {
            "event_type": "connection_established",
            "data": {
                "message": "Connected to public WebSocket",
                "user_id": user_id,
                "username": username
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        await websocket.send_json(welcome_message)

    def disconnect(self, user_id: str) -> None:
        """
        Disconnect a user and clean up their connection.

        Args:
            user_id: User's unique identifier
        """
        # Get username for logging
        username = self.user_metadata.get(user_id, {}).get("username", "unknown")

        # Remove from connection pool
        if user_id in self.user_connections:
            del self.user_connections[user_id]
            logger.info(f"WebSocket disconnected: user={username}")

        # Remove metadata
        if user_id in self.user_metadata:
            del self.user_metadata[user_id]

    async def send_to_user(self, user_id: str, event_type: str, data: dict) -> None:
        """
        Send a message to a specific user.

        Args:
            user_id: Target user's ID
            event_type: Type of event
            data: Event data
        """
        message = {
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }

        if user_id in self.user_connections:
            websocket = self.user_connections[user_id]
            try:
                await websocket.send_json(message)
                logger.info(f"Sent {event_type} to user {user_id} via WebSocket")
            except WebSocketDisconnect:
                logger.warning(f"User {user_id} disconnected during send")
                self.disconnect(user_id)
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {e}")
                self.disconnect(user_id)
        else:
            connected_users = list(self.user_connections.keys())
            logger.info(f"User {user_id} not connected on this worker, skipping {event_type}. Connected users: {connected_users}")

    async def connect_bot(self, websocket: WebSocket, connection_id: str) -> None:
        """
        Register a bot WebSocket connection.

        Args:
            websocket: The WebSocket connection
            connection_id: Unique identifier for this connection
        """
        self.bot_connections[connection_id] = websocket
        self.bot_metadata[connection_id] = {
            "connected_at": datetime.utcnow().isoformat()
        }
        logger.info(f"Bot WebSocket registered: connection_id={connection_id}")

    def disconnect_bot(self, connection_id: str) -> None:
        """
        Disconnect a bot and clean up their connection.

        Args:
            connection_id: Bot connection identifier
        """
        if connection_id in self.bot_connections:
            del self.bot_connections[connection_id]
            logger.info(f"Bot WebSocket disconnected: connection_id={connection_id}")

        if connection_id in self.bot_metadata:
            del self.bot_metadata[connection_id]

    async def _broadcast_to_bots(self, event_type: str, data: dict) -> None:
        """
        Broadcast an event to all connected bots.

        Args:
            event_type: Type of event
            data: Event data
        """
        logger.info(f"Broadcasting {event_type} to {len(self.bot_connections)} bots")

        message = {
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }

        disconnected_bots = []

        for connection_id, websocket in self.bot_connections.items():
            try:
                await websocket.send_json(message)
                logger.info(f"Sent {event_type} to bot {connection_id}")
            except WebSocketDisconnect:
                logger.warning(f"Bot {connection_id} disconnected during send")
                disconnected_bots.append(connection_id)
            except Exception as e:
                logger.error(f"Error sending message to bot {connection_id}: {e}")
                disconnected_bots.append(connection_id)

        # Clean up disconnected bots
        for connection_id in disconnected_bots:
            self.disconnect_bot(connection_id)

    async def notify_ticket_created(self, user_id: str, ticket_data: dict) -> None:
        """
        Notify a user about their newly created ticket.

        Args:
            user_id: Ticket owner's user ID
            ticket_data: Dictionary containing ticket information
        """
        ticket_id = ticket_data.get('id', 'unknown')
        logger.info(f"Notifying user {user_id} about created ticket {ticket_id}")
        await self.send_to_user(user_id, WebSocketEventType.TICKET_CREATED, ticket_data)
        # Also broadcast to all bots with user_id included
        ticket_data_with_user = {**ticket_data, 'user_id': user_id}
        await self._broadcast_to_bots(WebSocketEventType.TICKET_CREATED, ticket_data_with_user)

    async def notify_ticket_updated(self, user_id: str, ticket_data: dict) -> None:
        """
        Notify a user about their ticket update.

        Args:
            user_id: Ticket owner's user ID
            ticket_data: Dictionary containing updated ticket information
        """
        ticket_id = ticket_data.get('id', 'unknown')
        status = ticket_data.get('status', 'unknown')
        logger.info(f"Notifying user {user_id} about updated ticket {ticket_id} (status={status})")
        await self.send_to_user(user_id, WebSocketEventType.TICKET_UPDATED, ticket_data)
        # Also broadcast to all bots with user_id included
        ticket_data_with_user = {**ticket_data, 'user_id': user_id}
        await self._broadcast_to_bots(WebSocketEventType.TICKET_UPDATED, ticket_data_with_user)

    async def notify_ticket_completed(self, user_id: str, ticket_data: dict) -> None:
        """
        Notify a user about their completed ticket.

        Args:
            user_id: Ticket owner's user ID
            ticket_data: Dictionary containing completed ticket information with results
        """
        ticket_id = ticket_data.get('id', 'unknown')
        logger.info(f"Notifying user {user_id} about completed ticket {ticket_id}")
        await self.send_to_user(user_id, WebSocketEventType.TICKET_COMPLETED, ticket_data)
        # Also broadcast to all bots with user_id included
        ticket_data_with_user = {**ticket_data, 'user_id': user_id}
        await self._broadcast_to_bots(WebSocketEventType.TICKET_COMPLETED, ticket_data_with_user)

    async def notify_thread_created(self, user_id: str, thread_data: dict) -> None:
        """
        Notify a user about their newly created support thread.

        Args:
            user_id: Thread owner's user ID
            thread_data: Dictionary containing thread information
        """
        thread_id = thread_data.get('id', 'unknown')
        logger.info(f"Notifying user {user_id} about created thread {thread_id}")
        await self.send_to_user(user_id, WebSocketEventType.THREAD_CREATED, thread_data)
        # Also broadcast to all bots with user_id included
        thread_data_with_user = {**thread_data, 'user_id': user_id}
        await self._broadcast_to_bots(WebSocketEventType.THREAD_CREATED, thread_data_with_user)

    async def notify_thread_message_added(self, user_id: str, message_data: dict) -> None:
        """
        Notify a user about a new message in their thread.

        Args:
            user_id: Thread owner's user ID
            message_data: Dictionary containing message information
        """
        thread_id = message_data.get('thread_id', 'unknown')
        logger.info(f"Notifying user {user_id} about new message in thread {thread_id}")
        await self.send_to_user(user_id, WebSocketEventType.THREAD_MESSAGE_ADDED, message_data)

    async def notify_thread_status_updated(self, user_id: str, thread_data: dict) -> None:
        """
        Notify a user about their thread status update.

        Args:
            user_id: Thread owner's user ID
            thread_data: Dictionary containing thread status information
        """
        thread_id = thread_data.get('thread_id', 'unknown')
        status = thread_data.get('status', 'unknown')
        logger.info(f"Notifying user {user_id} about thread {thread_id} status update to {status}")
        await self.send_to_user(user_id, WebSocketEventType.THREAD_STATUS_UPDATED, thread_data)

    async def notify_thread_messages_read(self, user_id: str, thread_data: dict) -> None:
        """
        Notify a user that their thread messages were marked as read.

        Args:
            user_id: Thread owner's user ID
            thread_data: Dictionary containing read information
        """
        thread_id = thread_data.get('thread_id', 'unknown')
        logger.info(f"Notifying user {user_id} that messages in thread {thread_id} were read")
        await self.send_to_user(user_id, WebSocketEventType.THREAD_MESSAGES_READ, thread_data)

    async def broadcast_support_message_created(self, message_data: dict) -> None:
        """
        DEPRECATED: Use notify_thread_created instead.
        Broadcast support message creation to all connected users.

        Args:
            message_data: Dictionary containing support message information
        """
        message_id = message_data.get('id', 'unknown')
        logger.info(f"Broadcasting support message created: {message_id}")
        # Broadcast to all bots
        await self._broadcast_to_bots(WebSocketEventType.SUPPORT_MESSAGE_CREATED, message_data)

    async def broadcast_support_message_answered(self, message_data: dict) -> None:
        """
        DEPRECATED: Use notify_thread_message_added instead.
        Notify a user about support message answer.

        Args:
            message_data: Dictionary containing support message answer information
        """
        user_id = message_data.get('user_id')
        message_id = message_data.get('id', 'unknown')
        logger.info(f"Notifying user {user_id} about answered support message {message_id}")
        if user_id:
            await self.send_to_user(str(user_id), WebSocketEventType.SUPPORT_MESSAGE_ANSWERED, message_data)

    async def notify_contact_thread_created(self, user_id: str, thread_data: dict) -> None:
        """
        Notify a user about their newly created contact thread.

        Args:
            user_id: Thread owner's user ID
            thread_data: Dictionary containing thread information
        """
        thread_id = thread_data.get('id', 'unknown')
        logger.info(f"Notifying user {user_id} about created contact thread {thread_id}")
        await self.send_to_user(user_id, WebSocketEventType.CONTACT_THREAD_CREATED, thread_data)
        # Also broadcast to all bots with user_id included
        thread_data_with_user = {**thread_data, 'user_id': user_id}
        await self._broadcast_to_bots(WebSocketEventType.CONTACT_THREAD_CREATED, thread_data_with_user)

    async def notify_contact_thread_message_added(self, user_id: str, message_data: dict) -> None:
        """
        Notify a user about a new message in their contact thread.

        Args:
            user_id: Thread owner's user ID
            message_data: Dictionary containing message information
        """
        thread_id = message_data.get('thread_id', 'unknown')
        logger.info(f"Notifying user {user_id} about new message in contact thread {thread_id}")
        await self.send_to_user(user_id, WebSocketEventType.CONTACT_THREAD_MESSAGE_ADDED, message_data)

    async def notify_contact_thread_status_updated(self, user_id: str, thread_data: dict) -> None:
        """
        Notify a user about their contact thread status update.

        Args:
            user_id: Thread owner's user ID
            thread_data: Dictionary containing thread status information
        """
        thread_id = thread_data.get('thread_id', 'unknown')
        status = thread_data.get('status', 'unknown')
        logger.info(f"Notifying user {user_id} about contact thread {thread_id} status update to {status}")
        await self.send_to_user(user_id, WebSocketEventType.CONTACT_THREAD_STATUS_UPDATED, thread_data)

    async def notify_contact_thread_messages_read(self, user_id: str, thread_data: dict) -> None:
        """
        Notify a user that their contact thread messages were marked as read.

        Args:
            user_id: Thread owner's user ID
            thread_data: Dictionary containing read information
        """
        thread_id = thread_data.get('thread_id', 'unknown')
        logger.info(f"Notifying user {user_id} that messages in contact thread {thread_id} were read")
        await self.send_to_user(user_id, WebSocketEventType.CONTACT_THREAD_MESSAGES_READ, thread_data)

    async def broadcast_contact_message_created(self, message_data: dict) -> None:
        """
        DEPRECATED: Use notify_contact_thread_created instead.
        Broadcast contact message creation to all connected users.

        Args:
            message_data: Dictionary containing contact message information
        """
        message_id = message_data.get('id', 'unknown')
        logger.info(f"Broadcasting contact message created: {message_id}")
        # Broadcast to all bots
        await self._broadcast_to_bots(WebSocketEventType.CONTACT_MESSAGE_CREATED, message_data)

    async def broadcast_contact_message_answered(self, message_data: dict) -> None:
        """
        DEPRECATED: Use notify_contact_thread_message_added instead.
        Notify a user about contact message answer.

        Args:
            message_data: Dictionary containing contact message answer information
        """
        user_id = message_data.get('user_id')
        message_id = message_data.get('id', 'unknown')
        logger.info(f"Notifying user {user_id} about answered contact message {message_id}")
        if user_id:
            await self.send_to_user(str(user_id), WebSocketEventType.CONTACT_MESSAGE_ANSWERED, message_data)

    async def notify_balance_updated(self, user_id: str, new_balance: float) -> None:
        """
        Notify a user about their balance change.

        Args:
            user_id: User's ID
            new_balance: New balance value
        """
        logger.info(f"Notifying user {user_id} about balance update: ${new_balance}")
        await self.send_to_user(user_id, WebSocketEventType.BALANCE_UPDATED, {
            "user_id": user_id,
            "new_balance": new_balance
        })

    def get_connection_stats(self) -> dict:
        """
        Get current connection statistics.

        Returns:
            Dictionary with connection counts
        """
        return {
            "user_count": len(self.user_connections),
            "bot_count": len(self.bot_connections),
            "total_connections": len(self.user_connections) + len(self.bot_connections)
        }


# Singleton instance
public_ws_manager = PublicWebSocketManager()
ws_manager = public_ws_manager  # Alias for compatibility


# =============================================================================
# Redis pub/sub for cross-worker WebSocket notifications
# =============================================================================
import asyncio
import json
import os
import redis.asyncio as aioredis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_WS_CHANNEL = "ws:user_notify"


async def publish_user_notification(user_id: str, event_type: str, data: dict):
    """Publish a notification to Redis so ALL workers can deliver it."""
    try:
        r = aioredis.from_url(REDIS_URL)
        message = json.dumps({"user_id": user_id, "event_type": event_type, "data": data})
        await r.publish(REDIS_WS_CHANNEL, message)
        await r.aclose()
        logger.info(f"Published {event_type} for user {user_id} to Redis")
    except Exception as e:
        logger.error(f"Error publishing to Redis: {e}")
        # Fallback to direct send (works if user happens to be on this worker)
        await public_ws_manager.send_to_user(user_id, event_type, data)


async def start_redis_subscriber():
    """Background task: subscribe to Redis channel, forward to local WebSocket connections."""
    while True:
        try:
            r = aioredis.from_url(REDIS_URL)
            pubsub = r.pubsub()
            await pubsub.subscribe(REDIS_WS_CHANNEL)
            logger.info(f"Redis WS subscriber started on channel {REDIS_WS_CHANNEL}")

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        payload = json.loads(message["data"])
                        user_id = payload["user_id"]
                        event_type = payload["event_type"]
                        event_data = payload["data"]
                        logger.info(f"Redis subscriber received {event_type} for user {user_id}")
                        await public_ws_manager.send_to_user(user_id, event_type, event_data)
                    except Exception as e:
                        logger.error(f"Error processing Redis WS message: {e}")
        except asyncio.CancelledError:
            logger.info("Redis WS subscriber cancelled")
            break
        except Exception as e:
            logger.error(f"Redis WS subscriber error: {e}, reconnecting in 3s...")
            await asyncio.sleep(3)
