"""Persistent design memory for original-game development workflows."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DESIGN_MEMORY_DIR = ".god_code"
DESIGN_MEMORY_FILE = "design_memory.json"
LEGACY_MEMORY_FILE = "GOD_CODE.md"


@dataclass
class GameplayIntentProfile:
    genre: str = ""
    camera_model: str = ""
    player_control_model: str = ""
    combat_model: str = ""
    enemy_model: str = ""
    boss_model: str = ""
    testing_focus: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    confidence: float = 0.0
    confirmed: bool = False

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.genre,
                self.camera_model,
                self.player_control_model,
                self.combat_model,
                self.enemy_model,
                self.boss_model,
                self.testing_focus,
                self.conflicts,
                self.reasons,
                self.confidence,
                self.confirmed,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _intent_from_data(data: dict[str, Any] | GameplayIntentProfile | None) -> GameplayIntentProfile:
    if isinstance(data, GameplayIntentProfile):
        return data
    if not isinstance(data, dict):
        return GameplayIntentProfile()
    return GameplayIntentProfile(
        genre=str(data.get("genre", "")),
        camera_model=str(data.get("camera_model", "")),
        player_control_model=str(data.get("player_control_model", "")),
        combat_model=str(data.get("combat_model", "")),
        enemy_model=str(data.get("enemy_model", "")),
        boss_model=str(data.get("boss_model", "")),
        testing_focus=list(data.get("testing_focus") or []),
        conflicts=list(data.get("conflicts") or []),
        reasons=list(data.get("reasons") or []),
        confidence=float(data.get("confidence", 0.0) or 0.0),
        confirmed=bool(data.get("confirmed", False)),
    )


@dataclass
class DesignMemory:
    game_title: str = ""
    concept: str = ""
    pillars: list[str] = field(default_factory=list)
    control_rules: list[str] = field(default_factory=list)
    ui_principles: list[str] = field(default_factory=list)
    visual_rules: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    scene_ownership: dict[str, str] = field(default_factory=dict)
    mechanic_notes: dict[str, list[str]] = field(default_factory=dict)
    gameplay_intent: GameplayIntentProfile = field(default_factory=GameplayIntentProfile)
    notes: str = ""

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.game_title,
                self.concept,
                self.pillars,
                self.control_rules,
                self.ui_principles,
                self.visual_rules,
                self.non_goals,
                self.scene_ownership,
                self.mechanic_notes,
                not self.gameplay_intent.is_empty,
                self.notes,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["gameplay_intent"] = self.gameplay_intent.to_dict()
        return data


def design_memory_path(project_root: Path) -> Path:
    return project_root / DESIGN_MEMORY_DIR / DESIGN_MEMORY_FILE


def load_design_memory(project_root: Path) -> DesignMemory:
    path = design_memory_path(project_root)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        gameplay_intent = _intent_from_data(data.get("gameplay_intent"))
        payload = {key: value for key, value in data.items() if key != "gameplay_intent"}
        payload["gameplay_intent"] = gameplay_intent
        return DesignMemory(**payload)

    legacy_path = project_root / LEGACY_MEMORY_FILE
    if legacy_path.exists():
        return DesignMemory(notes=legacy_path.read_text(encoding="utf-8", errors="replace"))

    return DesignMemory()


def save_design_memory(project_root: Path, memory: DesignMemory) -> Path:
    path = design_memory_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memory.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def update_design_memory(
    project_root: Path,
    *,
    section: str,
    text: str = "",
    items: list[str] | None = None,
    mapping: dict[str, Any] | None = None,
    append: bool = False,
) -> DesignMemory:
    memory = load_design_memory(project_root)
    items = items or []
    mapping = mapping or {}

    if section in {"game_title", "concept", "notes"}:
        current = getattr(memory, section)
        setattr(memory, section, f"{current}\n{text}".strip() if append and current else text)
    elif section in {"pillars", "control_rules", "ui_principles", "visual_rules", "non_goals"}:
        current_list = list(getattr(memory, section))
        setattr(memory, section, current_list + items if append else list(items))
    elif section == "scene_ownership":
        current_map = dict(memory.scene_ownership)
        memory.scene_ownership = {**current_map, **mapping} if append else dict(mapping)
    elif section == "gameplay_intent":
        base = memory.gameplay_intent.to_dict() if append else {}
        memory.gameplay_intent = _intent_from_data({**base, **mapping})
    elif section.startswith("mechanic_notes:"):
        key = section.split(":", 1)[1].strip()
        current_notes = dict(memory.mechanic_notes)
        current_list = list(current_notes.get(key, []))
        current_notes[key] = current_list + items if append else list(items)
        memory.mechanic_notes = current_notes
    else:
        raise ValueError(f"Unknown design memory section: {section}")

    save_design_memory(project_root, memory)
    return memory


def format_design_memory(memory: DesignMemory) -> str:
    if memory.is_empty:
        return "No project design memory has been defined yet."

    lines = ["## Project Design Memory"]
    if memory.game_title:
        lines.append(f"- Title: {memory.game_title}")
    if memory.concept:
        lines.append(f"- Concept: {memory.concept}")
    if memory.pillars:
        lines.append("\n### Gameplay Pillars")
        lines.extend(f"- {item}" for item in memory.pillars)
    if memory.control_rules:
        lines.append("\n### Control Rules")
        lines.extend(f"- {item}" for item in memory.control_rules)
    if memory.ui_principles:
        lines.append("\n### UI Principles")
        lines.extend(f"- {item}" for item in memory.ui_principles)
    if memory.visual_rules:
        lines.append("\n### Visual Rules")
        lines.extend(f"- {item}" for item in memory.visual_rules)
    if memory.non_goals:
        lines.append("\n### Non-Goals")
        lines.extend(f"- {item}" for item in memory.non_goals)
    if memory.scene_ownership:
        lines.append("\n### Scene Ownership")
        for scene, owner in sorted(memory.scene_ownership.items()):
            lines.append(f"- {scene}: {owner}")
    if memory.mechanic_notes:
        lines.append("\n### Mechanic Notes")
        for key, notes in sorted(memory.mechanic_notes.items()):
            lines.append(f"- {key}: {', '.join(notes)}")
    if not memory.gameplay_intent.is_empty:
        intent = memory.gameplay_intent
        lines.append("\n### Gameplay Intent")
        if intent.genre:
            lines.append(f"- Genre: {intent.genre}")
        if intent.camera_model:
            lines.append(f"- Camera: {intent.camera_model}")
        if intent.player_control_model:
            lines.append(f"- Player Control: {intent.player_control_model}")
        if intent.combat_model:
            lines.append(f"- Combat: {intent.combat_model}")
        if intent.enemy_model:
            lines.append(f"- Enemy Model: {intent.enemy_model}")
        if intent.boss_model:
            lines.append(f"- Boss Model: {intent.boss_model}")
        if intent.testing_focus:
            lines.append(f"- Testing Focus: {', '.join(intent.testing_focus)}")
        lines.append(f"- Confirmed: {'yes' if intent.confirmed else 'no'}")
        if intent.confidence:
            lines.append(f"- Confidence: {intent.confidence:.2f}")
        if intent.conflicts:
            lines.append(f"- Conflicts: {', '.join(intent.conflicts)}")
    if memory.notes:
        lines.append("\n### Notes")
        lines.append(memory.notes[:2000])
    return "\n".join(lines)
