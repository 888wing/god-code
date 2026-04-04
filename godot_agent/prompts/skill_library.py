"""Task-specific prompt skills layered on top of the general playbook."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSkill:
    key: str
    name: str
    summary: str
    aliases: tuple[str, ...]
    keywords: tuple[str, ...]
    tool_names: tuple[str, ...]
    content: str


SKILLS: tuple[PromptSkill, ...] = (
    PromptSkill(
        key="ui_layout",
        name="UI Layout Architecture",
        summary="Plan container-based UI layouts, theming, and responsive Control hierarchies.",
        aliases=("ui layout", "hud layout", "menu layout", "gui"),
        keywords=("ui", "hud", "menu", "dialog", "layout", "container", "theme", "button", "panel", "control"),
        tool_names=(
            "list_dir",
            "grep",
            "glob",
            "read_file",
            "read_scene",
            "scene_tree",
            "add_scene_node",
            "write_scene_property",
            "validate_project",
            "check_consistency",
            "analyze_impact",
            "plan_ui_layout",
            "validate_ui_layout",
            "screenshot_scene",
            "capture_viewport",
            "compare_baseline",
            "run_playtest",
        ),
        content="""
Goal: build Control scenes with container-driven layout instead of manual positioning.

Workflow:
1. Inspect the current Control tree before editing.
2. Prefer Margin/VBox/HBox/Grid/Center/Panel containers over bare Control roots.
3. Keep themes attached near the root and reuse inherited styling.
4. Validate layout with validate_ui_layout and screenshots after scene edits.
""".strip(),
    ),
    PromptSkill(
        key="animation_pipeline",
        name="Animation Pipeline",
        summary="Coordinate SpriteFrames, AnimationPlayer, Tween, and state-driven animation changes.",
        aliases=("animation pipeline", "animation", "sprite animation", "anim"),
        keywords=("animation", "sprite", "spriteframes", "animatedsprite", "animationplayer", "tween", "idle", "walk", "attack"),
        tool_names=(
            "list_dir",
            "grep",
            "glob",
            "read_file",
            "read_script",
            "edit_script",
            "lint_script",
            "read_scene",
            "scene_tree",
            "write_scene_property",
            "validate_project",
            "analyze_impact",
            "slice_sprite_sheet",
            "validate_sprite_imports",
            "capture_viewport",
            "compare_baseline",
            "run_playtest",
        ),
        content="""
Goal: keep animation setup explicit, reusable, and easy to validate.

Checks:
- Use AnimatedSprite2D + SpriteFrames for frame-based 2D animation.
- Use AnimationPlayer or Tween for property choreography.
- Avoid per-frame play() calls inside _process.
- Validate visible output with runtime or screenshot evidence after animation changes.
""".strip(),
    ),
    PromptSkill(
        key="scene_transition",
        name="Scene Transition & Flow",
        summary="Structure scene swaps, pause overlays, and transition manager flows.",
        aliases=("scene transition", "scene flow", "scene management", "level loading"),
        keywords=("scene", "transition", "change_scene", "loading", "pause", "restart", "main_menu", "autoload"),
        tool_names=(
            "list_dir",
            "grep",
            "glob",
            "read_file",
            "read_script",
            "edit_script",
            "lint_script",
            "read_scene",
            "scene_tree",
            "validate_project",
            "project_dependency_graph",
            "analyze_impact",
            "run_playtest",
            "get_runtime_snapshot",
        ),
        content="""
Goal: keep scene changes centralized and predictable.

Checks:
- Prefer one transition owner such as an Autoload manager.
- Avoid ad-hoc scene swaps across unrelated gameplay scripts.
- Verify changed scene paths and transition triggers after edits.
""".strip(),
    ),
    PromptSkill(
        key="game_state",
        name="Game State & Persistence",
        summary="Model save/load flows, Autoload state, and user:// persistence for demos.",
        aliases=("game state", "save load", "persistence", "save system"),
        keywords=("save", "load", "state", "persist", "config", "settings", "checkpoint", "inventory", "user://"),
        tool_names=(
            "list_dir",
            "grep",
            "glob",
            "read_file",
            "write_file",
            "edit_file",
            "read_script",
            "edit_script",
            "lint_script",
            "validate_project",
            "check_consistency",
            "analyze_impact",
            "read_design_memory",
            "update_design_memory",
        ),
        content="""
Goal: keep demo persistence small, explicit, and recoverable.

