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
class CombatProfile:
    player_space_model: str = ""
    density_curve: str = ""
    readability_target: str = ""
    bullet_cleanup_policy: str = ""
    phase_style: str = ""

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.player_space_model,
                self.density_curve,
                self.readability_target,
                self.bullet_cleanup_policy,
                self.phase_style,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AssetSpec:
    style: str = ""
    target_size: list[int] = field(default_factory=list)
    background_key: str = ""
    alpha_required: bool = False
    palette_mode: str = ""
    import_filter: str = ""
    allow_resize: bool = True

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.style,
                self.target_size,
                self.background_key,
                self.alpha_required,
                self.palette_mode,
                self.import_filter,
                not self.allow_resize,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PolishProfile:
    combat_feedback: str = ""
    boss_transition: str = ""
    ui_readability: str = ""
    wave_pacing: str = ""
    juice_level: str = ""

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.combat_feedback,
                self.boss_transition,
                self.ui_readability,
                self.wave_pacing,
                self.juice_level,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GameplayIntentProfile:
    genre: str = ""
    camera_model: str = ""
    player_control_model: str = ""
    combat_model: str = ""
    enemy_model: str = ""
    boss_model: str = ""
    testing_focus: list[str] = field(default_factory=list)
    combat_profile: CombatProfile = field(default_factory=CombatProfile)
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
                not self.combat_profile.is_empty,
                self.conflicts,
                self.reasons,
                self.confidence,
                self.confirmed,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["combat_profile"] = self.combat_profile.to_dict()
        return data


def _combat_profile_from_data(data: dict[str, Any] | CombatProfile | None) -> CombatProfile:
    if isinstance(data, CombatProfile):
        return data
    if not isinstance(data, dict):
        return CombatProfile()
    return CombatProfile(
        player_space_model=str(data.get("player_space_model", "")),
        density_curve=str(data.get("density_curve", "")),
        readability_target=str(data.get("readability_target", "")),
        bullet_cleanup_policy=str(data.get("bullet_cleanup_policy", "")),
        phase_style=str(data.get("phase_style", "")),
    )


def _asset_spec_from_data(data: dict[str, Any] | AssetSpec | None) -> AssetSpec:
    if isinstance(data, AssetSpec):
        return data
    if not isinstance(data, dict):
        return AssetSpec()
    target_size = [int(value) for value in (data.get("target_size") or [])[:2] if str(value).strip()]
    return AssetSpec(
        style=str(data.get("style", "")),
        target_size=target_size,
        background_key=str(data.get("background_key", "")),
        alpha_required=bool(data.get("alpha_required", False)),
        palette_mode=str(data.get("palette_mode", "")),
        import_filter=str(data.get("import_filter", "")),
        allow_resize=bool(data.get("allow_resize", True)),
    )


def _polish_profile_from_data(data: dict[str, Any] | PolishProfile | None) -> PolishProfile:
    if isinstance(data, PolishProfile):
        return data
    if not isinstance(data, dict):
        return PolishProfile()
    return PolishProfile(
        combat_feedback=str(data.get("combat_feedback", "")),
        boss_transition=str(data.get("boss_transition", "")),
        ui_readability=str(data.get("ui_readability", "")),
        wave_pacing=str(data.get("wave_pacing", "")),
        juice_level=str(data.get("juice_level", "")),
    )


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
        combat_profile=_combat_profile_from_data(data.get("combat_profile")),
        conflicts=list(data.get("conflicts") or []),
        reasons=list(data.get("reasons") or []),
        confidence=float(data.get("confidence", 0.0) or 0.0),
        confirmed=bool(data.get("confirmed", False)),
    )


def gameplay_intent_from_data(data: dict[str, Any] | GameplayIntentProfile | None) -> GameplayIntentProfile:
    return _intent_from_data(data)


def asset_spec_from_data(data: dict[str, Any] | AssetSpec | None) -> AssetSpec:
    return _asset_spec_from_data(data)


def polish_profile_from_data(data: dict[str, Any] | PolishProfile | None) -> PolishProfile:
    return _polish_profile_from_data(data)


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
    quality_target: str = ""
    asset_spec: AssetSpec = field(default_factory=AssetSpec)
    polish_profile: PolishProfile = field(default_factory=PolishProfile)
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
                self.quality_target,
                not self.asset_spec.is_empty,
                not self.polish_profile.is_empty,
                self.notes,
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["gameplay_intent"] = self.gameplay_intent.to_dict()
        data["asset_spec"] = self.asset_spec.to_dict()
        data["polish_profile"] = self.polish_profile.to_dict()
        return data


def design_memory_path(project_root: Path) -> Path:
    return project_root / DESIGN_MEMORY_DIR / DESIGN_MEMORY_FILE


