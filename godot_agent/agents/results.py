"""Structured results for sub-agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentTaskResult:
    role: str
    content: str = ""
    verdict: str = "PASS"
    notes: list[str] = field(default_factory=list)
    used_tools: list[str] = field(default_factory=list)
    raw: object | None = None
