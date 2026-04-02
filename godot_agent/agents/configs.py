"""Built-in role configurations for multi-agent orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from godot_agent.runtime.modes import allowed_tools_for_mode


@dataclass(frozen=True)
class AgentConfig:
    name: str
    mode: str
    prompt: str
    allowed_tools: set[str]
    auto_validate: bool = False
    max_tool_rounds: int = 8


_READ_ONLY_TOOLS = allowed_tools_for_mode("plan")
_WORKER_TOOLS = allowed_tools_for_mode("apply")


AGENT_CONFIGS: dict[str, AgentConfig] = {
    "planner": AgentConfig(
        name="planner",
        mode="plan",
        prompt=(
            "You are the Planner agent. Inspect the project and produce a concrete implementation plan, "
            "risks, and validation strategy. Do not edit files."
        ),
        allowed_tools=set(_READ_ONLY_TOOLS),
        auto_validate=False,
        max_tool_rounds=6,
    ),
    "explorer": AgentConfig(
        name="explorer",
        mode="review",
        prompt=(
            "You are the Explorer agent. Read the project, map the relevant scripts/scenes/resources, "
            "and return concise findings. Do not edit files."
        ),
        allowed_tools=set(_READ_ONLY_TOOLS),
        auto_validate=False,
        max_tool_rounds=6,
    ),
    "worker": AgentConfig(
        name="worker",
        mode="apply",
        prompt=(
            "You are the Worker agent. Implement the requested change with the smallest viable edit, "
            "then rely on validation and reviewer feedback to converge."
        ),
        allowed_tools=set(_WORKER_TOOLS),
        auto_validate=True,
        max_tool_rounds=12,
    ),
    "reviewer": AgentConfig(
        name="reviewer",
        mode="review",
        prompt=(
            "You are the Reviewer agent. Validate the changes adversarially and report concrete findings. "
            "Do not edit files."
        ),
        allowed_tools=set(_READ_ONLY_TOOLS),
        auto_validate=False,
        max_tool_rounds=4,
    ),
    "playtest_analyst": AgentConfig(
        name="playtest_analyst",
        mode="review",
        prompt=(
            "You are the Playtest Analyst agent. Evaluate runtime evidence and scenario-based playtest output, "
            "then explain whether the gameplay intent still holds."
        ),
        allowed_tools=set(_READ_ONLY_TOOLS),
        auto_validate=False,
        max_tool_rounds=4,
    ),
}
