"""LiveRuntimeClient — AsyncIO TCP client for the GodCodeBridge Godot plugin.

Connects to the GodCodeBridge GDScript plugin running inside a Godot editor or
game instance.  Communication uses newline-delimited JSON-RPC 2.0 over TCP
(default port 9394).

Typical usage::

    client = LiveRuntimeClient()
    if await client.connect():
        snapshot = await client.build_snapshot()
        await client.disconnect()
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from godot_agent.runtime.runtime_bridge import (
    RuntimeNodeState,
    RuntimeSnapshot,
    _timestamp,
)

logger = logging.getLogger(__name__)

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 9394
_DEFAULT_TIMEOUT = 5.0


# ---------------------------------------------------------------------------
# Pure helper — convert a scene-tree list into a RuntimeSnapshot
# ---------------------------------------------------------------------------

def _build_snapshot_from_tree(tree_data: list[dict[str, Any]]) -> RuntimeSnapshot:
    """Convert raw scene-tree data from GodCodeBridge into a RuntimeSnapshot.

    This is a module-level function so it can be unit-tested without a network
    connection.  The returned snapshot always has ``source="live_editor"``,
    ``evidence_level="high"``, and ``bridge_connected=True`` because data came
    from a real Godot process.
    """
    nodes: list[RuntimeNodeState] = []
    for entry in tree_data:
        path = str(entry.get("path", ""))
        node_type = str(entry.get("type", ""))
        # Everything besides path/type becomes a string property.
        properties: dict[str, str] = {}
        for key, value in entry.items():
            if key not in ("path", "type"):
                properties[key] = str(value)
        nodes.append(RuntimeNodeState(path=path, type=node_type, properties=properties))

    return RuntimeSnapshot(
        nodes=nodes,
        source="live_editor",
        evidence_level="high",
        bridge_connected=True,
        captured_at=_timestamp(),
    )


# ---------------------------------------------------------------------------
# LiveRuntimeClient
# ---------------------------------------------------------------------------

class LiveRuntimeClient:
    """AsyncIO TCP client that talks JSON-RPC to GodCodeBridge inside Godot."""

    def __init__(
        self,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_id: int = 0

    # -- connection lifecycle -----------------------------------------------

    @property
    def connected(self) -> bool:
        """Return True if the underlying transport is open."""
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> bool:
        """Open a TCP connection to the GodCodeBridge server.

        Returns ``True`` on success, ``False`` if the server is unreachable.
        """
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._timeout,
            )
            logger.info("Connected to GodCodeBridge at %s:%s", self._host, self._port)
            return True
        except (OSError, asyncio.TimeoutError) as exc:
            logger.debug("Connection to %s:%s failed: %s", self._host, self._port, exc)
            self._reader = None
            self._writer = None
            return False

    async def disconnect(self) -> None:
        """Close the connection.  Safe to call even when not connected."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            finally:
                self._reader = None
                self._writer = None
                logger.info("Disconnected from GodCodeBridge")

    # -- low-level transport ------------------------------------------------

    async def _send(self, payload: dict[str, Any]) -> None:
        """Send a newline-delimited JSON message."""
        if self._writer is None:
            raise ConnectionError("Not connected")
        data = (json.dumps(payload) + "\n").encode()
        self._writer.write(data)
        await self._writer.drain()

    async def _recv(self) -> dict[str, Any]:
        """Read one newline-delimited JSON response."""
        if self._reader is None:
            raise ConnectionError("Not connected")
        line = await asyncio.wait_for(self._reader.readline(), timeout=self._timeout)
        if not line:
            raise ConnectionError("Server closed the connection")
        return json.loads(line.decode())

    # -- JSON-RPC call ------------------------------------------------------

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a JSON-RPC 2.0 request and return the ``result`` field.

        Returns ``None`` if not connected or on any transport / timeout error.
        Auto-reconnects once on failure before giving up.
        """
        for attempt in range(2):
            if not self.connected:
                if attempt == 0:
                    # Try a single auto-reconnect.
                    if not await self.connect():
                        return None
                else:
                    return None

            self._request_id += 1
            request: dict[str, Any] = {
                "jsonrpc": "2.0",
                "method": method,
                "id": self._request_id,
            }
            if params is not None:
                request["params"] = params

            try:
                await self._send(request)
                response = await self._recv()
                if "error" in response:
                    logger.warning("JSON-RPC error for %s: %s", method, response["error"])
                    return None
                return response.get("result")
            except (OSError, asyncio.TimeoutError, ConnectionError, json.JSONDecodeError) as exc:
                logger.debug("call(%s) attempt %d failed: %s", method, attempt, exc)
                await self.disconnect()
                continue

        return None

    # -- convenience methods ------------------------------------------------

    async def ping(self) -> bool:
        """Return True if the server responds to a ping."""
        result = await self.call("ping")
        return result is not None

    async def get_scene_tree(self) -> list[dict[str, Any]]:
        """Fetch the current scene tree from Godot.

        Returns an empty list on failure.
        """
        result = await self.call("get_scene_tree")
        if isinstance(result, list):
            return result
        return []

    async def build_snapshot(self) -> RuntimeSnapshot:
        """Fetch the scene tree and convert it to a RuntimeSnapshot.

        If the connection is down, returns a minimal snapshot with
        ``bridge_connected=False`` and ``evidence_level="low"``.
        """
        tree = await self.get_scene_tree()
        if tree:
            return _build_snapshot_from_tree(tree)
        # Disconnected or empty tree — return a low-evidence stub.
        return RuntimeSnapshot(
            source="live_editor",
            evidence_level="low",
            bridge_connected=False,
            captured_at=_timestamp(),
        )
