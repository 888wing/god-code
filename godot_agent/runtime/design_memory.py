"""Persistent design memory for original-game development workflows."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


DESIGN_MEMORY_DIR = ".god_code"
DESIGN_MEMORY_FILE = "design_memory.json"
LEGACY_MEMORY_FILE = "GOD_CODE.md"


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
                self.notes,
            ]
        )


def design_memory_path(project_root: Path) -> Path:
    return project_root / DESIGN_MEMORY_DIR / DESIGN_MEMORY_FILE


def load_design_memory(project_root: Path) -> DesignMemory:
    path = design_memory_path(project_root)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return DesignMemory(**data)

    legacy_path = project_root / LEGACY_MEMORY_FILE
    if legacy_path.exists():
        return DesignMemory(notes=legacy_path.read_text(encoding="utf-8", errors="replace"))

    return DesignMemory()


def save_design_memory(project_root: Path, memory: DesignMemory) -> Path:
    path = design_memory_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(memory), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def update_design_memory(
    project_root: Path,
    *,
    section: str,
    text: str = "",
    items: list[str] | None = None,
    mapping: dict[str, str] | None = None,
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
    if memory.notes:
        lines.append("\n### Notes")
        lines.append(memory.notes[:2000])
    return "\n".join(lines)
