"""Runtime bridge state used by editor/runtime integration and playtest analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class RuntimeNodeState:
    path: str
    type: str
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class RuntimeEvent:
    name: str
    payload: str = ""


@dataclass
class RuntimeSnapshot:
    active_scene: str = ""
    nodes: list[RuntimeNodeState] = field(default_factory=list)
    events: list[RuntimeEvent] = field(default_factory=list)
    input_actions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    screenshot_paths: list[str] = field(default_factory=list)


_snapshot: RuntimeSnapshot | None = None


def update_runtime_snapshot(snapshot: RuntimeSnapshot) -> RuntimeSnapshot:
    global _snapshot
    _snapshot = snapshot
    return snapshot


def clear_runtime_snapshot() -> None:
    global _snapshot
    _snapshot = None


def get_runtime_snapshot() -> RuntimeSnapshot | None:
    return _snapshot


def runtime_snapshot_dict(snapshot: RuntimeSnapshot | None = None) -> dict:
    target = snapshot or _snapshot
    return asdict(target) if target is not None else {}


def format_runtime_snapshot(snapshot: RuntimeSnapshot | None) -> str:
    if snapshot is None:
        return "No runtime snapshot available."

    lines = ["## Runtime Snapshot"]
    if snapshot.active_scene:
        lines.append(f"- Active Scene: {snapshot.active_scene}")
    if snapshot.input_actions:
        lines.append(f"- Recent Input Actions: {', '.join(snapshot.input_actions[:10])}")
    if snapshot.events:
        lines.append("- Events: " + ", ".join(event.name for event in snapshot.events[:10]))
    if snapshot.nodes:
        lines.append("- Visible Nodes:")
        for node in snapshot.nodes[:10]:
            lines.append(f"  - {node.path} [{node.type}]")
    if snapshot.errors:
        lines.append("- Errors: " + " | ".join(snapshot.errors[:5]))
    if snapshot.warnings:
        lines.append("- Warnings: " + " | ".join(snapshot.warnings[:5]))
    return "\n".join(lines)
