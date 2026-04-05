"""Tests for LiveRuntimeClient — TCP bridge to Godot's GodCodeBridge plugin."""
from __future__ import annotations

import asyncio
import json

import pytest

from godot_agent.runtime.live_client import LiveRuntimeClient, _build_snapshot_from_tree
from godot_agent.runtime.runtime_bridge import RuntimeSnapshot


# ---------------------------------------------------------------------------
# Connection tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_fails_gracefully_when_no_server():
    """connect() returns False when nothing is listening."""
    client = LiveRuntimeClient(port=19394, timeout=0.5)
    connected = await client.connect()
    assert connected is False


@pytest.mark.asyncio
async def test_disconnect_is_safe_when_not_connected():
    """disconnect() should not raise even if never connected."""
    client = LiveRuntimeClient(port=19394, timeout=0.5)
    await client.disconnect()  # should be a no-op


@pytest.mark.asyncio
async def test_call_returns_none_when_not_connected():
    """call() should return None when there is no connection."""
    client = LiveRuntimeClient(port=19394, timeout=0.5)
    result = await client.call("ping")
    assert result is None


@pytest.mark.asyncio
async def test_ping_returns_false_when_not_connected():
    """ping() wraps call('ping') and returns False on failure."""
    client = LiveRuntimeClient(port=19394, timeout=0.5)
    assert await client.ping() is False


@pytest.mark.asyncio
async def test_get_scene_tree_returns_empty_when_not_connected():
    """get_scene_tree() returns [] when disconnected."""
    client = LiveRuntimeClient(port=19394, timeout=0.5)
    tree = await client.get_scene_tree()
    assert tree == []


@pytest.mark.asyncio
async def test_build_snapshot_returns_disconnected_snapshot_when_offline():
    """build_snapshot() returns a low-evidence snapshot when not connected."""
    client = LiveRuntimeClient(port=19394, timeout=0.5)
    snapshot = await client.build_snapshot()
    assert isinstance(snapshot, RuntimeSnapshot)
    assert snapshot.bridge_connected is False
    assert snapshot.source == "live_editor"
    assert snapshot.evidence_level == "low"


# ---------------------------------------------------------------------------
# Snapshot builder tests (pure function, no network)
# ---------------------------------------------------------------------------

def test_build_snapshot_from_tree_basic():
    """_build_snapshot_from_tree converts a tree list to a RuntimeSnapshot."""
    tree = [
        {"path": "/root/Main", "type": "Node2D", "visible": True, "children_count": 3},
        {"path": "/root/Main/Player", "type": "CharacterBody2D", "visible": True, "children_count": 0},
    ]
    snapshot = _build_snapshot_from_tree(tree)
    assert snapshot.source == "live_editor"
    assert snapshot.evidence_level == "high"
    assert snapshot.bridge_connected is True
    assert len(snapshot.nodes) == 2
    assert snapshot.nodes[0].path == "/root/Main"
    assert snapshot.nodes[0].type == "Node2D"
    assert snapshot.nodes[1].path == "/root/Main/Player"


def test_build_snapshot_from_tree_empty():
    """Empty tree still produces a valid live_editor snapshot."""
    snapshot = _build_snapshot_from_tree([])
    assert snapshot.source == "live_editor"
    assert snapshot.evidence_level == "high"
    assert snapshot.bridge_connected is True
    assert snapshot.nodes == []


def test_build_snapshot_from_tree_preserves_properties():
    """Extra keys in node dicts are stored as properties."""
    tree = [
        {
            "path": "/root/HUD",
            "type": "CanvasLayer",
            "visible": False,
            "children_count": 5,
            "modulate": "(1, 1, 1, 1)",
        },
    ]
    snapshot = _build_snapshot_from_tree(tree)
    node = snapshot.nodes[0]
    assert node.path == "/root/HUD"
    assert node.properties.get("visible") == "False"
    assert node.properties.get("children_count") == "5"
    assert node.properties.get("modulate") == "(1, 1, 1, 1)"


# ---------------------------------------------------------------------------
# Integration: echo server (tests the full send/receive path)
# ---------------------------------------------------------------------------

async def _run_echo_server(host: str, port: int, ready: asyncio.Event) -> None:
    """Minimal JSON-RPC echo server for integration testing."""
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                request = json.loads(line.decode())
                method = request.get("method", "")
                response: dict
                if method == "ping":
                    response = {"jsonrpc": "2.0", "result": {"status": "pong"}, "id": request.get("id")}
                elif method == "get_scene_tree":
                    tree = [{"path": "/root/Main", "type": "Node2D", "visible": True, "children_count": 1}]
                    response = {"jsonrpc": "2.0", "result": tree, "id": request.get("id")}
                else:
                    response = {"jsonrpc": "2.0", "result": None, "id": request.get("id")}
                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, host, port)
    ready.set()
    async with server:
        await server.serve_forever()


@pytest.mark.asyncio
async def test_connect_and_ping_with_echo_server():
    """Full round-trip: connect, ping, disconnect."""
    port = 19395
    ready = asyncio.Event()
    server_task = asyncio.create_task(_run_echo_server("127.0.0.1", port, ready))
    try:
        await asyncio.wait_for(ready.wait(), timeout=2.0)
        client = LiveRuntimeClient(port=port, timeout=2.0)
        connected = await client.connect()
        assert connected is True
        assert await client.ping() is True
        await client.disconnect()
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_get_scene_tree_with_echo_server():
    """get_scene_tree() returns parsed tree data from the server."""
    port = 19396
    ready = asyncio.Event()
    server_task = asyncio.create_task(_run_echo_server("127.0.0.1", port, ready))
    try:
        await asyncio.wait_for(ready.wait(), timeout=2.0)
        client = LiveRuntimeClient(port=port, timeout=2.0)
        await client.connect()
        tree = await client.get_scene_tree()
        assert len(tree) == 1
        assert tree[0]["path"] == "/root/Main"
        await client.disconnect()
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_build_snapshot_with_echo_server():
    """build_snapshot() integrates get_scene_tree + _build_snapshot_from_tree."""
    port = 19397
    ready = asyncio.Event()
    server_task = asyncio.create_task(_run_echo_server("127.0.0.1", port, ready))
    try:
        await asyncio.wait_for(ready.wait(), timeout=2.0)
        client = LiveRuntimeClient(port=port, timeout=2.0)
        await client.connect()
        snapshot = await client.build_snapshot()
        assert snapshot.source == "live_editor"
        assert snapshot.evidence_level == "high"
        assert snapshot.bridge_connected is True
        assert len(snapshot.nodes) == 1
        assert snapshot.nodes[0].path == "/root/Main"
        await client.disconnect()
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
