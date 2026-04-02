"""Task-specific prompt skills layered on top of the general playbook."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSkill:
    name: str
    keywords: tuple[str, ...]
    tool_names: tuple[str, ...]
    content: str


SKILLS: tuple[PromptSkill, ...] = (
    PromptSkill(
        name="Collision Architecture",
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
        name="Physics Gameplay",
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
