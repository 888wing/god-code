"""Lightweight GDScript linter based on Playbook Section 3.

Checks code ordering, naming conventions, type annotations,
and common anti-patterns. Does NOT parse AST — uses regex patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class LintIssue:
    line: int
    severity: str  # "error", "warning", "info"
    rule: str
    message: str

    def __str__(self) -> str:
        return f"L{self.line} [{self.severity}] {self.rule}: {self.message}"


# Expected declaration order (Playbook 3.2)
_SECTION_ORDER = [
    "tool", "class_name", "extends", "doccomment",
    "signal", "enum", "const", "static_var",
    "export_var", "var", "onready_var",
    "lifecycle", "public_method", "private_method",
]


def lint_gdscript(text: str, filename: str = "") -> list[LintIssue]:
    """Lint GDScript source text. Returns list of issues sorted by line."""
    issues: list[LintIssue] = []
    lines = text.splitlines()

    _check_naming(lines, filename, issues)
    _check_ordering(lines, issues)
    _check_type_annotations(lines, issues)
    _check_antipatterns(lines, issues)

    issues.sort(key=lambda i: i.line)
    return issues


def _check_naming(lines: list[str], filename: str, issues: list[LintIssue]) -> None:
    """Check naming conventions (Playbook 3.1)."""
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Signal should be past tense (heuristic: ends with common verb suffixes)
        sig_match = re.match(r'^signal\s+(\w+)', stripped)
        if sig_match:
            name = sig_match.group(1)
            # Warn if signal looks like present tense verb
            if name.startswith(("do_", "run_", "start_", "open_", "close_")):
                issues.append(LintIssue(i, "warning", "signal-naming",
                    f'Signal "{name}" should use past tense (e.g., "{name}ed" or "{name}_completed").'))

        # Function naming
        func_match = re.match(r'^func\s+(\w+)', stripped)
        if func_match:
            name = func_match.group(1)
            if name != name.lower() and not name.startswith("_"):
                # Might be PascalCase
                if re.match(r'^[A-Z]', name):
                    issues.append(LintIssue(i, "warning", "func-naming",
                        f'Function "{name}" should be snake_case.'))

        # Variable naming
        var_match = re.match(r'^(?:var|const)\s+(\w+)', stripped)
        if var_match:
            name = var_match.group(1)
            if stripped.startswith("const") and name != name.upper() and not name.startswith("_"):
                if not re.match(r'^[A-Z][a-zA-Z]+$', name):  # Allow PascalCase for scene consts
                    issues.append(LintIssue(i, "info", "const-naming",
                        f'Constant "{name}" should be CONSTANT_CASE.'))


def _check_ordering(lines: list[str], issues: list[LintIssue]) -> None:
    """Check code section ordering (Playbook 3.2)."""
    last_section_idx = -1
    last_section_name = ""

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        section = _classify_line(stripped)
        if section is None:
            continue

        try:
            section_idx = _SECTION_ORDER.index(section)
        except ValueError:
            continue

        if section_idx < last_section_idx:
            issues.append(LintIssue(i, "warning", "code-order",
                f'"{section}" appears after "{last_section_name}". '
                f'Expected order: signals → enums → consts → exports → vars → @onready → lifecycle → methods.'))

        if section_idx >= last_section_idx:
            last_section_idx = section_idx
            last_section_name = section


def _classify_line(line: str) -> str | None:
    """Classify a line into its section category."""
    if line.startswith("@tool"): return "tool"
    if line.startswith("class_name"): return "class_name"
    if line.startswith("extends"): return "extends"
    if line.startswith("##"): return "doccomment"
    if line.startswith("signal "): return "signal"
    if line.startswith("enum "): return "enum"
    if line.startswith("const "): return "const"
    if re.match(r'^static\s+var\s', line): return "static_var"
    if line.startswith("@export"): return "export_var"
    if line.startswith("@onready"): return "onready_var"
    if re.match(r'^var\s', line): return "var"
    if re.match(r'^func\s+_(ready|process|physics_process|input|unhandled_input|enter_tree|exit_tree|init|draw)', line):
        return "lifecycle"
    if re.match(r'^func\s+_', line): return "private_method"
    if re.match(r'^func\s+', line): return "public_method"
    return None


def _check_type_annotations(lines: list[str], issues: list[LintIssue]) -> None:
    """Check for missing type annotations (Playbook 3.4)."""
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # var without type annotation
        var_match = re.match(r'^(?:@export\s+|@onready\s+)?var\s+(\w+)\s*=\s*', stripped)
        if var_match and ":" not in stripped.split("=")[0]:
            name = var_match.group(1)
            # Skip if using := (type inference)
            if ":=" not in stripped:
                issues.append(LintIssue(i, "info", "type-annotation",
                    f'Variable "{name}" has no type annotation. Consider: var {name}: Type = ...'))

        # func without return type
        func_match = re.match(r'^func\s+(\w+)\s*\(', stripped)
        if func_match and ") ->" not in stripped and "):" in stripped:
            name = func_match.group(1)
            issues.append(LintIssue(i, "info", "return-type",
                f'Function "{name}" has no return type annotation. Consider: -> void or -> Type'))


def _check_antipatterns(lines: list[str], issues: list[LintIssue]) -> None:
    """Check for common anti-patterns (Playbook 19)."""
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # get_node in _process (should be @onready)
        if "get_node(" in stripped:
            # Check if we're inside a _process function (rough heuristic)
            issues.append(LintIssue(i, "warning", "cache-node",
                'get_node() call found. Cache with @onready instead of calling every frame.'))

        # Hardcoded key checks
        if "is_key_pressed(" in stripped or "KEY_" in stripped:
            issues.append(LintIssue(i, "warning", "input-map",
                'Hardcoded key check. Use Input.is_action_pressed("action_name") instead.'))

        # Direct position set on RigidBody
        if re.match(r'.*rigid.*\.position\s*=', stripped, re.IGNORECASE):
            issues.append(LintIssue(i, "warning", "rigidbody-position",
                'Setting RigidBody position directly. Use apply_force/impulse or _integrate_forces.'))

        # Boolean operators
        if " && " in stripped or " || " in stripped or stripped.startswith("!"):
            issues.append(LintIssue(i, "info", "bool-operators",
                'Use "and", "or", "not" instead of "&&", "||", "!" in GDScript.'))


def format_lint_report(issues: list[LintIssue], filename: str = "") -> str:
    """Format lint issues as a readable report."""
    if not issues:
        return f"{'✓ ' + filename + ': ' if filename else ''}No lint issues found."

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    infos = [i for i in issues if i.severity == "info"]

    header = f"{filename}: " if filename else ""
    lines = [f"{header}{len(errors)} errors, {len(warnings)} warnings, {len(infos)} info"]
    for issue in issues:
        lines.append(f"  {issue}")
    return "\n".join(lines)
