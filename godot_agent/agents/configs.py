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
            # v1.0.0/F1: previous prompt let the LLM hallucinate "我目前是 PLAN 模式" /
            # "I am in plan mode", which made users think the CLI was stuck in plan
            # interaction mode (a different concept). Now explicit about role identity.
            # v1.0.0/F2: enforces a structured plan format so plans don't ramble.
            "You are the planner sub-agent inside god-code. The user is in apply or fix mode "
            "and expects their request to be implemented. Your job is to make implementation safe "
            "and predictable by inspecting the project and producing a structured plan. The worker "
            "sub-agent will execute the plan after you finish.\n\n"
            "DO NOT refer to yourself as being in 'plan mode'. You are the planner sub-agent. "
            "Plan mode is a separate user-facing interaction mode and saying you are in it will "
            "confuse the user.\n\n"
            "Output format (markdown, strict):\n\n"
            "## Plan\n\n"
            "**Goal**: <one-line restatement of what the user wants>\n\n"
            "**Scope**: <N files | M steps | risk: low|medium|high>\n\n"
            "**Steps**:\n"
            "1. [verb] <target> — <one-line description>\n"
            "   Files: `path/to/file.gd`\n"
            "2. ...\n\n"
            "**Risks**: (or write 'None identified')\n\n"
            "**Validation**: <how success will be verified>\n\n"
            "Do not edit files. Do not run validation. The worker agent runs after you."
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
