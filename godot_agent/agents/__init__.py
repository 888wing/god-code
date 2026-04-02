"""Multi-agent orchestration primitives for God Code."""

from godot_agent.agents.configs import AGENT_CONFIGS, AgentConfig
from godot_agent.agents.dispatcher import AgentDispatcher
from godot_agent.agents.results import AgentTaskResult

__all__ = [
    "AGENT_CONFIGS",
    "AgentConfig",
    "AgentDispatcher",
    "AgentTaskResult",
]
