"""Tests for godot_agent.llm.streaming module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from godot_agent.llm.client import LLMClient
from godot_agent.llm.streaming import _stream_via_backend, _stream_direct
from godot_agent.llm.types import LLMConfig, Message


def _make_client(*, backend_url: str = "") -> LLMClient:
    cfg = LLMConfig(
        api_key="sk-test",
        provider="openai",
        model="gpt-5.4",
        backend_url=backend_url,
        backend_api_key="gc_live_test" if backend_url else "",
    )
    return LLMClient(cfg)


class _FakeStreamCtx:
    """Fake httpx async stream context manager that records the request body."""

    def __init__(self, recorder: dict, status_code: int = 200):
        self.recorder = recorder
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self) -> None:
        pass

    async def aiter_lines(self):
        yield "data: [DONE]"

    async def aiter_bytes(self):
        if False:
            yield b""


class TestBackendStreaming:
    @pytest.mark.asyncio
    async def test_backend_streaming_sets_stream_options_include_usage(self):
        """Regression v1.0.0/B5: _stream_via_backend MUST send
        stream_options={"include_usage": True} so the final SSE chunk
        contains usage info. Without this, backend-mode users see
        token count of 0 in the TUI usage line.
        """
        recorder: dict = {}
        client = _make_client(backend_url="https://backend.example.com")

        def fake_stream(method, url, **kwargs):
            recorder["url"] = url
            recorder["body"] = kwargs.get("json")
            recorder["headers"] = kwargs.get("headers")
            return _FakeStreamCtx(recorder)

        client._http.stream = MagicMock(side_effect=fake_stream)

        await _stream_via_backend(
            client,
            messages=[Message.user("hi")],
            tools=None,
            on_chunk=None,
            route_metadata={
                "session_id": "test",
                "agent_role": "worker",
                "mode": "apply",
                "round_number": 1,
            },
        )

        assert "body" in recorder, "stream() was not called"
        body = recorder["body"]
        assert body.get("stream") is True
        assert "stream_options" in body, (
            "_stream_via_backend must set stream_options for usage reporting; "
            f"body keys: {sorted(body.keys())}"
        )
        assert body["stream_options"] == {"include_usage": True}

    @pytest.mark.asyncio
    async def test_direct_streaming_already_sets_stream_options(self):
        """Sanity: _stream_direct already sets stream_options correctly.
        Documents the baseline behavior we're matching in backend mode.
        """
        recorder: dict = {}
        client = _make_client()

        def fake_stream(method, url, **kwargs):
            recorder["body"] = kwargs.get("json")
            return _FakeStreamCtx(recorder)

        client._http.stream = MagicMock(side_effect=fake_stream)

        await _stream_direct(
            client,
            messages=[Message.user("hi")],
            tools=None,
            on_chunk=None,
        )

        assert recorder["body"].get("stream_options") == {"include_usage": True}
