"""
WebSocket manager for real-time admin and worker notifications.
"""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Set
from uuid import UUID
import json
import logging
import asyncio
from datetime import datetime


# Logger setup
logger = logging.getLogger(__name__)


class WebSocketEventType:
    """Event type constants for WebSocket messages."""
    TICKET_CREATED = "ticket_created"
    TICKET_UPDATED = "ticket_updated"
    WORKER_REQUEST_CREATED = "worker_request_created"
    WORKER_REQUEST_APPROVED = "worker_request_approved"
    WORKER_REQUEST_REJECTED = "worker_request_rejected"
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
    # Worker invoice events
    WORKER_INVOICE_CREATED = "worker_invoice_created"
    # DEPRECATED: Old support message events (kept for backward compatibility)
    SUPPORT_MESSAGE_CREATED = "support_message_created"
    SUPPORT_MESSAGE_ANSWERED = "support_message_answered"
    SUPPORT_MESSAGE_UPDATED = "support_message_updated"
    # DEPRECATED: Old contact message events (kept for backward compatibility)
    CONTACT_MESSAGE_CREATED = "contact_message_created"
    CONTACT_MESSAGE_ANSWERED = "contact_message_answered"
    CONTACT_MESSAGE_UPDATED = "contact_message_updated"


class WebSocketManager:
    """
    Manages WebSocket connections for admin and worker users.

    Supports channel-based broadcasting:
    - Admins receive all events
    - Workers receive only events related to their assigned tickets
    - Ticket owners receive events for their tickets
    """

    def __init__(self):
        """Initialize the WebSocket manager with empty connection pools."""
        self.admin_connections: Dict[str, WebSocket] = {}
        self.worker_connections: Dict[str, WebSocket] = {}
        self.user_metadata: Dict[str, dict] = {}

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        username: str,
        is_admin: bool,
        worker_role: bool
    ) -> None:
        """
        Accept a WebSocket connection and register the user.

        Args:
            websocket: The WebSocket connection
            user_id: User's unique identifier
            username: User's username for logging
            is_admin: Whether user has admin privileges
            worker_role: Whether user has worker role
        """
        # Check for existing connection and close it
        existing_websocket = None
        if user_id in self.admin_connections:
            existing_websocket = self.admin_connections[user_id]
            logger.info(f"Closing existing admin connection for user {username} (reconnection)")
        elif user_id in self.worker_connections:
            existing_websocket = self.worker_connections[user_id]
            logger.info(f"Closing existing worker connection for user {username} (reconnection)")

        if existing_websocket:
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
            "is_admin": is_admin,
            "worker_role": worker_role,
            "connected_at": datetime.utcnow().isoformat()
        }

        # Add to appropriate connection pool
        if is_admin and not worker_role:
            self.admin_connections[user_id] = websocket
            logger.info(f"WebSocket connected: user={username} (admin=True, worker=False)")
        elif worker_role:
            self.worker_connections[user_id] = websocket
            logger.info(f"WebSocket connected: user={username} (admin={is_admin}, worker=True)")

        # Send welcome message
        welcome_message = {
            "event_type": "connection_established",
            "data": {
                "message": "Connected to admin WebSocket",
                "user_id": user_id,
                "username": username,
                "is_admin": is_admin,
                "worker_role": worker_role
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

        # Remove from connection pools
        if user_id in self.admin_connections:
            del self.admin_connections[user_id]
            logger.info(f"WebSocket disconnected: admin user={username}")

        if user_id in self.worker_connections:
            del self.worker_connections[user_id]
            logger.info(f"WebSocket disconnected: worker user={username}")

        # Remove metadata
        if user_id in self.user_metadata:
            del self.user_metadata[user_id]

    async def send_personal_message(self, user_id: str, message: dict) -> None:
        """
        Send a message to a specific user.

        Args:
            user_id: Target user's ID
            message: Message dictionary to send
        """
        # Find the WebSocket connection
        websocket = None
        if user_id in self.admin_connections:
            websocket = self.admin_connections[user_id]
        elif user_id in self.worker_connections:
            websocket = self.worker_connections[user_id]

        if websocket:
            try:
                await websocket.send_json(message)
                logger.debug(f"Sent {message.get('event_type')} to user {user_id}")
            except WebSocketDisconnect:
                logger.warning(f"WebSocket disconnected during send to user {user_id}")
                self.disconnect(user_id)
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {e}")
                self.disconnect(user_id)

    async def broadcast_to_admins(self, event_type: str, data: dict) -> None:
        """
        Broadcast a message to all connected admins.

        Args:
            event_type: Type of event being broadcast
            data: Event data
        """
        message = {
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }

        admin_count = len(self.admin_connections)
        logger.info(f"Broadcasting {event_type} to {admin_count} admins")

        # Create tasks for parallel sending
        async def send_to_admin(user_id: str, websocket: WebSocket):
            try:
                await websocket.send_json(message)
                return None  # Success
            except WebSocketDisconnect:
                logger.warning(f"Admin {user_id} disconnected during broadcast")
                return user_id  # Failed
            except Exception as e:
                logger.error(f"Error broadcasting to admin {user_id}: {e}")
                return user_id  # Failed

        # Execute all sends in parallel
        tasks = [send_to_admin(user_id, websocket) for user_id, websocket in self.admin_connections.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect failed user IDs for cleanup
        failed_user_ids = [user_id for user_id in results if user_id is not None and not isinstance(user_id, Exception)]

        # Clean up failed connections
        for user_id in failed_user_ids:
            self.disconnect(user_id)

    async def broadcast_to_worker(self, worker_id: str, event_type: str, data: dict) -> None:
        """
        Send a message to a specific worker.

        Args:
            worker_id: Target worker's user ID
            event_type: Type of event
            data: Event data
        """
        message = {
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }

        if worker_id in self.worker_connections:
            logger.info(f"Broadcasting {event_type} to worker {worker_id}")
            try:
                websocket = self.worker_connections[worker_id]
                await websocket.send_json(message)
            except WebSocketDisconnect:
                logger.warning(f"Worker {worker_id} disconnected during send")
                self.disconnect(worker_id)
            except Exception as e:
                logger.error(f"Error sending to worker {worker_id}: {e}")
                self.disconnect(worker_id)

    async def broadcast_to_user(self, user_id: str, event_type: str, data: dict) -> None:
        """
        Send a message to a specific user (admin or worker).

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

        logger.info(f"Broadcasting {event_type} to user {user_id}")
        await self.send_personal_message(user_id, message)

    async def broadcast_ticket_created(self, ticket_data: dict) -> None:
        """
        Broadcast ticket creation event to admins only.

        Note: Regular users cannot connect to /admin/ws, so ticket creators
        will not receive real-time notifications through this WebSocket.
        Implement a public WebSocket endpoint if user notifications are needed.

        Args:
            ticket_data: Dictionary containing ticket information
        """
        ticket_id = ticket_data.get('id', 'unknown')

        logger.info(f"Ticket created event broadcasted for ticket {ticket_id}")

        # Notify all admins only
        await self.broadcast_to_admins(WebSocketEventType.TICKET_CREATED, ticket_data)

    async def broadcast_ticket_updated(self, ticket_data: dict) -> None:
        """
        Broadcast ticket update event to admins and assigned workers.

        Note: Regular users (ticket creators) cannot connect to /admin/ws,
        so they will not receive real-time notifications through this WebSocket.
        Implement a public WebSocket endpoint if user notifications are needed.

        Args:
            ticket_data: Dictionary containing updated ticket information
        """
        ticket_id = ticket_data.get('id', 'unknown')
        worker_id = ticket_data.get('worker_id')
        status = ticket_data.get('status', 'unknown')

        logger.info(f"Ticket updated event broadcasted for ticket {ticket_id} (status={status})")

        # Notify all admins
        await self.broadcast_to_admins(WebSocketEventType.TICKET_UPDATED, ticket_data)

        # Notify assigned worker if present
        if worker_id:
            await self.broadcast_to_worker(worker_id, WebSocketEventType.TICKET_UPDATED, ticket_data)

    async def broadcast_worker_request_created(self, request_data: dict) -> None:
        """
        Broadcast worker registration request creation.

        Args:
            request_data: Dictionary containing worker request information
        """
        request_id = request_data.get('request_id', 'unknown')
        logger.info(f"Worker request created event broadcasted for request {request_id}")

        # Only admins need to see worker registration requests
        await self.broadcast_to_admins(WebSocketEventType.WORKER_REQUEST_CREATED, request_data)

    async def broadcast_worker_request_approved(self, request_data: dict, new_user_id: str) -> None:
        """
        Broadcast worker registration approval.

        Args:
            request_data: Dictionary containing approved worker request info
            new_user_id: The newly created user's ID
        """
        request_id = request_data.get('request_id', 'unknown')
        logger.info(f"Worker request approved event broadcasted for request {request_id}, new user {new_user_id}")

        # Notify all admins
        await self.broadcast_to_admins(WebSocketEventType.WORKER_REQUEST_APPROVED, request_data)

        # Notify the newly approved worker if they're already connected (unlikely but possible)
        await self.broadcast_to_user(new_user_id, WebSocketEventType.WORKER_REQUEST_APPROVED, request_data)

    async def broadcast_thread_created(self, thread_data: dict) -> None:
        """
        Broadcast support thread creation to all admins.

        Args:
            thread_data: Dictionary containing thread information
        """
        thread_id = thread_data.get('id', 'unknown')
        logger.info(f"Thread created event broadcasted for thread {thread_id}")
        await self.broadcast_to_admins(WebSocketEventType.THREAD_CREATED, thread_data)

    async def broadcast_thread_message_added(self, message_data: dict) -> None:
        """
        Broadcast thread message addition to all admins.

        Args:
            message_data: Dictionary containing message information
        """
        thread_id = message_data.get('thread_id', 'unknown')
        message_id = message_data.get('message_id', 'unknown')
        logger.info(f"Thread message added event broadcasted for thread {thread_id}, message {message_id}")
        await self.broadcast_to_admins(WebSocketEventType.THREAD_MESSAGE_ADDED, message_data)

    async def broadcast_thread_status_updated(self, thread_data: dict) -> None:
        """
        Broadcast thread status update to all admins.

        Args:
            thread_data: Dictionary containing thread status information
        """
        thread_id = thread_data.get('thread_id', 'unknown')
        logger.info(f"Thread status updated event broadcasted for thread {thread_id}")
        await self.broadcast_to_admins(WebSocketEventType.THREAD_STATUS_UPDATED, thread_data)

    async def broadcast_thread_messages_read(self, thread_data: dict) -> None:
        """
        Broadcast thread messages read event to all admins.

        Args:
            thread_data: Dictionary containing read information
        """
        thread_id = thread_data.get('thread_id', 'unknown')
        logger.info(f"Thread messages read event broadcasted for thread {thread_id}")
        await self.broadcast_to_admins(WebSocketEventType.THREAD_MESSAGES_READ, thread_data)

    async def broadcast_support_message_created(self, message_data: dict) -> None:
        """
        DEPRECATED: Use broadcast_thread_created instead.
        Broadcast support message creation to all admins.

        Args:
            message_data: Dictionary containing support message information
        """
        message_id = message_data.get('id', 'unknown')
        logger.info(f"Support message created event broadcasted for message {message_id}")
        await self.broadcast_to_admins(WebSocketEventType.SUPPORT_MESSAGE_CREATED, message_data)

    async def broadcast_support_message_answered(self, message_data: dict) -> None:
        """
        DEPRECATED: Use broadcast_thread_message_added instead.
        Broadcast support message answer to all admins.

        Args:
            message_data: Dictionary containing support message answer information
        """
        message_id = message_data.get('id', 'unknown')
        logger.info(f"Support message answered event broadcasted for message {message_id}")
        await self.broadcast_to_admins(WebSocketEventType.SUPPORT_MESSAGE_ANSWERED, message_data)

    async def broadcast_contact_thread_created(self, thread_data: dict) -> None:
        """
        Broadcast contact thread creation to all admins.

        Args:
            thread_data: Dictionary containing thread information
        """
        thread_id = thread_data.get('id', 'unknown')
        logger.info(f"Contact thread created event broadcasted for thread {thread_id}")
        await self.broadcast_to_admins(WebSocketEventType.CONTACT_THREAD_CREATED, thread_data)

    async def broadcast_contact_thread_message_added(self, message_data: dict) -> None:
        """
        Broadcast contact thread message addition to all admins.

        Args:
            message_data: Dictionary containing message information
        """
        thread_id = message_data.get('thread_id', 'unknown')
        message_id = message_data.get('message_id', 'unknown')
        logger.info(f"Contact thread message added event broadcasted for thread {thread_id}, message {message_id}")
        await self.broadcast_to_admins(WebSocketEventType.CONTACT_THREAD_MESSAGE_ADDED, message_data)

    async def broadcast_contact_thread_status_updated(self, thread_data: dict) -> None:
        """
        Broadcast contact thread status update to all admins.

        Args:
            thread_data: Dictionary containing thread status information
        """
        thread_id = thread_data.get('thread_id', 'unknown')
        logger.info(f"Contact thread status updated event broadcasted for thread {thread_id}")
        await self.broadcast_to_admins(WebSocketEventType.CONTACT_THREAD_STATUS_UPDATED, thread_data)

    async def broadcast_contact_thread_messages_read(self, thread_data: dict) -> None:
        """
        Broadcast contact thread messages read event to all admins.

        Args:
            thread_data: Dictionary containing read information
        """
        thread_id = thread_data.get('thread_id', 'unknown')
        logger.info(f"Contact thread messages read event broadcasted for thread {thread_id}")
        await self.broadcast_to_admins(WebSocketEventType.CONTACT_THREAD_MESSAGES_READ, thread_data)

    async def broadcast_contact_message_created(self, message_data: dict) -> None:
        """
        DEPRECATED: Use broadcast_contact_thread_created instead.
        Broadcast contact message creation to all admins.

        Args:
            message_data: Dictionary containing contact message information
        """
        message_id = message_data.get('id', 'unknown')
        logger.info(f"Contact message created event broadcasted for message {message_id}")
        await self.broadcast_to_admins(WebSocketEventType.CONTACT_MESSAGE_CREATED, message_data)

    async def broadcast_contact_message_answered(self, message_data: dict) -> None:
        """
        DEPRECATED: Use broadcast_contact_thread_message_added instead.
        Broadcast contact message answer to all admins.

        Args:
            message_data: Dictionary containing contact message answer information
        """
        message_id = message_data.get('id', 'unknown')
        logger.info(f"Contact message answered event broadcasted for message {message_id}")
        await self.broadcast_to_admins(WebSocketEventType.CONTACT_MESSAGE_ANSWERED, message_data)

    async def broadcast_support_message_updated(self, message_data: dict) -> None:
        """
        DEPRECATED: Use broadcast_thread_status_updated instead.
        Broadcast support message status update to all admins.
        This is for pure status changes without adding an answer.

        Args:
            message_data: Dictionary containing support message update information
        """
        message_id = message_data.get('id', 'unknown')
        logger.info(f"Support message updated event broadcasted for message {message_id}")
        await self.broadcast_to_admins(WebSocketEventType.SUPPORT_MESSAGE_UPDATED, message_data)

    async def broadcast_contact_message_updated(self, message_data: dict) -> None:
        """
        Broadcast contact message status update to all admins.
        This is for pure status changes without adding an answer.

        Args:
            message_data: Dictionary containing contact message update information
        """
        message_id = message_data.get('id', 'unknown')
        logger.info(f"Contact message updated event broadcasted for message {message_id}")
        await self.broadcast_to_admins(WebSocketEventType.CONTACT_MESSAGE_UPDATED, message_data)

    def get_online_worker_ids(self) -> List[str]:
        """Return list of user IDs for currently connected workers."""
        return list(self.worker_connections.keys())

    def is_worker_online(self, user_id: str) -> bool:
        """Check if a specific worker is currently connected."""
        return user_id in self.worker_connections

    def get_connection_stats(self) -> dict:
        """
        Get current connection statistics.

        Returns:
            Dictionary with connection counts
        """
        return {
            "admin_count": len(self.admin_connections),
            "worker_count": len(self.worker_connections),
            "total_connections": len(self.admin_connections) + len(self.worker_connections)
        }


# Singleton instance
ws_manager = WebSocketManager()
