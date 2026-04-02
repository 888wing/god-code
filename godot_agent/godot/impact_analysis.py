"""Change-impact analysis for original Godot game development."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from godot_agent.godot.dependency_graph import DependencyGraph, build_dependency_graph
from godot_agent.godot.project import parse_project_godot


@dataclass
class ImpactAnalysisReport:
    requested_files: list[str] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)
    affected_scenes: list[str] = field(default_factory=list)
    affected_scripts: list[str] = field(default_factory=list)
    affected_resources: list[str] = field(default_factory=list)
    affected_autoloads: list[str] = field(default_factory=list)
    input_actions: list[str] = field(default_factory=list)
    validation_focus: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _res_path(project_root: Path, path: str | Path) -> str:
    path_obj = Path(path).resolve()
    try:
        return "res://" + str(path_obj.relative_to(project_root.resolve()))
    except ValueError:
        return str(path_obj)


def _abs_from_res(project_root: Path, path: str) -> Path:
    if path.startswith("res://"):
        return (project_root / path.replace("res://", "")).resolve()
    return Path(path).resolve()


def _extract_input_actions(path: Path) -> set[str]:
    if not path.exists() or path.suffix not in {".gd", ".tscn", ".cfg", ".godot"}:
        return set()
    text = path.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r'Input\.\w+\(\s*"([^"]+)"', text))


def _categorize_affected(report: ImpactAnalysisReport, graph: DependencyGraph) -> None:
    for path in report.affected_files:
        node = graph.nodes.get(path)
        node_type = node.type if node else ("scene" if path.endswith(".tscn") else "script" if path.endswith(".gd") else "resource")
        if node_type == "scene":
            report.affected_scenes.append(path)
        elif node_type in {"script", "autoload"}:
            report.affected_scripts.append(path)
        else:
            report.affected_resources.append(path)

    for name, path in graph.autoloads.items():
        if path in report.affected_files:
            report.affected_autoloads.append(name)


def analyze_change_impact(project_root: Path, changed_files: set[str]) -> ImpactAnalysisReport:
    graph = build_dependency_graph(project_root)
    project = parse_project_godot(project_root / "project.godot") if (project_root / "project.godot").exists() else None
    requested = sorted(_res_path(project_root, path) for path in changed_files)
    affected: set[str] = set(requested)
    reasons: list[str] = []
    input_actions: set[str] = set()

    for path in requested:
        node = graph.nodes.get(path)
        if node:
            affected.update(node.depends_on)
            affected.update(node.depended_by)
            if node.depends_on:
                reasons.append(f"{path} depends on {', '.join(node.depends_on[:5])}.")
            if node.depended_by:
                reasons.append(f"{path} is used by {', '.join(node.depended_by[:5])}.")
        if path.endswith("project.godot") and project is not None:
            if project.main_scene:
                affected.add(project.main_scene)
            affected.update(project.autoloads.values())
            input_actions.update(project.raw_sections.get("input", {}).keys())
            reasons.append("project.godot changes can affect main scene, autoloads, and input map.")

        input_actions.update(_extract_input_actions(_abs_from_res(project_root, path)))

    report = ImpactAnalysisReport(
        requested_files=requested,
        affected_files=sorted(affected),
        input_actions=sorted(action for action in input_actions if action),
        reasons=reasons,
    )
    _categorize_affected(report, graph)

    if any(path.endswith(".tscn") for path in report.requested_files):
        report.validation_focus.append("Validate scene tree, node ownership, resources, and signal wiring.")
    if any(path.endswith(".gd") for path in report.requested_files):
        report.validation_focus.append("Re-check gameplay scripts, typed APIs, and state transitions.")
    if report.input_actions:
        report.validation_focus.append("Verify impacted input actions during runtime or playtest replay.")
    if report.affected_autoloads:
        report.validation_focus.append("Re-test autoload-driven systems and global event flows.")

    if not report.validation_focus:
        report.validation_focus.append("Run standard lint, project validation, and reviewer checks.")
    return report


def infer_request_impact(project_root: Path, task: str) -> ImpactAnalysisReport:
    graph = build_dependency_graph(project_root)
    task_lower = task.lower()
    requested: set[str] = set()
    for path in graph.nodes:
        rel = path.replace("res://", "").lower()
        stem = Path(rel).stem.lower()
        stem_tokens = [token for token in re.split(r"[_\-\s/]+", stem) if token]
        if stem and stem in task_lower:
            requested.add(_abs_from_res(project_root, path).as_posix())
        elif stem_tokens and all(token in task_lower for token in stem_tokens):
            requested.add(_abs_from_res(project_root, path).as_posix())
        elif rel and any(token in task_lower for token in rel.split("/")):
            requested.add(_abs_from_res(project_root, path).as_posix())

    if not requested and graph.main_scene:
        requested.add(_abs_from_res(project_root, graph.main_scene).as_posix())

    return analyze_change_impact(project_root, requested)


def format_impact_report(report: ImpactAnalysisReport) -> str:
    lines = ["## Change Impact Analysis"]
    if report.requested_files:
        lines.append("- Requested files: " + ", ".join(report.requested_files))
    if report.affected_files:
        lines.append("- Affected files: " + ", ".join(report.affected_files[:12]))
    if report.affected_autoloads:
        lines.append("- Affected autoloads: " + ", ".join(report.affected_autoloads))
    if report.input_actions:
        lines.append("- Input actions: " + ", ".join(report.input_actions))
    if report.validation_focus:
        lines.append("\n### Validation Focus")
        lines.extend(f"- {item}" for item in report.validation_focus)
    if report.reasons:
        lines.append("\n### Why")
        lines.extend(f"- {reason}" for reason in report.reasons[:8])
    return "\n".join(lines)