Checks:
- Use user:// for writable data.
- Keep save/load ownership centralized in an Autoload or dedicated resource flow.
- Reset state intentionally on new-game paths.
""".strip(),
    ),
    PromptSkill(
        key="bullet_hell",
        name="Bullet Hell Combat",
        summary="Design scripted waves, bullet patterns, boss phases, and readability for shmup combat.",
        aliases=("bullet hell", "danmaku", "shmup"),
        keywords=(
            "bullet",
            "boss",
            "wave",
            "pattern",
            "danmaku",
            "graze",
            "shmup",
            "barrage",
        ),
        tool_names=(
            "list_dir",
            "grep",
            "glob",
            "read_file",
            "read_script",
            "edit_script",
            "lint_script",
            "read_scene",
            "scene_tree",
            "write_scene_property",
            "validate_project",
            "analyze_impact",
            "read_design_memory",
            "update_design_memory",
            "get_runtime_snapshot",
            "run_playtest",
            "load_scene",
            "set_fixture",
            "press_action",
            "advance_ticks",
            "get_runtime_state",
            "get_events_since",
            "capture_viewport",
            "compare_baseline",
            "report_failure",
        ),
        content="""
Goal: build readable, deliberate encounter choreography rather than generic reactive enemy AI.

Workflow:
1. Separate enemy core from movement pattern, fire pattern, and boss phase logic.
2. Treat wave timing, entry path, and bullet shape as first-class combat design assets.
3. Prefer scripted patterns and encounter direction over chase logic unless the genre profile explicitly asks for reactive enemies.
4. Validate phase transitions, bullet clears, and dodge space with runtime harness checks.

Checks:
- Waves should not race or double-advance.
- Boss phase changes should clearly gate pattern transitions.
- Bullet density should remain readable relative to player movement speed.
- Titles, controls, and actual mechanics should agree on the game's combat direction.
""".strip(),
    ),
    PromptSkill(
        key="topdown_shooter",
        name="Top-Down Shooter Combat",
        summary="Shape reactive combat loops for arena and top-down shooters.",
        aliases=("topdown shooter", "top down shooter", "arena shooter"),
        keywords=("shooter", "arena", "weapon", "enemy", "targeting", "pressure"),
        tool_names=(
            "list_dir",
            "grep",
            "glob",
            "read_file",
            "read_script",
            "edit_script",
            "lint_script",
            "read_scene",
            "scene_tree",
            "write_scene_property",
            "validate_project",
            "analyze_impact",
            "read_design_memory",
            "update_design_memory",
            "get_runtime_snapshot",
            "run_playtest",
            "load_scene",
            "set_fixture",
            "press_action",
            "advance_ticks",
            "get_runtime_state",
            "get_events_since",
            "capture_viewport",
            "compare_baseline",
        ),
        content="""
Goal: keep combat responsive, pressure-based, and readable in a free-movement top-down shooter.

Workflow:
1. Decide whether enemies should kite, rush, flank, or hold position before changing scripts.
2. Keep enemy reactions explicit with small state transitions rather than ad-hoc condition chains.
3. Tune pressure through spawn pacing and target selection, not just raw HP inflation.
4. Validate combat loops with runtime state and event checks after each mechanical change.
""".strip(),
    ),
    PromptSkill(
        key="platformer_enemy",
        name="Platformer Enemy Systems",
        summary="Design patrol/chase/attack platformer enemies with reliable ledge and floor logic.",
        aliases=("platformer", "platformer enemy"),
        keywords=("jump", "platform", "ledge", "floor", "patrol", "chase"),
        tool_names=(
            "list_dir",
            "grep",
            "glob",
            "read_file",
            "read_script",
            "edit_script",
            "lint_script",
            "read_scene",
            "scene_tree",
            "write_scene_property",
            "validate_project",
            "analyze_impact",
            "read_design_memory",
            "update_design_memory",
            "get_runtime_snapshot",
            "run_playtest",
            "load_scene",
            "set_fixture",
            "press_action",
            "advance_ticks",
            "get_runtime_state",
            "get_events_since",
        ),
        content="""
Goal: build platformer enemies with explicit movement states and predictable terrain interaction.

Checks:
- Patrol and chase logic should be stateful and readable.
- Ledge, wall, and floor checks must be explicit.
- Attack timing should not be mixed into navigation code without a clear transition model.
""".strip(),
    ),
    PromptSkill(
        key="tower_defense",
        name="Tower Defense Systems",
        summary="Design lanes, path-following enemies, tower pressure, and wave pacing.",
        aliases=("tower defense", "tower defence"),
        keywords=("tower", "turret", "lane", "path", "defense", "wave"),
        tool_names=(
            "list_dir",
            "grep",
            "glob",
            "read_file",
            "read_script",
            "edit_script",
            "lint_script",
            "read_scene",
            "scene_tree",
            "write_scene_property",
            "validate_project",
            "analyze_impact",
            "read_design_memory",
            "update_design_memory",
            "get_runtime_snapshot",
            "run_playtest",
            "load_scene",
            "set_fixture",
            "advance_ticks",
            "get_runtime_state",
            "get_events_since",
            "capture_viewport",
            "compare_baseline",
        ),
        content="""
Goal: optimize around lane control, path-following, target priority, and wave pressure.

