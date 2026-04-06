from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ContextHealth:
    token_usage_ratio: float = 0.0
    consecutive_errors: int = 0
    tool_success_rate: float = 1.0
    rounds_since_compact: int = 0

    @property
    def should_pause(self) -> bool:
        return (
            self.consecutive_errors >= 3
            or self.tool_success_rate < 0.3
            or self.token_usage_ratio > 0.9
        )

    @property
    def should_compact(self) -> bool:
        return self.token_usage_ratio > 0.6 or self.rounds_since_compact > 5
