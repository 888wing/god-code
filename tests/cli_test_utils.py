from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from godot_agent.llm.types import Message, TokenUsage
from godot_agent.runtime.design_memory import GameplayIntentProfile


@dataclass
class FakeEngine:
    project_path: str
    submit_effects: list[Any] = field(default_factory=list)
    messages: list[Message] = field(default_factory=lambda: [Message.system("system")])
    session_usage: TokenUsage = field(default_factory=TokenUsage)
    session_api_calls: int = 0
    last_turn: Any = None
    last_user_input: str = ""
    intent_profile: GameplayIntentProfile = field(default_factory=GameplayIntentProfile)
    on_tool_start: Any = None
    on_tool_end: Any = None
    on_diff: Any = None
    on_stream_start: Any = None
    on_stream_chunk: Any = None
    on_stream_end: Any = None
    on_commit_suggest: Any = None
    on_event: Any = None
    auto_commit: bool = False
    use_streaming: bool = False
    closed: bool = False
    submissions: list[str] = field(default_factory=list)

    def scan_project(self):
        return None

    def _recent_context_files(self) -> list[str]:
        return []

    def refresh_intent_profile(self, user_hint: str | None = None) -> GameplayIntentProfile:
        return self.intent_profile

    async def submit(self, user_input: str) -> str:
        self.last_user_input = user_input
        self.submissions.append(user_input)
        effect = self.submit_effects.pop(0) if self.submit_effects else "ok"
        if isinstance(effect, BaseException):
            raise effect
        if callable(effect):
            return effect(user_input)
        return effect

    async def submit_with_images(self, prompt: str, images_b64: list[str]) -> str:
        self.last_user_input = prompt
        return await self.submit(prompt)

    async def close(self) -> None:
        self.closed = True


def scripted_async_inputs(values: Iterable[str | None]):
    iterator = iter(values)

    async def _reader(*args, **kwargs):
        return next(iterator, None)

    return _reader


def build_engine_factory(effect_sets: list[list[Any]] | None = None):
    created: list[FakeEngine] = []
    remaining = list(effect_sets or [])

    def _factory(config, project_root: Path):
        effects = remaining.pop(0) if remaining else []
        engine = FakeEngine(project_path=str(project_root), submit_effects=list(effects))
        created.append(engine)
        return engine

    return _factory, created
