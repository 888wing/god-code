"""Runtime bridge state used by editor/runtime integration and playtest analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RuntimeNodeState:
    path: str
    type: str
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class RuntimeEvent:
    name: str
    payload: str = ""
    tick: int = 0


@dataclass
class RuntimeSnapshot:
    active_scene: str = ""
    current_tick: int = 0
    nodes: list[RuntimeNodeState] = field(default_factory=list)
    events: list[RuntimeEvent] = field(default_factory=list)
    input_actions: list[str] = field(default_factory=list)
    active_inputs: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    fixtures: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    screenshot_paths: list[str] = field(default_factory=list)
    source: str = "synthetic"
    evidence_level: str = "low"
    bridge_connected: bool = False
    captured_at: str = ""


_snapshot: RuntimeSnapshot | None = None

_CONTRACT_STATE_ALIASES: dict[str, tuple[str, ...]] = {
    "enemy_bullets": ("enemy_bullets", "enemy_projectiles", "bullets_enemy", "enemy_bullet_count"),
    "player_bullets": ("player_bullets", "player_projectiles", "bullets_player", "player_bullet_count"),
    "enemies_alive": ("enemies_alive", "enemy_count", "active_enemies", "wave_enemy_count"),
    "player_lives": ("player_lives", "lives", "lives_remaining", "player_hp"),
    "boss_phase": ("boss_phase", "phase", "phase_index"),
    "phase_banner_visible": ("phase_banner_visible", "boss_phase_banner_visible", "banner_visible"),
    "screen_flash": ("screen_flash", "screen_flash_count", "flash_count"),
}

_CONTRACT_EVENT_ALIASES: dict[str, str] = {
    "wave_begin": "wave_started",
    "wave_start": "wave_started",
    "wave_escalated": "wave_pressure",
    "boss_phase": "boss_phase_changed",
    "phase_changed": "boss_phase_changed",
    "phase_transition_clear": "boss_transition_cleared",
    "boss_transition_clear": "boss_transition_cleared",
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _touch_snapshot(
    snapshot: RuntimeSnapshot,
    *,
    source: str | None = None,
    evidence_level: str | None = None,
    bridge_connected: bool | None = None,
) -> RuntimeSnapshot:
    if source is not None:
        snapshot.source = source
    if evidence_level is not None:
        snapshot.evidence_level = evidence_level
    if bridge_connected is not None:
        snapshot.bridge_connected = bridge_connected
    if not snapshot.captured_at:
        snapshot.captured_at = _timestamp()
    else:
        snapshot.captured_at = _timestamp()
    return snapshot


def _ensure_snapshot() -> RuntimeSnapshot:
    global _snapshot
    if _snapshot is None:
        _snapshot = _touch_snapshot(RuntimeSnapshot())
    return _snapshot


def normalize_runtime_event_name(name: str) -> str:
    normalized = name.strip().lower()
    if not normalized:
        return ""
    return _CONTRACT_EVENT_ALIASES.get(normalized, normalized)


def _resolve_contract_value(state: dict[str, Any], fixtures: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for key in aliases:
        if key in state:
            return state[key]
    for fixture_name in ("runtime", "combat", "encounter", "hud"):
        payload = fixtures.get(fixture_name)
        if isinstance(payload, dict):
            for key in aliases:
                if key in payload:
                    return payload[key]
    return None


def runtime_contract_state(snapshot: RuntimeSnapshot | None = None) -> dict[str, Any]:
    target = snapshot or _snapshot
    if target is None:
        return {}
    contract: dict[str, Any] = {}
    for key, aliases in _CONTRACT_STATE_ALIASES.items():
        value = _resolve_contract_value(target.state, target.fixtures, aliases)
        if value is not None:
            contract[key] = value
    return contract


def runtime_contract_events(snapshot: RuntimeSnapshot | None = None) -> list[RuntimeEvent]:
    target = snapshot or _snapshot
    if target is None:
        return []
    normalized: list[RuntimeEvent] = []
    for event in target.events:
        normalized.append(
            RuntimeEvent(
                name=normalize_runtime_event_name(event.name),
                payload=event.payload,
                tick=event.tick,
            )
        )
    return normalized


def update_runtime_snapshot(snapshot: RuntimeSnapshot) -> RuntimeSnapshot:
    global _snapshot
    if snapshot.source == "live_editor":
        snapshot.bridge_connected = True
        if snapshot.evidence_level == "low":
            snapshot.evidence_level = "high"
    elif snapshot.source == "headless":
        snapshot.bridge_connected = False
        if snapshot.evidence_level == "low":
            snapshot.evidence_level = "medium"
    else:
        snapshot.source = snapshot.source or "synthetic"
        snapshot.bridge_connected = False
        snapshot.evidence_level = snapshot.evidence_level or "low"
    _snapshot = _touch_snapshot(snapshot)
    return snapshot


def clear_runtime_snapshot() -> None:
    global _snapshot
    _snapshot = None


def get_runtime_snapshot() -> RuntimeSnapshot | None:
    return _snapshot


def reset_runtime_harness(active_scene: str = "") -> RuntimeSnapshot:
    global _snapshot
    _snapshot = _touch_snapshot(
        RuntimeSnapshot(active_scene=active_scene),
        source="synthetic",
        evidence_level="low",
        bridge_connected=False,
    )
    return _snapshot


def load_runtime_scene(scene_path: str) -> RuntimeSnapshot:
    snapshot = _ensure_snapshot()
    snapshot.active_scene = scene_path
    snapshot.current_tick = 0
    snapshot.nodes = []
    snapshot.events = []
    snapshot.input_actions = []
    snapshot.active_inputs = []
    snapshot.state = {}
    snapshot.fixtures = {}
    snapshot.errors = []
    snapshot.warnings = []
    snapshot.screenshot_paths = []
    return _touch_snapshot(snapshot, source="synthetic", evidence_level="low", bridge_connected=False)


def set_runtime_fixture(name: str, payload: Any) -> RuntimeSnapshot:
    snapshot = _ensure_snapshot()
    snapshot.fixtures[name] = payload
    return _touch_snapshot(snapshot, source="synthetic", evidence_level="low", bridge_connected=False)


def update_runtime_state(values: dict[str, Any]) -> RuntimeSnapshot:
    snapshot = _ensure_snapshot()
    snapshot.state.update(values)
    return _touch_snapshot(snapshot, source="synthetic", evidence_level="low", bridge_connected=False)


def press_runtime_action(action: str, *, pressed: bool = True) -> RuntimeSnapshot:
    snapshot = _ensure_snapshot()
    normalized = action.strip()
    if not normalized:
        return snapshot
    if pressed:
        if normalized not in snapshot.active_inputs:
            snapshot.active_inputs.append(normalized)
        snapshot.input_actions.append(normalized)
    else:
        snapshot.active_inputs = [item for item in snapshot.active_inputs if item != normalized]
    return _touch_snapshot(snapshot, source="synthetic", evidence_level="low", bridge_connected=False)


def record_runtime_event(name: str, payload: str = "", *, tick: int | None = None) -> RuntimeSnapshot:
    snapshot = _ensure_snapshot()
    snapshot.events.append(
        RuntimeEvent(
            name=normalize_runtime_event_name(name),
            payload=payload,
            tick=tick if tick is not None else snapshot.current_tick,
        )
    )
    return _touch_snapshot(snapshot, source="synthetic", evidence_level="low", bridge_connected=False)


def advance_runtime_ticks(
    count: int,
    *,
    state_updates: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
) -> RuntimeSnapshot:
    snapshot = _ensure_snapshot()
    snapshot.current_tick += max(int(count), 0)
    if state_updates:
        snapshot.state.update(state_updates)
    for event in events or []:
        record_runtime_event(
            str(event.get("name", "")),
            str(event.get("payload", "")),
            tick=int(event.get("tick", snapshot.current_tick)),
        )
    return _touch_snapshot(snapshot, source="synthetic", evidence_level="low", bridge_connected=False)


def runtime_events_since(tick: int) -> list[RuntimeEvent]:
    snapshot = _ensure_snapshot()
    return [event for event in snapshot.events if event.tick > tick]


def runtime_state_dict(snapshot: RuntimeSnapshot | None = None) -> dict[str, Any]:
    target = snapshot or _snapshot
    if target is None:
        return {}
    return {
        "active_scene": target.active_scene,
        "current_tick": target.current_tick,
        "state": dict(target.state),
        "contract_state": runtime_contract_state(target),
        "fixtures": dict(target.fixtures),
        "active_inputs": list(target.active_inputs),
    }


def add_runtime_screenshot(path: str) -> RuntimeSnapshot:
    snapshot = _ensure_snapshot()
    snapshot.screenshot_paths.append(path)
    snapshot.screenshot_paths = snapshot.screenshot_paths[-20:]
    return _touch_snapshot(snapshot)


def runtime_snapshot_dict(snapshot: RuntimeSnapshot | None = None) -> dict:
    target = snapshot or _snapshot
    if target is None:
        return {}
    data = asdict(target)
    data["contract_state"] = runtime_contract_state(target)
    data["contract_events"] = [asdict(event) for event in runtime_contract_events(target)]
    return data


def format_runtime_snapshot(snapshot: RuntimeSnapshot | None) -> str:
    if snapshot is None:
        return "No runtime snapshot available."

    lines = ["## Runtime Snapshot"]
    lines.append(f"- Evidence Source: {snapshot.source} ({snapshot.evidence_level})")
    lines.append(f"- Bridge Connected: {'yes' if snapshot.bridge_connected else 'no'}")
    if snapshot.captured_at:
        lines.append(f"- Captured At: {snapshot.captured_at}")
    if snapshot.active_scene:
        lines.append(f"- Active Scene: {snapshot.active_scene}")
    lines.append(f"- Tick: {snapshot.current_tick}")
    if snapshot.input_actions:
        lines.append(f"- Recent Input Actions: {', '.join(snapshot.input_actions[:10])}")
    if snapshot.active_inputs:
        lines.append(f"- Active Inputs: {', '.join(snapshot.active_inputs[:10])}")
    if snapshot.events:
        lines.append("- Events: " + ", ".join(f"{event.name}@{event.tick}" for event in snapshot.events[:10]))
    if snapshot.nodes:
        lines.append("- Visible Nodes:")
        for node in snapshot.nodes[:10]:
            lines.append(f"  - {node.path} [{node.type}]")
    if snapshot.state:
        lines.append("- State:")
        for key, value in list(snapshot.state.items())[:10]:
            lines.append(f"  - {key}: {value}")
    contract_state = runtime_contract_state(snapshot)
    if contract_state:
        lines.append("- Contract State:")
        for key, value in list(contract_state.items())[:10]:
            lines.append(f"  - {key}: {value}")
    if snapshot.fixtures:
        lines.append("- Fixtures: " + ", ".join(list(snapshot.fixtures.keys())[:10]))
    if snapshot.errors:
        lines.append("- Errors: " + " | ".join(snapshot.errors[:5]))
    if snapshot.warnings:
        lines.append("- Warnings: " + " | ".join(snapshot.warnings[:5]))
    return "\n".join(lines)
