"""MCP Server — exposes god-code's Godot tools to AI agents (Claude Code, Codex, etc).

Usage:
    god-code mcp --project /path/to/godot/project

Runs as a local stdio process. No backend server needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

mcp = FastMCP("god-code")  # 

# Project root — set via CLI arg
_project_root: Path | None = None


def set_mcp_project_root(path: Path) -> None:
    global _project_root
    _project_root = path.resolve()


def _root() -> Path:
    return _project_root or Path.cwd()


# ─── Validation Tools ─────────────────────────────────────────────

@mcp.tool()
async def validate_project(project_path: str = "") -> dict:
    """Run Godot headless validation on the project. Returns errors and warnings.

    If project_path is empty, uses the configured project root.
    """
    from godot_agent.runtime.error_loop import validate_project as _validate, format_validation_for_llm
    root = project_path or str(_root())
    # Read godot_path from config
    godot_path = "godot"
    config_file = Path.home() / ".config" / "god-code" / "config.json"
    if config_file.exists():
        cfg = json.loads(config_file.read_text())
        godot_path = cfg.get("godot_path", "godot")
    result = await _validate(root, godot_path, timeout=30)
    return {
        "success": result.success,
        "errors": [{"file": e.file, "line": e.line, "message": e.message} for e in result.errors],
        "warnings": [{"file": w.file, "line": w.line, "message": w.message} for w in result.warnings],
        "summary": format_validation_for_llm(result),
    }


@mcp.tool()
def validate_tscn(file_path: str, auto_fix: bool = False) -> dict:
    """Validate a .tscn scene file format. Optionally auto-fix ordering issues.

    Checks: sub_resource ordering, load_steps count, duplicate nodes, resource references.
    """
    from godot_agent.godot.tscn_validator import validate_tscn as _validate, validate_and_fix
    text = Path(file_path).read_text(errors="replace")
    if auto_fix:
        fixed_text, issues = validate_and_fix(text)
        if fixed_text != text:
            Path(file_path).write_text(fixed_text)
        return {
            "fixed": fixed_text != text,
            "remaining_issues": [{"line": i.line, "severity": i.severity, "message": i.message} for i in issues],
        }
    issues = _validate(text)
    return {
        "issues": [{"line": i.line, "severity": i.severity, "message": i.message} for i in issues],
        "has_errors": any(i.severity == "error" for i in issues),
    }


# ─── Code Quality Tools ──────────────────────────────────────────

@mcp.tool()
def lint_script(file_path: str) -> dict:
    """Lint a GDScript file for naming conventions, code ordering, type annotations, and anti-patterns.

    Based on Godot 4.4 style guide.
    """
    from godot_agent.godot.gdscript_linter import lint_gdscript, format_lint_report
    text = Path(file_path).read_text(errors="replace")
    issues = lint_gdscript(text, filename=Path(file_path).name)
    return {
        "issues": [{"line": i.line, "severity": i.severity, "rule": i.rule, "message": i.message} for i in issues],
        "error_count": sum(1 for i in issues if i.severity == "error"),
        "warning_count": sum(1 for i in issues if i.severity == "warning"),
        "report": format_lint_report(issues, Path(file_path).name),
    }


@mcp.tool()
def check_consistency(project_path: str = "") -> dict:
    """Check cross-file consistency: collision layers, signal names, resource paths, group names.

    Scans all .gd and .tscn files in the project.
    """
    from godot_agent.godot.consistency_checker import check_consistency as _check, format_consistency_report
    root = Path(project_path) if project_path else _root()
    issues = _check(root)
    return {
        "issues": [{"file": i.file, "line": i.line, "severity": i.severity, "message": i.message} for i in issues],
        "error_count": sum(1 for i in issues if i.severity == "error"),
        "report": format_consistency_report(issues),
    }


# ─── Collision & Architecture Tools ──────────────────────────────

@mcp.tool()
def plan_collision(entities: list[str]) -> dict:
    """Generate standard collision layer/mask config for game entities.

    Standard scheme: Player=1, Enemy=2, Terrain=3, PlayerBullet=4, EnemyBullet=5, Pickup=6, Trigger=7, Interactable=8.

    Args:
        entities: List of entity types (e.g., ["player", "enemy", "player_bullet", "enemy_bullet"])
    """
    from godot_agent.godot.collision_planner import plan_game_collisions, format_collision_plan
    configs = plan_game_collisions(entities)
    return {
        "configs": [
            {"entity": c.entity_type, "layer": c.layer, "layer_bitmask": c.layer_bitmask,
             "mask_layers": c.mask_layers, "mask_bitmask": c.mask_bitmask, "gdscript": c.to_gdscript()}
            for c in configs
        ],
        "plan": format_collision_plan(configs),
    }


@mcp.tool()
def analyze_dependencies(project_path: str = "") -> dict:
    """Build a dependency graph of scenes, scripts, and resources in the project."""
    from godot_agent.godot.dependency_graph import build_dependency_graph
    root = Path(project_path) if project_path else _root()
    graph = build_dependency_graph(root)
    return {
        "node_count": len(graph.nodes),
        "main_scene": graph.main_scene,
        "autoloads": graph.autoloads,
        "orphans": graph.orphans(),
        "summary": graph.format_summary(),
    }


@mcp.tool()
def suggest_patterns(project_path: str = "") -> dict:
    """Analyze project scripts and suggest design patterns (object pool, component, state machine)."""
    from godot_agent.godot.pattern_advisor import analyze_project, format_advice
    root = Path(project_path) if project_path else _root()
    advice = analyze_project(root)
    return {
        "suggestions": [
            {"file": a.file, "pattern": a.pattern, "severity": a.severity, "message": a.message}
            for a in advice
        ],
        "report": format_advice(advice),
    }


# ─── Scene Tools ─────────────────────────────────────────────────

@mcp.tool()
def parse_scene(file_path: str) -> dict:
    """Parse a .tscn scene file and return its node tree, resources, and connections."""
    from godot_agent.godot.scene_parser import parse_tscn
    text = Path(file_path).read_text(errors="replace")
    scene = parse_tscn(text)
    return {
        "format": scene.format,
        "load_steps": scene.load_steps,
        "ext_resources": [{"type": r.type, "path": r.path, "id": r.id} for r in scene.ext_resources],
        "nodes": [
            {"name": n.name, "type": n.type, "parent": n.parent,
             "properties": n.properties}
            for n in scene.nodes
        ],
        "connections": [
            {"signal": c.signal, "from": c.from_node, "to": c.to_node, "method": c.method}
            for c in scene.connections
        ],
        "node_paths": scene.node_paths(),
    }


@mcp.tool()
def project_info(project_path: str = "") -> dict:
    """Read project.godot and return project name, version, autoloads, resolution, renderer."""
    from godot_agent.godot.project import parse_project_godot
    root = Path(project_path) if project_path else _root()
    proj = parse_project_godot(root / "project.godot")
    return {
        "name": proj.name,
        "version": proj.version,
        "main_scene": proj.main_scene,
        "viewport_width": proj.viewport_width,
        "viewport_height": proj.viewport_height,
        "renderer": proj.renderer,
        "autoloads": proj.autoloads,
    }


# ─── Knowledge Tools ─────────────────────────────────────────────

@mcp.tool()
def godot_knowledge(topic: str) -> dict:
    """Query the Godot 4.4 Playbook for best practices, patterns, and API references.

    Topics: collision, physics, signal, animation, ui, input, performance, resource, autoload, shader, navigation, etc.
    """
    from godot_agent.prompts.knowledge_selector import select_sections
    sections = select_sections(topic, max_sections=3)
    return {
        "sections": [{"title": t, "content": c} for t, c in sections],
        "topic": topic,
    }


# ─── Sprite Generation ───────────────────────────────────────────

@mcp.tool()
async def generate_sprite(
    subject: str,
    output_path: str,
    size: int = 32,
    style: str = "pixel_modern",
    facing: str = "front",
    category: str = "character",
    extra: str = "",
) -> dict:
    """Generate a pixel art sprite using AI with automatic post-processing.

    Pipeline: AI generation → chroma key (green → transparent) → auto-crop → nearest-neighbor resize.

    Args:
        subject: What to draw (e.g., "fire mage casting spell", "health potion")
        output_path: Where to save the PNG file
        size: Target pixel size (8, 16, 24, 32, 48, 64, 128)
        style: pixel_8bit, pixel_16bit, pixel_modern, chibi, minimal
        facing: front, left, right, back
        category: character, enemy, boss, item, projectile, ui_icon, effect
    """
    from godot_agent.tools.image_gen import GenerateSpriteTool
    tool = GenerateSpriteTool()
    result = await tool.execute(tool.Input(
        subject=subject, output_path=output_path, size=size,
        style=style, facing=facing, category=category, extra=extra,
    ))
    if result.error:
        return {"error": result.error}
    return {
        "path": result.output.path,
        "width": result.output.width,
        "height": result.output.height,
        "prompt_used": result.output.prompt_used,
    }


# ─── Resource Validation ─────────────────────────────────────────

@mcp.tool()
def validate_resources(file_path: str, project_path: str = "") -> dict:
    """Check that all ext_resource paths in a .tscn file actually exist on disk."""
    from godot_agent.godot.resource_validator import validate_resources as _validate
    root = Path(project_path) if project_path else _root()
    issues = _validate(Path(file_path), project_root=root)
    return {
        "valid": len(issues) == 0,
        "missing": issues,
    }


def run_mcp_server(project_path: str | None = None) -> None:
    """Entry point called by CLI: god-code mcp [--project PATH]"""
    if project_path:
        set_mcp_project_root(Path(project_path))
    mcp.run(transport="stdio")
