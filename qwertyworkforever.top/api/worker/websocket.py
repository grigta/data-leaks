"""
Simple WebSocket manager for worker notifications.
Broadcasts events (new tickets, ticket updates) to all connected workers.
Tracks authenticated worker user IDs for online status.
"""
import logging
import json
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WorkerWebSocketManager:
    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}  # user_id -> WebSocket
        self.anonymous_connections: list[WebSocket] = []  # legacy: unauthenticated connections

    async def connect(self, ws: WebSocket, user_id: str | None = None):
        await ws.accept()
        if user_id:
            # Close existing connection for this user (reconnect)
            if user_id in self.connections:
                try:
                    await self.connections[user_id].close()
                except Exception:
                    pass
            self.connections[user_id] = ws
            logger.info(f"Worker WS connected: user_id={user_id}. Online workers: {len(self.connections)}")
        else:
            self.anonymous_connections.append(ws)
            logger.info(f"Worker WS connected (anonymous). Total anon: {len(self.anonymous_connections)}")

    def disconnect(self, ws: WebSocket, user_id: str | None = None):
        if user_id and user_id in self.connections:
            if self.connections[user_id] is ws:
                del self.connections[user_id]
            logger.info(f"Worker WS disconnected: user_id={user_id}. Online workers: {len(self.connections)}")
        elif ws in self.anonymous_connections:
            self.anonymous_connections.remove(ws)
            logger.info(f"Worker WS disconnected (anonymous). Total anon: {len(self.anonymous_connections)}")

    def get_online_worker_ids(self) -> List[str]:
        """Return list of authenticated online worker user IDs."""
        return list(self.connections.keys())

    async def send_to_worker(self, user_id: str, event: str, data: dict | None = None):
        """Send event to a specific worker by user_id."""
        message = json.dumps({"event": event, "data": data or {}})
        if user_id in self.connections:
            try:
                await self.connections[user_id].send_text(message)
            except Exception:
                if user_id in self.connections:
                    del self.connections[user_id]

    async def broadcast(self, event: str, data: dict | None = None):
        message = json.dumps({"event": event, "data": data or {}})
        dead = []
        # Broadcast to authenticated connections
        for user_id, ws in self.connections.items():
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(user_id)
        for user_id in dead:
            if user_id in self.connections:
                del self.connections[user_id]

        # Broadcast to anonymous connections (legacy)
        dead_anon = []
        for ws in self.anonymous_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead_anon.append(ws)
        for ws in dead_anon:
            if ws in self.anonymous_connections:
                self.anonymous_connections.remove(ws)


ws_manager = WorkerWebSocketManager()