def load_design_memory(project_root: Path) -> DesignMemory:
    path = design_memory_path(project_root)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        gameplay_intent = _intent_from_data(data.get("gameplay_intent"))
        asset_spec = _asset_spec_from_data(data.get("asset_spec"))
        polish_profile = _polish_profile_from_data(data.get("polish_profile"))
        known_fields = {f.name for f in DesignMemory.__dataclass_fields__.values()}
        payload = {key: value for key, value in data.items() if key in known_fields and key not in {"gameplay_intent", "asset_spec", "polish_profile"}}
        payload["gameplay_intent"] = gameplay_intent
        payload["asset_spec"] = asset_spec
        payload["polish_profile"] = polish_profile
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
    elif section == "quality_target":
        current_value = memory.quality_target
        memory.quality_target = f"{current_value}\n{text}".strip() if append and current_value and text else text.strip()
    elif section == "asset_spec":
        base = memory.asset_spec.to_dict() if append else {}
        memory.asset_spec = _asset_spec_from_data({**base, **mapping})
    elif section == "polish_profile":
        base = memory.polish_profile.to_dict() if append else {}
        memory.polish_profile = _polish_profile_from_data({**base, **mapping})
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
        if not intent.combat_profile.is_empty:
            combat = intent.combat_profile
            lines.append("- Combat Profile:")
            if combat.player_space_model:
                lines.append(f"  - Player Space: {combat.player_space_model}")
            if combat.density_curve:
                lines.append(f"  - Density Curve: {combat.density_curve}")
            if combat.readability_target:
                lines.append(f"  - Readability: {combat.readability_target}")
            if combat.bullet_cleanup_policy:
                lines.append(f"  - Bullet Cleanup: {combat.bullet_cleanup_policy}")
            if combat.phase_style:
                lines.append(f"  - Phase Style: {combat.phase_style}")
        lines.append(f"- Confirmed: {'yes' if intent.confirmed else 'no'}")
        if intent.confidence:
            lines.append(f"- Confidence: {intent.confidence:.2f}")
        if intent.conflicts:
            lines.append(f"- Conflicts: {', '.join(intent.conflicts)}")
    if memory.quality_target:
        lines.append("\n### Quality Target")
        lines.append(f"- Target: {memory.quality_target}")
    if not memory.asset_spec.is_empty:
        asset = memory.asset_spec
        lines.append("\n### Asset Spec")
        if asset.style:
            lines.append(f"- Style: {asset.style}")
        if asset.target_size:
            lines.append(f"- Target Size: {asset.target_size[0]}x{asset.target_size[1] if len(asset.target_size) > 1 else asset.target_size[0]}")
        if asset.background_key:
            lines.append(f"- Background Key: {asset.background_key}")
        lines.append(f"- Alpha Required: {'yes' if asset.alpha_required else 'no'}")
        if asset.palette_mode:
            lines.append(f"- Palette Mode: {asset.palette_mode}")
        if asset.import_filter:
            lines.append(f"- Import Filter: {asset.import_filter}")
        lines.append(f"- Allow Resize: {'yes' if asset.allow_resize else 'no'}")
    if not memory.polish_profile.is_empty:
        polish = memory.polish_profile
        lines.append("\n### Polish Profile")
        if polish.combat_feedback:
            lines.append(f"- Combat Feedback: {polish.combat_feedback}")
        if polish.boss_transition:
            lines.append(f"- Boss Transition: {polish.boss_transition}")
        if polish.ui_readability:
            lines.append(f"- UI Readability: {polish.ui_readability}")
        if polish.wave_pacing:
            lines.append(f"- Wave Pacing: {polish.wave_pacing}")
        if polish.juice_level:
            lines.append(f"- Juice Level: {polish.juice_level}")
    if memory.notes:
        lines.append("\n### Notes")
        lines.append(memory.notes[:2000])
    return "\n".join(lines)


def resolved_quality_target(memory: DesignMemory | None) -> str:
    target = (memory.quality_target if memory else "").strip().lower()
    return target or "prototype"


def resolved_asset_spec(memory: DesignMemory | None) -> AssetSpec:
    spec = memory.asset_spec if memory else AssetSpec()
    return spec if not spec.is_empty else AssetSpec()


def resolved_polish_profile(memory: DesignMemory | None, *, quality_target: str | None = None) -> PolishProfile:
    profile = memory.polish_profile if memory else PolishProfile()
    target = (quality_target or resolved_quality_target(memory)).strip().lower()
    if profile.is_empty and target == "demo":
        return PolishProfile(
            combat_feedback="required",
            boss_transition="required",
            ui_readability="required",
            wave_pacing="required",
            juice_level="moderate",
        )
    return profile
