"""
Hub WebSocket temps réel pour OLEA.

Permet à plusieurs comptables de travailler simultanément :
 - Chaque client se connecte via ``ws://.../ws/live``
 - Quand un utilisateur effectue une opération (CRUD caisse, migration…),
   le backend broadcast un événement JSON à TOUS les clients connectés
 - Les clients reçoivent l'événement et rafraîchissent automatiquement leurs données

Format d'un événement :
  { "channel": "caisse" | "migration", "action": "create" | "update" | "delete" | "migrate" | "migrate_all" | "cleanup", "payload": { ... } }
"""

from typing import List
from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio

class ConnectionManager:
    """Gère les connexions WebSocket actives et le broadcast."""

    def __init__(self):
        self._connections: List[WebSocket] = []
        self._loop: asyncio.AbstractEventLoop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Enregistre la boucle asyncio principale (appelé au démarrage)."""
        self._loop = loop

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def _broadcast(self, channel: str, action: str, payload: dict = None):
        """Envoie un événement à tous les clients connectés (version async)."""
        message = json.dumps({
            "channel": channel,
            "action": action,
            "payload": payload or {},
        }, default=str)

        dead: List[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        # Nettoyer les connexions mortes
        for ws in dead:
            self.disconnect(ws)

    def broadcast(self, channel: str, action: str, payload: dict = None):
        """
        Broadcast thread-safe : peut être appelé depuis un endpoint synchrone
        ou asynchrone. Planifie l'envoi sur la boucle asyncio principale.
        """
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._broadcast(channel, action, payload),
            self._loop,
        )

    @property
    def active_count(self) -> int:
        return len(self._connections)


# Instance globale unique
manager = ConnectionManager()
