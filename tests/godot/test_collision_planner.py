import pytest
from godot_agent.godot.collision_planner import (
    plan_collision, plan_game_collisions, validate_collision_consistency,
)


class TestCollisionPlanner:
    def test_player_layer(self):
        config = plan_collision("player")
        assert config is not None
        assert config.layer == 1
        assert config.layer_bitmask == 1

    def test_enemy_bullet_layer(self):
        config = plan_collision("enemy_bullet")
        assert config is not None
        assert config.layer == 5
        assert 1 in config.mask_layers  # detects player

    def test_unknown_entity(self):
        assert plan_collision("spaceship") is None

    def test_plan_multiple(self):
        configs = plan_game_collisions(["player", "enemy", "player_bullet"])
        assert len(configs) == 3

    def test_consistency_check(self):
        pairs = [
            ("player", 1, 2),     # layer 1, mask includes layer 2
            ("enemy", 2, 0),      # layer 2, mask includes nothing
        ]
        issues = validate_collision_consistency(pairs)
        assert len(issues) > 0  # player detects enemy but enemy doesn't detect player
