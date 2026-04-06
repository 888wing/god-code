from __future__ import annotations

import logging

import httpx

from godot_agent.llm.adapters import get_provider_adapter
from godot_agent.llm.redact import redact_secrets
from godot_agent.llm.types import ChatResponse, ComputerUseResponse, LLMConfig, Message, TokenUsage, ToolCall
from godot_agent.runtime.providers import infer_provider

log = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.provider = infer_provider(
            base_url=config.base_url,
            model=config.model,
            provider=config.provider,
        )
        self.adapter = get_provider_adapter(self.provider)
        self._http = httpx.AsyncClient(timeout=120.0)
        self._use_backend = bool(config.backend_url)
        self._backend_url = config.backend_url.rstrip("/") if config.backend_url else ""

    def _build_headers(self) -> dict[str, str]:
        return self.adapter.build_headers(self.config)

    def _build_request_body(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> dict:
        return self.adapter.build_request_body(self.config, messages, tools)

    def _build_url(self) -> str:
        return self.adapter.build_url(self.config)

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        *,
        route_metadata: dict | None = None,
    ) -> ChatResponse:
        if self._use_backend:
            if route_metadata is None:
                log.warning("Backend configured but route_metadata is None — building default metadata")
                route_metadata = {"session_id": "", "agent_role": "worker", "mode": "apply", "round_number": 1}
            return await self._chat_via_backend(messages, tools, route_metadata)
        return await self._chat_direct(messages, tools)

    async def _chat_direct(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> ChatResponse:
        import asyncio as _asyncio

        body = self._build_request_body(messages, tools)
        url = self._build_url()
        headers = self._build_headers()

        for attempt in range(5):
            resp = await self._http.post(url, headers=headers, json=body)
            if resp.status_code == 429:
                wait = min(2 ** attempt * 2, 30)
                log.warning("Rate limited, retrying in %ds (attempt %d/5)", wait, attempt + 1)
                await _asyncio.sleep(wait)
                continue
            if resp.status_code == 400:
                error_body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = error_body.get("error", {}).get("message", resp.text[:200])
                if "content filtering" in error_msg.lower() or "content_filter" in error_msg.lower():
                    if attempt < 4:
                        log.warning("Content filter triggered, retrying (attempt %d/5): %s", attempt + 1, redact_secrets(error_msg[:100]))
                        await _asyncio.sleep(1)
                        continue
                    # Final attempt — return a safe fallback message
                    return ChatResponse(
                        message=Message.assistant(
                            content="[Response blocked by API content filter. Try rephrasing your request or using a different model provider.]"
                        ),
                        usage=TokenUsage(),
                    )
                resp.raise_for_status()
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]["message"]
        tool_calls = None
        if "tool_calls" in choice and choice["tool_calls"]:
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                )
                for tc in choice["tool_calls"]
            ]
        msg = Message.assistant(content=choice.get("content"), tool_calls=tool_calls)
        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )
        return ChatResponse(message=msg, usage=usage)

    async def _chat_via_backend(
        self,
        messages: list[Message],
        tools: list[dict] | None,
        metadata: dict,
    ) -> ChatResponse:
        body: dict = {
            "messages": [m.to_dict() for m in messages],
            "metadata": metadata,
            "stream": False,
        }
        if tools:
            body["tools"] = tools
        if self.config.backend_provider_keys:
            body["provider_keys"] = self.config.backend_provider_keys

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.config.backend_api_key:
            headers["Authorization"] = f"Bearer {self.config.backend_api_key}"

        import asyncio as _asyncio
        url = f"{self._backend_url}/v1/orchestrate"
        for attempt in range(3):
            resp = await self._http.post(url, json=body, headers=headers)
            if resp.status_code in (429, 502, 503):
                wait = min(2 ** attempt * 2, 10)
                log.warning("Backend %d, retrying in %ds (attempt %d/3)", resp.status_code, wait, attempt + 1)
                await _asyncio.sleep(wait)
                continue
            if resp.status_code >= 400:
                detail = ""
                try:
                    err_body = resp.json()
                    err_obj = err_body.get("error", {})
                    detail = err_obj.get("message", "") if isinstance(err_obj, dict) else str(err_obj)
                except Exception:
                    detail = resp.text[:200]
                log.error("Backend API error %d: %s", resp.status_code, redact_secrets(detail))
            break
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]["message"]
        tool_calls = None
        if choice.get("tool_calls"):
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                )
                for tc in choice["tool_calls"]
            ]
        msg = Message.assistant(content=choice.get("content"), tool_calls=tool_calls)
        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        routing = data.get("routing", {})
        if routing:
            log.info(
                "Backend routed to %s/%s: %s (latency=%dms)",
                routing.get("provider"),
                routing.get("model"),
                routing.get("reason"),
                routing.get("latency_ms", 0),
            )

        return ChatResponse(message=msg, usage=usage)

    async def computer_use(
        self,
        prompt: str,
        *,
        screenshot_b64: str | None = None,
        previous_response_id: str | None = None,
        call_id: str | None = None,
        detail: str = "original",
    ) -> ComputerUseResponse:
        # Computer use currently only works via direct provider API (Anthropic/OpenAI responses API).
        # Backend routing for computer_use is not yet supported — log a warning if backend is configured.
        if self._use_backend:
            log.warning("computer_use() does not route through backend — using direct provider API")
        body = self.adapter.build_computer_use_request(
            self.config,
            prompt=prompt,
            screenshot_b64=screenshot_b64,
            previous_response_id=previous_response_id,
            call_id=call_id,
            detail=detail,
        )
        resp = await self._http.post(
            self.adapter.build_responses_url(self.config),
            headers=self._build_headers(),
            json=body,
        )
        if resp.status_code >= 400:
            detail_msg = ""
            try:
                err_body = resp.json()
                err_obj = err_body.get("error", {})
                detail_msg = err_obj.get("message", "") if isinstance(err_obj, dict) else str(err_obj)
            except Exception:
                detail_msg = resp.text[:200]
            log.error("computer_use API error %d: %s", resp.status_code, redact_secrets(detail_msg))
        resp.raise_for_status()
        return self.adapter.parse_computer_use_response(resp.json())

    async def close(self):
        await self._http.aclose()
