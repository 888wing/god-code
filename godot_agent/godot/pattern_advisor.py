"""Advises on Godot design patterns based on project analysis.

Detects anti-patterns and suggests improvements from Playbook Section 14:
- Object Pool for frequently spawned entities
- Component Pattern for complex entities
- State Machine for multi-state behavior
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PatternAdvice:
    file: str
    pattern: str  # "object_pool", "component", "state_machine"
    severity: str  # "suggestion", "recommended", "critical"
    message: str
    example: str = ""


def analyze_project(project_root: Path) -> list[PatternAdvice]:
    """Analyze project scripts and suggest design patterns."""
    advice: list[PatternAdvice] = []

    for gd_file in project_root.rglob("*.gd"):
        if ".godot" in str(gd_file):
            continue
        rel = str(gd_file.relative_to(project_root))
        try:
            text = gd_file.read_text(errors="replace")
        except Exception:
            continue

        _check_object_pool(rel, text, advice)
        _check_component_pattern(rel, text, advice)
        _check_state_machine(rel, text, advice)
        _check_script_size(rel, text, advice)

    return advice


def _check_object_pool(file: str, text: str, advice: list[PatternAdvice]) -> None:
    """Detect frequent instantiate+queue_free patterns that need pooling."""
    instantiate_count = len(re.findall(r'\.instantiate\(\)', text))
    queue_free_count = len(re.findall(r'queue_free\(\)', text))

    if instantiate_count >= 3 and queue_free_count >= 1:
        advice.append(PatternAdvice(
            file=file,
            pattern="object_pool",
            severity="recommended" if instantiate_count >= 5 else "suggestion",
            message=f"Found {instantiate_count} instantiate() calls and {queue_free_count} queue_free(). "
                    f"Consider Object Pool pattern to reduce allocation overhead.",
            example="""class_name ObjectPool extends Node
@export var scene: PackedScene
@export var pool_size: int = 20
var _pool: Array[Node] = []

func _ready():
    for i in pool_size:
        var inst := scene.instantiate()
        inst.set_process(false); inst.hide()
        add_child(inst); _pool.append(inst)

func get_instance() -> Node:
    for obj in _pool:
        if not obj.visible:
            obj.show(); obj.set_process(true)
            return obj
    var inst := scene.instantiate()
    add_child(inst); _pool.append(inst)
    return inst"""
        ))


def _check_component_pattern(file: str, text: str, advice: list[PatternAdvice]) -> None:
    """Detect monolithic scripts that should use Component pattern."""
    lines = text.splitlines()
    func_count = sum(1 for l in lines if re.match(r'^func\s', l.strip()))
    var_count = sum(1 for l in lines if re.match(r'^var\s', l.strip()))

    # Detect multiple responsibility indicators
    has_health = bool(re.search(r'(hp|health|damage|hit|die|dead)', text, re.IGNORECASE))
    has_movement = bool(re.search(r'(velocity|speed|move|position\s*[+\-]=)', text, re.IGNORECASE))
    has_shooting = bool(re.search(r'(shoot|fire|bullet|projectile|spawn)', text, re.IGNORECASE))
    has_ai = bool(re.search(r'(target|patrol|chase|state|ai)', text, re.IGNORECASE))

    responsibilities = sum([has_health, has_movement, has_shooting, has_ai])

    if responsibilities >= 3 and len(lines) > 100:
        advice.append(PatternAdvice(
            file=file,
            pattern="component",
            severity="recommended",
            message=f"Script has {responsibilities} responsibilities ({len(lines)} lines, {func_count} functions). "
                    f"Consider splitting into Component nodes: HealthComponent, MovementComponent, etc.",
        ))


def _check_state_machine(file: str, text: str, advice: list[PatternAdvice]) -> None:
    """Detect complex state logic that should use State Machine pattern."""
    # Count match/if chains on state-like variables
    state_matches = len(re.findall(r'match\s+(state|phase|mode|current_state)', text))
    state_ifs = len(re.findall(r'if\s+(state|phase|mode|current_state)\s*==', text))

    total = state_matches + state_ifs
    if total >= 3:
        advice.append(PatternAdvice(
            file=file,
            pattern="state_machine",
            severity="suggestion" if total < 5 else "recommended",
            message=f"Found {total} state/phase checks. Consider a formal State Machine pattern "
                    f"with separate State nodes for each state.",
        ))


def _check_script_size(file: str, text: str, advice: list[PatternAdvice]) -> None:
    """Warn about oversized scripts."""
    lines = text.splitlines()
    if len(lines) > 200:
        advice.append(PatternAdvice(
            file=file,
            pattern="component",
            severity="recommended",
            message=f"Script is {len(lines)} lines (>200). Consider splitting into sub-scenes or utility classes.",
        ))
    elif len(lines) > 150:
        advice.append(PatternAdvice(
            file=file,
            pattern="component",
            severity="suggestion",
            message=f"Script is {len(lines)} lines. Approaching the 200-line threshold for splitting.",
        ))


def format_advice(advice: list[PatternAdvice]) -> str:
    """Format pattern advice for display."""
    if not advice:
        return "No design pattern suggestions — project structure looks good."

    lines = ["## Design Pattern Suggestions", ""]
    by_severity = {"critical": [], "recommended": [], "suggestion": []}
    for a in advice:
        by_severity.get(a.severity, []).append(a)

    for sev in ["critical", "recommended", "suggestion"]:
        items = by_severity[sev]
        if not items:
            continue
        lines.append(f"### {sev.title()}")
        for a in items:
            lines.append(f"- **{a.file}** [{a.pattern}]: {a.message}")
            if a.example:
                lines.append(f"  ```gdscript\n  {a.example}\n  ```")
        lines.append("")

    return "\n".join(lines)
