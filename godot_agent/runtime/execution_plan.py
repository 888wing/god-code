from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class PlanStep:
    index: int
    action: str          # create, modify, delete, configure, validate
    target: str          # human-readable description
    files: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, approved, skipped, running, done, failed
    summary: str = ""

    def mark_done(self, summary: str) -> None:
        self.status = "done"
        self.summary = summary

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "action": self.action, "target": self.target,
                "files": self.files, "status": self.status, "summary": self.summary}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanStep:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ExecutionPlan:
    title: str
    steps: list[PlanStep] = field(default_factory=list)
    risk: str = "low"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def approved_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == "approved"]

    @property
    def pending_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == "pending"]

    @property
    def actionable_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status != "skipped"]

    @property
    def done_count(self) -> int:
        return sum(1 for s in self.steps if s.status == "done")

    @property
    def total_actionable(self) -> int:
        return len(self.actionable_steps)

    @property
    def current_step(self) -> PlanStep | None:
        for s in self.steps:
            if s.status == "running":
                return s
        for s in self.steps:
            if s.status == "approved":
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "steps": [s.to_dict() for s in self.steps],
                "risk": self.risk, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionPlan:
        steps = [PlanStep.from_dict(s) for s in data.get("steps", [])]
        return cls(title=data["title"], steps=steps, risk=data.get("risk", "low"),
                   created_at=data.get("created_at", ""))
