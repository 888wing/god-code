from __future__ import annotations

from pathlib import Path

from godot_agent.godot.scene_parser import parse_tscn


def validate_resources(tscn_path: Path, project_root: Path) -> list[str]:
    """Validate that all ext_resource paths in a .tscn file exist on disk.

    Args:
        tscn_path: Path to the .tscn scene file.
        project_root: Godot project root directory (where project.godot lives).

    Returns:
        List of issue strings for each missing resource. Empty list means all valid.
    """
    text = tscn_path.read_text(encoding="utf-8", errors="replace")
    scene = parse_tscn(text)
    issues: list[str] = []
    for res in scene.ext_resources:
        if res.path.startswith("res://"):
            rel = res.path[6:]  # strip "res://" prefix
            full = project_root / rel
            if not full.exists():
                issues.append(f"Missing resource: {res.path} (expected at {full})")
    return issues