Checks:
- Enemy path logic should be deterministic.
- Towers should select targets according to clear priority rules.
- Wave composition should be tunable without rewriting enemy scripts.
""".strip(),
    ),
    PromptSkill(
        key="stealth_guard",
        name="Stealth Guard AI",
        summary="Design patrol, detection, alert, and search loops for stealth enemies.",
        aliases=("stealth guard", "guard ai", "stealth"),
        keywords=("stealth", "guard", "vision", "alert", "patrol", "search"),
        tool_names=(
            "list_dir",
            "grep",
            "glob",
            "read_file",
            "read_script",
            "edit_script",
            "lint_script",
            "read_scene",
            "scene_tree",
            "write_scene_property",
            "validate_project",
            "analyze_impact",
            "read_design_memory",
            "update_design_memory",
            "get_runtime_snapshot",
            "run_playtest",
            "load_scene",
            "set_fixture",
            "press_action",
            "advance_ticks",
            "get_runtime_state",
            "get_events_since",
            "capture_viewport",
            "compare_baseline",
        ),
        content="""
Goal: keep stealth enemies legible through explicit perception and alert-state transitions.

Checks:
- LOS and detection thresholds should be inspectable.
- Alert decay and search behavior should be distinct states, not scattered timers.
- Patrol routing should remain stable after combat or suspicion events.
""".strip(),
    ),
    PromptSkill(
        key="collision",
        name="Collision Architecture",
        summary="Audit collision layers, masks, shapes, and trigger interactions.",
        aliases=("collision architecture", "collisions"),
        keywords=(
            "collision",
            "layer",
            "mask",
            "hitbox",
            "hurtbox",
            "area2d",
            "physicsbody",
            "projectile",
            "bullet",
            "trigger",
        ),
        tool_names=(
            "list_dir",
            "grep",
            "glob",
            "read_file",
            "read_script",
            "edit_script",
            "lint_script",
            "read_scene",
            "scene_tree",
            "add_scene_node",
            "write_scene_property",
            "add_scene_connection",
            "remove_scene_node",
            "validate_project",
            "check_consistency",
            "project_dependency_graph",
            "analyze_impact",
            "run_godot",
            "screenshot_scene",
            "get_runtime_snapshot",
            "get_runtime_state",
            "get_events_since",
            "capture_viewport",
            "compare_baseline",
            "run_playtest",
        ),
        content="""
Goal: keep collision behavior explicit, auditable, and consistent across scripts and scenes.

Workflow:
1. Inspect the scene tree and node types before changing any layer or mask values.
2. Use the standard role-to-layer mapping when possible instead of inventing ad-hoc bitmasks.
3. Prefer one clear owner for collision intent: scene properties for static setup, script assignments only when runtime switching is required.
4. After edits, verify both directions of interaction: who detects whom, and who physically collides with whom.

Checks:
- Every physics body or area must have a collision shape.
- Layer values should be single-layer bitmasks unless the design explicitly requires multi-layer membership.
- Masks should match gameplay intent, not merely mirror layers mechanically.
- Projectiles and triggers should usually be one-way detectors, and that asymmetry should be intentional.

Recommended tools:
- read_scene / scene_tree for node auditing
- write_scene_property for collision_layer and collision_mask
- check_consistency for project-wide collision review
- validate_project after any mutation touching scenes or scripts
""".strip(),
    ),
    PromptSkill(
        key="physics",
        name="Physics Gameplay",
        summary="Stabilize movement, gravity, body semantics, and frame-rate-safe motion.",
        aliases=("physics gameplay", "movement"),
        keywords=(
            "physics",
            "movement",
            "velocity",
            "gravity",
            "jump",
            "slide",
            "characterbody",
            "rigidbody",
            "kinematic",
            "_physics_process",
        ),
        tool_names=(
            "list_dir",
            "grep",
            "glob",
            "read_file",
            "read_script",
            "edit_script",
            "lint_script",
            "read_scene",
            "scene_tree",
            "write_scene_property",
            "validate_project",
            "analyze_impact",
            "run_godot",
            "screenshot_scene",
            "get_runtime_snapshot",
            "get_runtime_state",
            "get_events_since",
            "capture_viewport",
            "compare_baseline",
            "run_playtest",
        ),
        content="""
Goal: keep gameplay motion deterministic, frame-rate-safe, and aligned with Godot body semantics.

Workflow:
1. Identify the body type first: CharacterBody, RigidBody, StaticBody, or Area.
2. Put movement and collision response in _physics_process, not _process.
3. Update velocity with clear ownership: input, acceleration, gravity, then movement call.
4. Preserve existing tuning values unless the task requires mechanical changes.

Checks:
- CharacterBody movement should use velocity and move_and_slide or equivalent body-appropriate APIs.
- RigidBody behavior should prefer forces/impulses over hand-authored transform changes.
- Gravity, jump, friction, and acceleration should not be split between multiple loops without reason.
- Collision-driven state transitions should remain readable and testable.

Recommended tools:
- read_script / edit_script for motion code
- read_scene for body type and shape checks
- validate_project after code or scene changes
- screenshot_scene or runtime validation when behavior depends on spatial setup
""".strip(),
    ),
)
