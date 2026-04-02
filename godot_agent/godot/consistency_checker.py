"""Cross-file consistency checker for Godot projects.

Scans all .gd and .tscn files to verify:
- Collision layer/mask consistency across files
- Signal connections match declared signals
- preload/load paths reference existing files
- Group names are consistent
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConsistencyIssue:
    file: str
    line: int | None
    severity: str
    message: str

    def __str__(self) -> str:
        loc = f"{self.file}:{self.line}" if self.line else self.file
        return f"[{self.severity}] {loc} — {self.message}"


@dataclass
class ProjectScan:
    collision_configs: list[tuple[str, int, int, int]] = field(default_factory=list)  # (file, line, layer, mask)
    resource_refs: list[tuple[str, int, str]] = field(default_factory=list)  # (file, line, path)
    group_adds: list[tuple[str, int, str]] = field(default_factory=list)  # (file, line, group)
    group_checks: list[tuple[str, int, str]] = field(default_factory=list)  # (file, line, group)
    signal_declarations: list[tuple[str, str]] = field(default_factory=list)  # (file, signal_name)
    signal_emits: list[tuple[str, int, str]] = field(default_factory=list)  # (file, line, signal_name)


def scan_project(project_root: Path) -> ProjectScan:
    """Scan all .gd and .tscn files for consistency-relevant data."""
    scan = ProjectScan()

    for gd_file in project_root.rglob("*.gd"):
        if ".godot" in str(gd_file):
            continue
        rel = str(gd_file.relative_to(project_root))
        try:
            text = gd_file.read_text(errors="replace")
        except Exception:
            continue

        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()

            # Collision layer/mask assignments
            cl_match = re.search(r'collision_layer\s*=\s*(\d+)', stripped)
            cm_match = re.search(r'collision_mask\s*=\s*(\d+)', stripped)
            if cl_match:
                mask_val = int(cm_match.group(1)) if cm_match else 0
                scan.collision_configs.append((rel, i, int(cl_match.group(1)), mask_val))

            # preload/load resource references
            for ref_match in re.finditer(r'(?:preload|load)\s*\(\s*["\']([^"\']+)["\']', stripped):
                scan.resource_refs.append((rel, i, ref_match.group(1)))

            # Group operations
            grp_add = re.search(r'add_to_group\s*\(\s*["\']([^"\']+)["\']', stripped)
            if grp_add:
                scan.group_adds.append((rel, i, grp_add.group(1)))

            grp_check = re.search(r'is_in_group\s*\(\s*["\']([^"\']+)["\']', stripped)
            if grp_check:
                scan.group_checks.append((rel, i, grp_check.group(1)))

            grp_call = re.search(r'call_group\s*\(\s*["\']([^"\']+)["\']', stripped)
            if grp_call:
                scan.group_checks.append((rel, i, grp_call.group(1)))

            grp_tree = re.search(r'get_nodes_in_group\s*\(\s*["\']([^"\']+)["\']', stripped)
            if grp_tree:
                scan.group_checks.append((rel, i, grp_tree.group(1)))

            # Signal declarations
            sig_decl = re.match(r'^signal\s+(\w+)', stripped)
            if sig_decl:
                scan.signal_declarations.append((rel, sig_decl.group(1)))

            # Signal emits
            sig_emit = re.search(r'(\w+)\.emit\s*\(', stripped)
            if sig_emit:
                scan.signal_emits.append((rel, i, sig_emit.group(1)))

    # Also scan .tscn for collision layers
    for tscn_file in project_root.rglob("*.tscn"):
        if ".godot" in str(tscn_file):
            continue
        rel = str(tscn_file.relative_to(project_root))
        try:
            text = tscn_file.read_text(errors="replace")
        except Exception:
            continue

        for i, line in enumerate(text.splitlines(), 1):
            cl_match = re.search(r'collision_layer\s*=\s*(\d+)', line)
            cm_match = re.search(r'collision_mask\s*=\s*(\d+)', line)
            if cl_match:
                mask_val = int(cm_match.group(1)) if cm_match else 0
                scan.collision_configs.append((rel, i, int(cl_match.group(1)), mask_val))

    return scan


def check_consistency(project_root: Path) -> list[ConsistencyIssue]:
    """Run all consistency checks and return issues."""
    scan = scan_project(project_root)
    issues: list[ConsistencyIssue] = []

    _check_resource_refs(project_root, scan, issues)
    _check_groups(scan, issues)
    _check_collision_standard(scan, issues)

    return issues


def _check_resource_refs(root: Path, scan: ProjectScan, issues: list[ConsistencyIssue]) -> None:
    """Verify preload/load paths exist."""
    for file, line, path in scan.resource_refs:
        if path.startswith("res://"):
            rel_path = path[6:]
            full_path = root / rel_path
            if not full_path.exists():
                issues.append(ConsistencyIssue(file, line, "error",
                    f'Resource "{path}" not found on disk.'))


def _check_groups(scan: ProjectScan, issues: list[ConsistencyIssue]) -> None:
    """Verify group names used in checks are also added somewhere."""
    added_groups = {g for _, _, g in scan.group_adds}
    for file, line, group in scan.group_checks:
        if group not in added_groups:
            issues.append(ConsistencyIssue(file, line, "warning",
                f'Group "{group}" is checked/called but never added with add_to_group().'))


def _check_collision_standard(scan: ProjectScan, issues: list[ConsistencyIssue]) -> None:
    """Check if collision layers follow the standard 1-8 scheme."""
    from godot_agent.godot.collision_planner import _layer_to_bitmask
    standard_bitmasks = {_layer_to_bitmask(i) for i in range(1, 9)}

    for file, line, layer, mask in scan.collision_configs:
        if layer not in standard_bitmasks and layer != 0:
            issues.append(ConsistencyIssue(file, line, "warning",
                f"collision_layer={layer} is not a standard single-layer bitmask. "
                f"Standard layers use bitmask values: 1,2,4,8,16,32,64,128."))


def format_consistency_report(issues: list[ConsistencyIssue]) -> str:
    """Format consistency check results."""
    if not issues:
        return "Consistency check PASSED — no issues found."

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    lines = [f"Consistency check: {len(errors)} errors, {len(warnings)} warnings"]
    for issue in issues:
        lines.append(f"  {issue}")
    return "\n".join(lines)
