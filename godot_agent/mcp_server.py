"""MCP Server — exposes god-code's Godot tools to AI agents (Claude Code, Codex, etc).

Usage:
    god-code mcp --project /path/to/godot/project

Runs as a local stdio process. No backend server needed.
12 analysis tools + 8 write/execute tools = full game development capability.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

log = logging.getLogger(__name__)

mcp = FastMCP("god-code")

_project_root: Path | None = None


def set_mcp_project_root(path: Path) -> None:
    global _project_root
    _project_root = path.resolve()


def _root() -> Path:
    return _project_root or Path.cwd()


def _godot_path() -> str:
    config_file = Path.home() / ".config" / "god-code" / "config.json"
    if config_file.exists():
        return json.loads(config_file.read_text()).get("godot_path", "godot")
    return "godot"


async def _execute_tool(tool_cls, **kwargs) -> dict:
    tool = tool_cls()
    result = await tool.execute(tool.Input(**kwargs))
    if result.error:
        return {"error": result.error}
    if result.output is None:
        return {"ok": True}
    return result.output.model_dump() if hasattr(result.output, "model_dump") else dict(result.output)


# ═══════════════════════════════════════════════════════════════════
# ANALYSIS TOOLS (read-only, zero side effects)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def validate_project(project_path: str = "") -> dict:
    """Run Godot headless validation. Returns errors and warnings."""
    from godot_agent.runtime.error_loop import validate_project as _validate, format_validation_for_llm
    root = project_path or str(_root())
    result = await _validate(root, _godot_path(), timeout=30)
    return {
        "success": result.success,
        "errors": [{"file": e.file, "line": e.line, "message": e.message} for e in result.errors],
        "warnings": [{"file": w.file, "line": w.line, "message": w.message} for w in result.warnings],
        "summary": format_validation_for_llm(result),
    }


@mcp.tool()
def validate_tscn(file_path: str, auto_fix: bool = False) -> dict:
    """Validate .tscn format. Optionally auto-fix ordering issues (sub_resource before node, load_steps count)."""
    from godot_agent.godot.tscn_validator import validate_tscn as _validate, validate_and_fix
    text = Path(file_path).read_text(errors="replace")
    if auto_fix:
        fixed_text, issues = validate_and_fix(text)
        if fixed_text != text:
            Path(file_path).write_text(fixed_text)
        return {"fixed": fixed_text != text, "remaining_issues": [str(i) for i in issues]}
    issues = _validate(text)
    return {"issues": [str(i) for i in issues], "has_errors": any(i.severity == "error" for i in issues)}


@mcp.tool()
def lint_script(file_path: str) -> dict:
    """Lint GDScript for naming, ordering, type annotations, and anti-patterns."""
    from godot_agent.godot.gdscript_linter import lint_gdscript, format_lint_report
    text = Path(file_path).read_text(errors="replace")
    issues = lint_gdscript(text, filename=Path(file_path).name)
    return {
        "report": format_lint_report(issues, Path(file_path).name),
        "error_count": sum(1 for i in issues if i.severity == "error"),
        "warning_count": sum(1 for i in issues if i.severity == "warning"),
    }


@mcp.tool()
def check_consistency(project_path: str = "") -> dict:
    """Check cross-file consistency: collision layers, signals, resource paths, groups."""
    from godot_agent.godot.consistency_checker import check_consistency as _check, format_consistency_report
    root = Path(project_path) if project_path else _root()
    issues = _check(root)
    return {"report": format_consistency_report(issues), "error_count": sum(1 for i in issues if i.severity == "error")}


@mcp.tool()
def plan_collision(entities: list[str]) -> dict:
    """Generate standard collision layer/mask config. Entities: player, enemy, player_bullet, enemy_bullet, terrain, pickup, trigger, interactable."""
    from godot_agent.godot.collision_planner import plan_game_collisions, format_collision_plan
    configs = plan_game_collisions(entities)
    return {
        "configs": [{"entity": c.entity_type, "layer": c.layer, "bitmask": c.layer_bitmask,
                      "mask_layers": c.mask_layers, "mask_bitmask": c.mask_bitmask, "gdscript": c.to_gdscript()}
                     for c in configs],
        "plan": format_collision_plan(configs),
    }


@mcp.tool()
def analyze_dependencies(project_path: str = "") -> dict:
    """Build project dependency graph (scenes → scripts → resources)."""
    from godot_agent.godot.dependency_graph import build_dependency_graph
    graph = build_dependency_graph(Path(project_path) if project_path else _root())
    return {"summary": graph.format_summary(), "autoloads": graph.autoloads, "orphans": graph.orphans()}


@mcp.tool()
def suggest_patterns(project_path: str = "") -> dict:
    """Suggest design patterns: object pool, component, state machine."""
    from godot_agent.godot.pattern_advisor import analyze_project, format_advice
    advice = analyze_project(Path(project_path) if project_path else _root())
    return {"report": format_advice(advice), "count": len(advice)}


@mcp.tool()
def parse_scene(file_path: str) -> dict:
    """Parse .tscn into structured data: nodes, resources, connections, node paths."""
    from godot_agent.godot.scene_parser import parse_tscn
    scene = parse_tscn(Path(file_path).read_text(errors="replace"))
    return {
        "nodes": [{"name": n.name, "type": n.type, "parent": n.parent, "properties": n.properties} for n in scene.nodes],
        "ext_resources": [{"type": r.type, "path": r.path, "id": r.id} for r in scene.ext_resources],
        "connections": [{"signal": c.signal, "from": c.from_node, "to": c.to_node, "method": c.method} for c in scene.connections],
        "node_paths": scene.node_paths(),
    }


@mcp.tool()
def project_info(project_path: str = "") -> dict:
    """Read project.godot: name, version, autoloads, resolution, renderer."""
    from godot_agent.godot.project import parse_project_godot
    proj = parse_project_godot((Path(project_path) if project_path else _root()) / "project.godot")
    return {"name": proj.name, "version": proj.version, "main_scene": proj.main_scene,
            "resolution": f"{proj.viewport_width}x{proj.viewport_height}", "autoloads": proj.autoloads}


@mcp.tool()
def godot_knowledge(topic: str) -> dict:
    """Query Godot 4.4 Playbook. Topics: collision, physics, signal, animation, ui, input, performance, resource, autoload, shader, etc."""
    from godot_agent.prompts.knowledge_selector import select_sections
    sections = select_sections(topic, max_sections=3)
    return {"sections": [{"title": t, "content": c} for t, c in sections]}


@mcp.tool()
def validate_resources(file_path: str, project_path: str = "") -> dict:
    """Check all ext_resource paths in a .tscn exist on disk."""
    from godot_agent.godot.resource_validator import validate_resources as _validate
    issues = _validate(Path(file_path), project_root=Path(project_path) if project_path else _root())
    return {"valid": len(issues) == 0, "missing": issues}


@mcp.tool()
def plan_ui_layout(pattern: str) -> dict:
    """Generate a standard UI layout configuration. Patterns: hud_overlay, pause_menu, dialog_box, inventory_grid, title_screen, health_bar."""
    from godot_agent.godot.ui_layout_advisor import plan_ui_layout as _plan

    config = _plan(pattern)
    if config is None:
        return {"error": f"Unknown pattern: {pattern}"}
    return {"summary": config.describe(), "nodes": config.to_tscn_nodes(), "gdscript": config.to_gdscript()}


@mcp.tool()
def validate_ui_layout(file_path: str) -> dict:
    """Validate Control-based layout conventions in a .tscn scene."""
    from godot_agent.godot.scene_parser import parse_tscn
    from godot_agent.godot.ui_layout_advisor import validate_ui_layout as _validate

    scene = parse_tscn(Path(file_path).read_text(errors="replace"))
    warnings = _validate(scene)
    return {"warning_count": len(warnings), "warnings": warnings, "summary": "\n".join(warnings) if warnings else "No UI layout issues found."}


@mcp.tool()
def scaffold_audio(pattern: str = "standard", parent_node: str = ".") -> dict:
    """Generate audio node scaffolding. Patterns: minimal, standard, positional."""
    from godot_agent.godot.audio_scaffolder import scaffold_audio_nodes

    nodes = scaffold_audio_nodes(pattern, parent_node=parent_node)
    return {"summary": f"Audio scaffold {pattern}", "nodes": nodes}


@mcp.tool()
def validate_audio_nodes(file_path: str, project_path: str = "") -> dict:
    """Validate audio nodes and bus assignments in a .tscn scene."""
    from godot_agent.godot.audio_scaffolder import validate_audio_nodes as _validate
    from godot_agent.godot.scene_parser import parse_tscn

    root = Path(project_path) if project_path else _root()
    scene = parse_tscn(Path(file_path).read_text(errors="replace"))
    warnings = _validate(scene, root)
    return {"warning_count": len(warnings), "warnings": warnings, "summary": "\n".join(warnings) if warnings else "No audio node issues found."}


# ═══════════════════════════════════════════════════════════════════
# WRITE TOOLS (modify files with format protection)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
def write_scene(file_path: str, content: str) -> dict:
    """Write a .tscn file with automatic format validation and fix.

    Validates the content before writing. Auto-fixes sub_resource ordering and load_steps count.
    Use this instead of writing .tscn files directly to prevent format errors.
    """
    from godot_agent.godot.tscn_validator import validate_and_fix
    fixed_text, issues = validate_and_fix(content)
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        return {"written": False, "errors": [str(e) for e in errors]}
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    Path(file_path).write_text(fixed_text, encoding="utf-8")
    return {"written": True, "path": file_path, "auto_fixed": fixed_text != content,
            "warnings": [str(i) for i in issues if i.severity == "warning"]}


@mcp.tool()
def add_scene_node(file_path: str, parent: str, name: str, node_type: str,
                   properties: dict[str, object] | None = None) -> dict:
    """Add a node to an existing .tscn scene file.

    Args:
        file_path: Path to .tscn file
        parent: Parent node path ("." for root's child, "NodeName" for deeper)
        name: New node name (PascalCase)
        node_type: Godot node type (Node2D, Sprite2D, Area2D, Label, etc.)
        properties: Optional property dict (e.g., {"position": "Vector2(100, 200)"})
    """
    from godot_agent.godot.scene_writer import add_node
    from godot_agent.godot.tscn_validator import validate_and_fix
    text = Path(file_path).read_text(errors="replace")
    new_text = add_node(text, parent=parent, name=name, type=node_type, properties=properties)
    fixed, issues = validate_and_fix(new_text)
    Path(file_path).write_text(fixed, encoding="utf-8")
    return {"added": True, "node": f"{name} ({node_type})", "parent": parent,
            "warnings": [str(i) for i in issues if i.severity == "warning"]}


@mcp.tool()
def set_scene_property(file_path: str, node_name: str, key: str, value: object) -> dict:
    """Set or update a property on a node in a .tscn file.

    Args:
        file_path: Path to .tscn file
        node_name: Name of the node to modify
        key: Property name (e.g., "position", "text", "color", "visible")
        value: Property value as Godot string (e.g., "Vector2(10, 20)", '"Hello"', "true")
    """
    from godot_agent.godot.scene_writer import set_node_property
    text = Path(file_path).read_text(errors="replace")
    new_text = set_node_property(text, node_name=node_name, key=key, value=value)
    Path(file_path).write_text(new_text, encoding="utf-8")
    return {"set": True, "node": node_name, "property": f"{key} = {value}"}


@mcp.tool()
def add_signal_connection(file_path: str, signal_name: str, from_node: str,
                          to_node: str, method: str) -> dict:
    """Add a signal connection to a .tscn file.

    Args:
        signal_name: Signal name (e.g., "pressed", "body_entered", "timeout")
        from_node: Source node path
        to_node: Target node path
        method: Handler method name (e.g., "_on_button_pressed")
    """
    from godot_agent.godot.scene_writer import add_connection
    text = Path(file_path).read_text(errors="replace")
    new_text = add_connection(text, signal_name=signal_name, from_node=from_node,
                              to_node=to_node, method=method)
    Path(file_path).write_text(new_text, encoding="utf-8")
    return {"connected": True, "signal": signal_name, "from": from_node, "to": to_node, "method": method}


@mcp.tool()
def write_script(file_path: str, content: str, lint: bool = True) -> dict:
    """Write a GDScript file with optional lint validation.

    Use this instead of writing .gd files directly. Runs the linter and returns issues.
    """
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    Path(file_path).write_text(content, encoding="utf-8")
    result = {"written": True, "path": file_path}
    if lint:
        from godot_agent.godot.gdscript_linter import lint_gdscript
        issues = lint_gdscript(content, filename=Path(file_path).name)
        result["lint_errors"] = sum(1 for i in issues if i.severity == "error")
        result["lint_warnings"] = sum(1 for i in issues if i.severity == "warning")
        if issues:
            result["lint_issues"] = [str(i) for i in issues[:10]]
    return result


# ═══════════════════════════════════════════════════════════════════
# EXECUTION TOOLS (run Godot, take screenshots)
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def run_gut_tests(test_script: str = "", project_path: str = "") -> dict:
    """Run GUT tests in headless mode. Returns pass/fail results.

    Args:
        test_script: Specific test script (e.g., "res://tests/test_battle.gd"). Empty = run all.
        project_path: Godot project root. Empty = use configured root.
    """
    import asyncio
    from godot_agent.tools.godot_cli import build_gut_command, parse_godot_output
    root = project_path or str(_root())
    cmd = build_gut_command(_godot_path(), test_script or None)
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=root)
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    output = stdout.decode(errors="replace") + "\n" + stderr.decode(errors="replace")
    report = parse_godot_output(output)
    return {
        "exit_code": proc.returncode or 0,
        "passed": proc.returncode == 0,
        "errors": [{"file": e.file, "line": e.line, "message": e.message} for e in report.errors],
        "output_tail": output[-500:],
    }


@mcp.tool()
async def screenshot_scene(
    scene_path: str,
    output_path: str = "",
    delay_ms: int = 1000,
    project_path: str = "",
    artifact_name: str = "",
    headless: bool = False,
    include_base64: bool = True,
    godot_path: str = "",
) -> dict:
    """Take a screenshot of a Godot scene via the shared ScreenshotTool.

    Defaults to windowed rendering on desktop platforms for reliable viewport capture.
    """
    from godot_agent.tools.screenshot import ScreenshotTool

    root = project_path or str(_root())
    return await _execute_tool(
        ScreenshotTool,
        scene_path=scene_path,
        godot_path=godot_path or _godot_path(),
        project_path=root,
        output_path=output_path,
        artifact_name=artifact_name or (Path(scene_path).stem or "scene"),
        headless=headless,
        include_base64=include_base64,
        delay_ms=delay_ms,
    )


@mcp.tool()
async def get_runtime_snapshot(project_path: str = "") -> dict:
    """Read the latest runtime snapshot, including state, fixtures, tick, and recent events."""
    from godot_agent.tools.editor_bridge import GetRuntimeSnapshotTool

    root = project_path or str(_root())
    return await _execute_tool(GetRuntimeSnapshotTool, project_path=root)


@mcp.tool()
async def run_playtest(project_path: str = "", changed_files: list[str] | None = None) -> dict:
    """Run the scenario-based playtest harness against the latest runtime snapshot."""
    from godot_agent.tools.editor_bridge import RunPlaytestTool

    root = project_path or str(_root())
    return await _execute_tool(RunPlaytestTool, project_path=root, changed_files=changed_files or [])


@mcp.tool()
async def run_scripted_playtest(
    project_path: str = "",
    scenario_ids: list[str] | None = None,
    changed_files: list[str] | None = None,
    run_all: bool = False,
) -> dict:
    """Run scripted-route playtest contracts against the current runtime evidence."""
    from godot_agent.tools.editor_bridge import RunScriptedPlaytestTool

    root = project_path or str(_root())
    return await _execute_tool(
        RunScriptedPlaytestTool,
        project_path=root,
        scenario_ids=scenario_ids or [],
        changed_files=changed_files or [],
        run_all=run_all,
    )


@mcp.tool()
async def list_scenarios(project_path: str = "", include_generated: bool = False) -> dict:
    """List playtest scenarios and mark which ones match the current project profile."""
    from godot_agent.tools.editor_bridge import ListScenariosTool

    root = project_path or str(_root())
    return await _execute_tool(ListScenariosTool, project_path=root, include_generated=include_generated)


@mcp.tool()
async def list_contracts(
    project_path: str = "",
    scenario_id: str = "",
    include_generated: bool = False,
    show_all: bool = False,
) -> dict:
    """List detailed scenario contracts for the current gameplay profile or a specific scenario id."""
    from godot_agent.tools.editor_bridge import ListContractsTool

    root = project_path or str(_root())
    return await _execute_tool(
        ListContractsTool,
        project_path=root,
        scenario_id=scenario_id,
        include_generated=include_generated,
        show_all=show_all,
    )


@mcp.tool()
async def load_scene(scene_path: str) -> dict:
    """Set the active scene in the runtime harness."""
    from godot_agent.tools.runtime_harness import LoadSceneTool

    return await _execute_tool(LoadSceneTool, scene_path=scene_path)


@mcp.tool()
async def set_fixture(name: str, payload: dict | None = None) -> dict:
    """Attach deterministic fixture data to the runtime harness."""
    from godot_agent.tools.runtime_harness import SetFixtureTool

    return await _execute_tool(SetFixtureTool, name=name, payload=payload or {})


@mcp.tool()
async def press_action(action: str, pressed: bool = True) -> dict:
    """Record a gameplay/UI action in the runtime harness."""
    from godot_agent.tools.runtime_harness import PressActionTool

    return await _execute_tool(PressActionTool, action=action, pressed=pressed)


@mcp.tool()
async def advance_ticks(count: int = 1, state_updates: dict | None = None, events: list[dict] | None = None) -> dict:
    """Advance the runtime harness by a number of physics ticks."""
    from godot_agent.tools.runtime_harness import AdvanceTicksTool

    return await _execute_tool(
        AdvanceTicksTool,
        count=count,
        state_updates=state_updates or {},
        events=events or [],
    )


@mcp.tool()
async def get_runtime_state(project_path: str = "") -> dict:
    """Read the runtime harness state, fixtures, active inputs, and current tick."""
    from godot_agent.tools.runtime_harness import GetRuntimeStateTool

    root = project_path or str(_root())
    return await _execute_tool(GetRuntimeStateTool, project_path=root)


@mcp.tool()
async def get_events_since(tick: int = 0) -> dict:
    """Read runtime events emitted after a specific tick."""
    from godot_agent.tools.runtime_harness import GetEventsSinceTool

    return await _execute_tool(GetEventsSinceTool, tick=tick)


@mcp.tool()
async def capture_viewport(
    project_path: str = "",
    scene_path: str = "",
    godot_path: str = "",
    output_path: str = "",
    artifact_name: str = "viewport",
    delay_ms: int = 1000,
) -> dict:
    """Persist a viewport screenshot artifact, reusing a runtime screenshot when available."""
    from godot_agent.tools.runtime_harness import CaptureViewportTool

    root = project_path or str(_root())
    return await _execute_tool(
        CaptureViewportTool,
        project_path=root,
        scene_path=scene_path,
        godot_path=godot_path or _godot_path(),
        output_path=output_path,
        artifact_name=artifact_name,
        delay_ms=delay_ms,
    )


@mcp.tool()
async def compare_baseline(
    baseline_id: str,
    actual_path: str,
    project_path: str = "",
    tolerance: int = 0,
    region: list[int] | None = None,
    create_baseline: bool = False,
) -> dict:
    """Compare a screenshot or sprite artifact against a stored baseline."""
    from godot_agent.tools.runtime_harness import CompareBaselineTool

    root = project_path or str(_root())
    return await _execute_tool(
        CompareBaselineTool,
        project_path=root,
        actual_path=actual_path,
        baseline_id=baseline_id,
        tolerance=tolerance,
        region=region or [],
        create_baseline=create_baseline,
    )


@mcp.tool()
async def report_failure(
    test_id: str,
    project_path: str = "",
    scene: str = "",
    step: str = "",
    reason: str = "",
    ui_state: dict | None = None,
    image_assert: dict | None = None,
    artifacts: dict | None = None,
    details: dict | None = None,
) -> dict:
    """Write a structured failure bundle to the artifact directory."""
    from godot_agent.tools.runtime_harness import ReportFailureTool

    root = project_path or str(_root())
    return await _execute_tool(
        ReportFailureTool,
        project_path=root,
        test_id=test_id,
        scene=scene,
        step=step,
        reason=reason,
        ui_state=ui_state or {},
        image_assert=image_assert or {},
        artifacts=artifacts or {},
        details=details or {},
    )


@mcp.tool()
async def run_scene(scene_path: str = "", project_path: str = "", timeout_seconds: int = 5) -> dict:
    """Run a Godot scene briefly to verify it loads without errors.

    Args:
        scene_path: res:// path. Empty = main scene from project.godot.
        timeout_seconds: How long to let it run before stopping (default 5).
    """
    import asyncio
    root = project_path or str(_root())
    cmd = [_godot_path(), "--headless"]
    if scene_path:
        cmd.extend(["--scene", scene_path])
    cmd.append("--quit-after")
    cmd.append(str(timeout_seconds))

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=root)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds + 10)
        output = stdout.decode(errors="replace") + "\n" + stderr.decode(errors="replace")
    except asyncio.TimeoutError:
        proc.kill()
        output = "Timed out"

    from godot_agent.runtime.error_loop import parse_godot_output
    errors = parse_godot_output(output)
    return {
        "loaded": not any(e.level == "ERROR" for e in errors),
        "errors": [{"file": e.file, "line": e.line, "message": e.message} for e in errors if e.level == "ERROR"],
        "exit_code": proc.returncode,
    }


# ═══════════════════════════════════════════════════════════════════
# SPRITE GENERATION
# ═══════════════════════════════════════════════════════════════════

@mcp.tool()
async def generate_sprite(
    subject: str, output_path: str, size: int = 32, style: str = "pixel_modern",
    facing: str = "front", category: str = "character", extra: str = "",
) -> dict:
    """Generate pixel art sprite with AI. Pipeline: generate → chroma key → crop → resize.

    Args:
        subject: What to draw (e.g., "fire mage", "health potion", "slime enemy")
        output_path: Where to save PNG
        size: Pixel size (8/16/24/32/48/64/128)
        style: pixel_8bit, pixel_16bit, pixel_modern, chibi, minimal
        facing: front, left, right, back
        category: character, enemy, boss, item, projectile, ui_icon, effect
    """
    from godot_agent.tools.image_gen import GenerateSpriteTool
    tool = GenerateSpriteTool()
    result = await tool.execute(tool.Input(
        subject=subject, output_path=output_path, size=size,
        style=style, facing=facing, category=category, extra=extra))
    if result.error:
        return {"error": result.error}
    return {"path": result.output.path, "width": result.output.width,
            "height": result.output.height, "prompt_used": result.output.prompt_used}


@mcp.tool()
async def slice_sprite_sheet(
    input_path: str,
    output_dir: str,
    frame_width: int,
    frame_height: int,
    columns: int = 0,
    rows: int = 0,
    prefix: str = "frame",
    chroma_key: str = "#00FF00",
    tolerance: int = 60,
    trim: bool = False,
    metadata_path: str = "",
) -> dict:
    """Slice a sprite sheet into transparent PNG frames and emit manifest metadata."""
    from godot_agent.tools.runtime_harness import SliceSpriteSheetTool

    return await _execute_tool(
        SliceSpriteSheetTool,
        input_path=input_path,
        output_dir=output_dir,
        frame_width=frame_width,
        frame_height=frame_height,
        columns=columns,
        rows=rows,
        prefix=prefix,
        chroma_key=chroma_key,
        tolerance=tolerance,
        trim=trim,
        metadata_path=metadata_path,
    )


@mcp.tool()
async def validate_sprite_imports(
    project_path: str = "",
    metadata_path: str = "",
    sprite_dir: str = "",
    smoke_scene_path: str = "",
    smoke_baseline_id: str = "",
    smoke_tolerance: int = 0,
    create_baseline: bool = False,
) -> dict:
    """Validate sliced sprite frames or a manifest, with optional smoke screenshot and baseline compare."""
    from godot_agent.tools.runtime_harness import ValidateSpriteImportsTool

    root = project_path or str(_root())
    return await _execute_tool(
        ValidateSpriteImportsTool,
        project_path=root,
        metadata_path=metadata_path,
        sprite_dir=sprite_dir,
        smoke_scene_path=smoke_scene_path,
        smoke_baseline_id=smoke_baseline_id,
        smoke_tolerance=smoke_tolerance,
        create_baseline=create_baseline,
    )


def run_mcp_server(project_path: str | None = None) -> None:
    """Entry point: god-code mcp [--project PATH]"""
    if project_path:
        set_mcp_project_root(Path(project_path))
    mcp.run(transport="stdio")
