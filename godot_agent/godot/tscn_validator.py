"""Validates .tscn files before writing to prevent common format errors.

Catches issues that Godot would reject at load time:
- sub_resource after node (most common error)
- load_steps mismatch
- duplicate node names at same parent level
- missing ext_resource references
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class TscnIssue:
    line: int
    severity: str  # "error" or "warning"
    message: str

    def __str__(self) -> str:
        return f"L{self.line} [{self.severity}] {self.message}"


def validate_tscn(text: str) -> list[TscnIssue]:
    """Validate .tscn text and return list of issues."""
    issues: list[TscnIssue] = []
    lines = text.splitlines()

    first_node_line: int | None = None
    last_sub_resource_line: int | None = None
    ext_resource_count = 0
    sub_resource_count = 0
    declared_load_steps: int | None = None
    ext_resource_ids: set[str] = set()
    referenced_ext_ids: set[str] = set()
    node_names_by_parent: dict[str, list[str]] = {}

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue

        # gd_scene header
        header_match = re.match(r'^\[gd_scene\s+(.*)\]$', stripped)
        if header_match:
            attrs = header_match.group(1)
            ls_match = re.search(r'load_steps=(\d+)', attrs)
            if ls_match:
                declared_load_steps = int(ls_match.group(1))

        # ext_resource
        if stripped.startswith("[ext_resource"):
            ext_resource_count += 1
            id_match = re.search(r'id="([^"]+)"', stripped)
            if id_match:
                ext_resource_ids.add(id_match.group(1))
            if first_node_line is not None:
                issues.append(TscnIssue(i, "error",
                    "ext_resource declared after first node. Must be before all nodes."))

        # sub_resource
        if stripped.startswith("[sub_resource"):
            sub_resource_count += 1
            last_sub_resource_line = i
            if first_node_line is not None:
                issues.append(TscnIssue(i, "error",
                    "sub_resource declared after first node. Must be before all nodes."))

        # node
        node_match = re.match(r'^\[node\s+(.*)\]$', stripped)
        if node_match:
            if first_node_line is None:
                first_node_line = i
            attrs = node_match.group(1)
            name_match = re.search(r'name="([^"]+)"', attrs)
            parent_match = re.search(r'parent="([^"]*)"', attrs)
            if name_match:
                name = name_match.group(1)
                parent = parent_match.group(1) if parent_match else "__root__"
                if parent not in node_names_by_parent:
                    node_names_by_parent[parent] = []
                if name in node_names_by_parent[parent]:
                    issues.append(TscnIssue(i, "error",
                        f'Duplicate node name "{name}" under parent "{parent}".'))
                node_names_by_parent[parent].append(name)

        # Track ExtResource references
        for ref_match in re.finditer(r'ExtResource\("([^"]+)"\)', stripped):
            referenced_ext_ids.add(ref_match.group(1))

    # Validate load_steps
    expected_steps = ext_resource_count + sub_resource_count + 1
    if declared_load_steps is not None and declared_load_steps != expected_steps:
        issues.append(TscnIssue(1, "warning",
            f"load_steps={declared_load_steps} but expected {expected_steps} "
            f"({ext_resource_count} ext + {sub_resource_count} sub + 1)."))

    # Check for unreferenced ext_resources (warning only)
    unreferenced = ext_resource_ids - referenced_ext_ids
    for uid in unreferenced:
        issues.append(TscnIssue(0, "warning",
            f'ext_resource id="{uid}" declared but never referenced.'))

    # Check for referenced but undeclared ext_resources
    undeclared = referenced_ext_ids - ext_resource_ids
    for uid in undeclared:
        issues.append(TscnIssue(0, "error",
            f'ExtResource("{uid}") used but not declared in ext_resource section.'))

    return issues


def validate_and_fix(text: str) -> tuple[str, list[TscnIssue]]:
    """Validate and attempt auto-fix of common issues. Returns (fixed_text, remaining_issues)."""
    issues = validate_tscn(text)
    has_ordering_error = any(
        "declared after first node" in i.message for i in issues if i.severity == "error"
    )

    if not has_ordering_error:
        return text, issues

    # Auto-fix: reorder sections
    lines = text.splitlines(keepends=True)
    header_lines: list[str] = []
    ext_lines: list[str] = []
    sub_lines: list[str] = []
    node_lines: list[str] = []
    connection_lines: list[str] = []

    current_section = "header"
    current_block: list[str] = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("[gd_scene"):
            _flush_block(current_block, current_section, header_lines, ext_lines, sub_lines, node_lines, connection_lines)
            current_section = "header"
            current_block = [line]
        elif stripped.startswith("[ext_resource"):
            _flush_block(current_block, current_section, header_lines, ext_lines, sub_lines, node_lines, connection_lines)
            current_section = "ext"
            current_block = [line]
        elif stripped.startswith("[sub_resource"):
            _flush_block(current_block, current_section, header_lines, ext_lines, sub_lines, node_lines, connection_lines)
            current_section = "sub"
            current_block = [line]
        elif stripped.startswith("[node"):
            _flush_block(current_block, current_section, header_lines, ext_lines, sub_lines, node_lines, connection_lines)
            current_section = "node"
            current_block = [line]
        elif stripped.startswith("[connection"):
            _flush_block(current_block, current_section, header_lines, ext_lines, sub_lines, node_lines, connection_lines)
            current_section = "connection"
            current_block = [line]
        else:
            current_block.append(line)

    _flush_block(current_block, current_section, header_lines, ext_lines, sub_lines, node_lines, connection_lines)

    fixed = "".join(header_lines + ext_lines + sub_lines + node_lines + connection_lines)

    # Recount load_steps
    ext_count = sum(1 for l in ext_lines if "[ext_resource" in l)
    sub_count = sum(1 for l in sub_lines if "[sub_resource" in l)
    expected = ext_count + sub_count + 1
    fixed = re.sub(r'load_steps=\d+', f'load_steps={expected}', fixed, count=1)

    remaining = validate_tscn(fixed)
    return fixed, remaining


def _flush_block(
    block: list[str], section: str,
    header: list[str], ext: list[str], sub: list[str],
    node: list[str], connection: list[str],
) -> None:
    if not block:
        return
    target = {"header": header, "ext": ext, "sub": sub, "node": node, "connection": connection}
    target.get(section, header).extend(block)
    block.clear()
