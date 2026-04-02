"""Collision layer planner following Godot Playbook standard (Section 7.3).

Assigns collision layers and masks based on entity roles,
ensuring cross-file consistency.

Standard layer plan:
  Layer 1: Player          Layer 5: Enemy Projectiles
  Layer 2: Enemies         Layer 6: Pickups/Items
  Layer 3: Terrain/Walls   Layer 7: Triggers/Areas
  Layer 4: Player Proj     Layer 8: Interactables
"""

from __future__ import annotations

from dataclasses import dataclass

# Standard collision layer assignments
LAYERS = {
    "player":             1,
    "enemy":              2,
    "enemies":            2,
    "terrain":            3,
    "wall":               3,
    "walls":              3,
    "player_projectile":  4,
    "player_bullet":      4,
    "enemy_projectile":   5,
    "enemy_bullet":       5,
    "pickup":             6,
    "item":               6,
    "trigger":            7,
    "area":               7,
    "interactable":       8,
    "npc":                8,
}

# Standard mask assignments (what each entity type detects)
MASKS = {
    "player":             [2, 3, 5, 6, 8],  # enemies, terrain, enemy bullets, pickups, interactables
    "enemy":              [1, 3, 4],          # player, terrain, player bullets
    "enemies":            [1, 3, 4],
    "terrain":            [],                  # static, detects nothing
    "wall":               [],
    "walls":              [],
    "player_projectile":  [2, 3],             # enemies, terrain
    "player_bullet":      [2, 3],
    "enemy_projectile":   [1],                # player only
    "enemy_bullet":       [1],
    "pickup":             [1],                # player only
    "item":               [1],
    "trigger":            [1, 2],             # player, enemies
    "area":               [1, 2],
    "interactable":       [1],                # player only
    "npc":                [1],
}


@dataclass
class CollisionConfig:
    entity_type: str
    layer: int
    layer_bitmask: int
    mask_layers: list[int]
    mask_bitmask: int

    def to_tscn_properties(self) -> dict[str, str]:
        return {
            "collision_layer": str(self.layer_bitmask),
            "collision_mask": str(self.mask_bitmask),
        }

    def to_gdscript(self) -> str:
        return (
            f"collision_layer = {self.layer_bitmask}  "
            f"# Layer {self.layer} ({self.entity_type})\n"
            f"collision_mask = {self.mask_bitmask}  "
            f"# Detects layers {self.mask_layers}"
        )

    def describe(self) -> str:
        return (
            f"{self.entity_type}: Layer {self.layer} "
            f"(bitmask={self.layer_bitmask}), "
            f"Mask layers {self.mask_layers} "
            f"(bitmask={self.mask_bitmask})"
        )


def _layer_to_bitmask(layer: int) -> int:
    """Convert 1-based layer number to bitmask value."""
    return 1 << (layer - 1)


def _layers_to_bitmask(layers: list[int]) -> int:
    """Convert list of 1-based layer numbers to combined bitmask."""
    result = 0
    for layer in layers:
        result |= 1 << (layer - 1)
    return result


def plan_collision(entity_type: str) -> CollisionConfig | None:
    """Get standard collision config for an entity type."""
    entity_lower = entity_type.lower().replace(" ", "_").replace("-", "_")
    layer = LAYERS.get(entity_lower)
    if layer is None:
        return None
    mask_layers = MASKS.get(entity_lower, [])
    return CollisionConfig(
        entity_type=entity_lower,
        layer=layer,
        layer_bitmask=_layer_to_bitmask(layer),
        mask_layers=mask_layers,
        mask_bitmask=_layers_to_bitmask(mask_layers),
    )


def plan_game_collisions(entity_types: list[str]) -> list[CollisionConfig]:
    """Plan collision config for all entity types in a game."""
    configs: list[CollisionConfig] = []
    for et in entity_types:
        config = plan_collision(et)
        if config:
            configs.append(config)
    return configs


def format_collision_plan(configs: list[CollisionConfig]) -> str:
    """Format collision plan as a readable summary for LLM context."""
    lines = ["## Collision Layer Plan", ""]
    lines.append("| Entity | Layer | Bitmask | Detects |")
    lines.append("|--------|-------|---------|---------|")
    for c in configs:
        detects = ", ".join(str(l) for l in c.mask_layers) or "none"
        lines.append(f"| {c.entity_type} | {c.layer} | {c.layer_bitmask} | layers {detects} |")
    return "\n".join(lines)


def validate_collision_consistency(
    layer_mask_pairs: list[tuple[str, int, int]],
) -> list[str]:
    """Check that collision configs are mutually consistent.

    Args:
        layer_mask_pairs: list of (name, layer_bitmask, mask_bitmask)

    Returns:
        List of inconsistency warnings.
    """
    issues: list[str] = []

    for name_a, layer_a, mask_a in layer_mask_pairs:
        for name_b, layer_b, mask_b in layer_mask_pairs:
            if name_a == name_b:
                continue
            # If A's mask includes B's layer, B should probably include A's layer in its mask
            a_detects_b = (mask_a & layer_b) != 0
            b_detects_a = (mask_b & layer_a) != 0
            if a_detects_b and not b_detects_a:
                issues.append(
                    f"{name_a} detects {name_b} (mask includes layer), "
                    f"but {name_b} does NOT detect {name_a}. "
                    f"This may be intentional (one-way detection) or a bug."
                )

    return issues
