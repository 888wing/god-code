"""Protected project paths that require stricter policy handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from godot_agent.godot.project import parse_project_godot


@dataclass
class ProtectedPathSet:
    project_root: Path | None = None
    paths: dict[str, str] = field(default_factory=dict)  # abs path -> reason

    def reason_for(self, path: str | Path) -> str | None:
        target = str(Path(path).resolve())
        return self.paths.get(target)

    def is_protected(self, path: str | Path) -> bool:
        return self.reason_for(path) is not None


def discover_protected_paths(project_root: Path | None) -> ProtectedPathSet:
    protected = ProtectedPathSet(project_root=project_root.resolve() if project_root else None)
    if project_root is None:
        return protected

    project_root = project_root.resolve()
    project_file = project_root / "project.godot"
    if project_file.exists():
        protected.paths[str(project_file.resolve())] = "project settings"
        try:
            project = parse_project_godot(project_file)
        except Exception:
            return protected

        if project.main_scene and project.main_scene.startswith("res://"):
            main_scene = project_root / project.main_scene.replace("res://", "")
            protected.paths[str(main_scene.resolve())] = "main scene"

        for autoload_name, autoload_path in project.autoloads.items():
            if autoload_path.startswith("res://"):
                script_path = project_root / autoload_path.replace("res://", "")
                protected.paths[str(script_path.resolve())] = f"autoload:{autoload_name}"

    return protected
