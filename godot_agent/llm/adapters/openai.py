from __future__ import annotations

from typing import Any

from godot_agent.llm.adapters.base import ProviderAdapter
from godot_agent.llm.types import ComputerUseCall, ComputerUseResponse, LLMConfig, Message
from godot_agent.runtime.providers import should_send_reasoning_effort, supports_computer_use, uses_max_completion_tokens


class OpenAICompatibleAdapter(ProviderAdapter):
    def build_request_body(
        self,
        config: LLMConfig,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        token_key = (
            "max_completion_tokens"
            if uses_max_completion_tokens(self.provider, config.model)
            else "max_tokens"
        )
        body: dict[str, Any] = {
            "model": config.model,
            "messages": [message.to_dict() for message in messages],
            token_key: config.max_tokens,
            "temperature": config.temperature,
        }
        if tools:
            body["tools"] = tools
        if should_send_reasoning_effort(self.provider, config.model, config.reasoning_effort):
            body["reasoning_effort"] = config.reasoning_effort
        return body

    def build_computer_use_request(
        self,
        config: LLMConfig,
        *,
        prompt: str,
        screenshot_b64: str | None = None,
        previous_response_id: str | None = None,
        call_id: str | None = None,
        detail: str = "original",
    ) -> dict[str, Any]:
        if not supports_computer_use(self.provider, config.model):
            raise ValueError(f"Computer use is not supported for provider={self.provider} model={config.model}")

        body: dict[str, Any] = {
            "model": config.model,
            "tools": [
                {
                    "type": "computer",
                    "environment": config.computer_use_environment,
                    "display_width": config.computer_use_display_width,
                    "display_height": config.computer_use_display_height,
                }
            ],
        }

        if previous_response_id:
            body["previous_response_id"] = previous_response_id

        if previous_response_id and screenshot_b64:
            if not call_id:
                raise ValueError("call_id is required when sending a computer screenshot continuation")
            body["input"] = [
                {
                    "type": "computer_call_output",
                    "call_id": call_id,
                    "output": {
                        "type": "computer_screenshot",
                        "image_url": f"data:image/png;base64,{screenshot_b64}",
                        "detail": detail,
                    },
                }
            ]
            return body

        if screenshot_b64:
            body["input"] = [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{screenshot_b64}",
                            "detail": detail,
                        },
                    ],
                }
            ]
        else:
            body["input"] = prompt
        return body

    def parse_computer_use_response(self, data: dict[str, Any]) -> ComputerUseResponse:
        output_items = data.get("output") or []
        output_text = data.get("output_text", "")
        if not output_text:
            text_parts: list[str] = []
            for item in output_items:
                if item.get("type") == "message":
                    for content_item in item.get("content", []):
                        if content_item.get("type") in {"output_text", "text"}:
                            text_parts.append(str(content_item.get("text", "")))
            output_text = "\n".join(part for part in text_parts if part).strip()

        computer_calls: list[ComputerUseCall] = []
        for item in output_items:
            if item.get("type") != "computer_call":
                continue
            actions = item.get("actions")
            if actions is None and item.get("action"):
                actions = [item["action"]]
            computer_calls.append(
                ComputerUseCall(
                    call_id=item.get("call_id", ""),
                    actions=list(actions or []),
                    pending_safety_checks=list(item.get("pending_safety_checks") or []),
                    status=item.get("status", ""),
                )
            )

        return ComputerUseResponse(
            response_id=data.get("id", ""),
            output_text=output_text,
            computer_calls=computer_calls,
            output_items=list(output_items),
        )
