"""Project-aware quality checks for Godot code and scene changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from godot_agent.godot.audio_scaffolder import validate_audio_nodes
from godot_agent.godot.consistency_checker import check_consistency
from godot_agent.godot.dependency_graph import build_dependency_graph
from godot_agent.godot.gdscript_linter import format_lint_report, lint_gdscript
from godot_agent.godot.impact_analysis import analyze_change_impact, format_impact_report
from godot_agent.godot.pattern_advisor import analyze_project
from godot_agent.godot.resource_validator import validate_resources
from godot_agent.godot.scene_parser import parse_tscn
from godot_agent.godot.tscn_validator import validate_tscn
from godot_agent.godot.ui_layout_advisor import validate_ui_layout
from godot_agent.runtime.error_loop import format_validation_for_llm, validate_project
from godot_agent.runtime.validation_checks import CheckResult, ValidationSuite


@dataclass
class ChangeSet:
    """Tracks which files were read and modified during the session."""

    read_files: set[str] = field(default_factory=set)
    modified_files: set[str] = field(default_factory=set)

    def mark_read(self, path: str) -> None:
        self.read_files.add(str(Path(path).resolve()))

    def mark_modified(self, path: str) -> None:
        resolved = str(Path(path).resolve())
        self.modified_files.add(resolved)
        self.read_files.add(resolved)

    def clear_modified(self) -> None:
        self.modified_files.clear()


@dataclass
class QualityCheck:
    name: str
    command: str
    status: str  # pass / warning / error
    summary: str
    details: str = ""
    file: str | None = None


@dataclass
class QualityGateReport:
    changed_files: list[str] = field(default_factory=list)
    checks: list[QualityCheck] = field(default_factory=list)

    @property
    def errors(self) -> list[QualityCheck]:
        return [check for check in self.checks if check.status == "error"]

    @property
    def warnings(self) -> list[QualityCheck]:
        return [check for check in self.checks if check.status == "warning"]

    @property
    def verdict(self) -> str:
        if self.errors:
            return "fail"
        if self.warnings:
            return "partial"
        return "pass"

    @property
    def requires_fix(self) -> bool:
        return self.verdict == "fail"


def _relative_to(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _add_check(
    report: QualityGateReport,
    *,
    name: str,
    command: str,
    status: str,
    summary: str,
    details: str = "",
    file: str | None = None,
) -> None:
    report.checks.append(
        QualityCheck(
            name=name,
            command=command,
            status=status,
            summary=summary,
            details=details.strip(),
            file=file,
        )
    )


def _use_cached(
    report: QualityGateReport,
    cached: CheckResult,
    command: str,
) -> None:
    """Convert a cached CheckResult into a QualityCheck and append it."""
    report.checks.append(
        QualityCheck(
            name=cached.name,
            command=command,
            status=cached.status,
            summary=cached.summary,
            details=cached.details.strip(),
            file=cached.file,
        )
    )


async def run_quality_gate(
    *,
    project_root: Path,
    changed_files: set[str],
    godot_path: str = "godot",
    validation_suite: ValidationSuite | None = None,
) -> QualityGateReport:
    """Run deterministic quality checks after file mutations."""

    report = QualityGateReport(
        changed_files=sorted(_relative_to(project_root, Path(path)) for path in changed_files)
    )
    if not changed_files:
        return report

    # Create suite internally when not provided (backward compat).
    # Don't run_all() here — suite.get() returns None for un-run suites,
    # so all checks fall through to the existing logic.
    if validation_suite is None:
        validation_suite = ValidationSuite(project_root=project_root, changed_files=changed_files)

    rel_changed = {
        _relative_to(project_root, Path(path)): Path(path).resolve()
        for path in changed_files
    }

    cached = validation_suite.get("change-impact")
    if cached:
        _use_cached(report, cached, f"analyze_change_impact {project_root}")
    else:
        impact_report = analyze_change_impact(project_root, changed_files)
        _add_check(
            report,
            name="change-impact",
            command=f"analyze_change_impact {project_root}",
            status="pass",
            summary=f"Identified {len(impact_report.affected_files)} affected files and {len(impact_report.validation_focus)} validation targets.",
            details=format_impact_report(impact_report),
        )

    for rel_path, abs_path in sorted(rel_changed.items()):
        if not abs_path.exists():
            cached = validation_suite.get("file-exists")
            if cached:
                _use_cached(report, cached, f"stat {abs_path}")
            else:
                _add_check(
                    report,
                    name="file-exists",
                    command=f"stat {abs_path}",
                    status="error",
                    summary="Changed file no longer exists on disk.",
                    file=rel_path,
                )
            continue

        if abs_path.suffix == ".gd":
            cached = validation_suite.get("gdscript-lint")
            if cached:
                _use_cached(report, cached, f"lint_gdscript {abs_path}")
            else:
                text = abs_path.read_text(encoding="utf-8", errors="replace")
                issues = lint_gdscript(text, rel_path)
                if issues:
                    error_count = len([issue for issue in issues if issue.severity == "error"])
                    warning_count = len([issue for issue in issues if issue.severity == "warning"])
                    status = "error" if error_count else "warning"
                    _add_check(
                        report,
                        name="gdscript-lint",
                        command=f"lint_gdscript {abs_path}",
                        status=status,
                        summary=f"{error_count} errors, {warning_count} warnings from GDScript linter.",
                        details=format_lint_report(issues, rel_path),
                        file=rel_path,
                    )
                else:
                    _add_check(
                        report,
                        name="gdscript-lint",
                        command=f"lint_gdscript {abs_path}",
                        status="pass",
                        summary="No GDScript lint issues found.",
                        file=rel_path,
                    )

        if abs_path.suffix == ".tscn":
            scene = None
            cached = validation_suite.get("tscn-validate")
            if cached:
                _use_cached(report, cached, f"validate_tscn {abs_path}")
            else:
                text = abs_path.read_text(encoding="utf-8", errors="replace")
                issues = validate_tscn(text)
                scene = parse_tscn(text)
                if issues:
                    error_count = len([issue for issue in issues if issue.severity == "error"])
                    warning_count = len([issue for issue in issues if issue.severity == "warning"])
                    status = "error" if error_count else "warning"
                    details = "\n".join(str(issue) for issue in issues[:20])
                    _add_check(
                        report,
                        name="tscn-validate",
                        command=f"validate_tscn {abs_path}",
                        status=status,
                        summary=f"{error_count} scene errors, {warning_count} warnings.",
                        details=details,
                        file=rel_path,
                    )
                else:
                    _add_check(
                        report,
                        name="tscn-validate",
                        command=f"validate_tscn {abs_path}",
                        status="pass",
                        summary="Scene format validation passed.",
                        file=rel_path,
                    )

            cached = validation_suite.get("scene-resources")
            if cached:
                _use_cached(report, cached, f"validate_resources {abs_path}")
            else:
                resource_issues = validate_resources(abs_path, project_root)
                if resource_issues:
                    _add_check(
                        report,
                        name="scene-resources",
                        command=f"validate_resources {abs_path}",
                        status="error",
                        summary=f"{len(resource_issues)} missing resource references.",
                        details="\n".join(resource_issues[:20]),
                        file=rel_path,
                    )
                else:
                    _add_check(
                        report,
                        name="scene-resources",
                        command=f"validate_resources {abs_path}",
                        status="pass",
                        summary="All referenced scene resources exist on disk.",
                        file=rel_path,
                    )

            cached = validation_suite.get("ui-layout")
            if cached:
                _use_cached(report, cached, f"validate_ui_layout {abs_path}")
            else:
                if scene is None:
                    text = abs_path.read_text(encoding="utf-8", errors="replace")
                    scene = parse_tscn(text)
                ui_warnings = validate_ui_layout(scene)
                if any(node.type == "Control" or node.type.endswith("Container") for node in scene.nodes):
                    _add_check(
                        report,
                        name="ui-layout",
                        command=f"validate_ui_layout {abs_path}",
                        status="warning" if ui_warnings else "pass",
                        summary="UI layout warnings found." if ui_warnings else "UI layout checks passed.",
                        details="\n".join(ui_warnings[:20]),
                        file=rel_path,
                    )

            cached = validation_suite.get("audio-nodes")
            if cached:
                _use_cached(report, cached, f"validate_audio_nodes {abs_path}")
            else:
                if scene is None:
                    text = abs_path.read_text(encoding="utf-8", errors="replace")
                    scene = parse_tscn(text)
                audio_warnings = validate_audio_nodes(scene, project_root)
                if any("AudioStreamPlayer" in (node.type or "") for node in scene.nodes):
                    _add_check(
                        report,
                        name="audio-nodes",
                        command=f"validate_audio_nodes {abs_path}",
                        status="warning" if audio_warnings else "pass",
                        summary="Audio node warnings found." if audio_warnings else "Audio node checks passed.",
                        details="\n".join(audio_warnings[:20]),
                        file=rel_path,
                    )

    cached = validation_suite.get("project-consistency")
    if cached:
        _use_cached(report, cached, f"check_consistency {project_root}")
    else:
        consistency_issues = check_consistency(project_root)
        relevant_consistency = [
            issue for issue in consistency_issues
            if issue.file in rel_changed or any(rel in issue.file for rel in rel_changed)
        ]
        if relevant_consistency:
            error_count = len([issue for issue in relevant_consistency if issue.severity == "error"])
            warning_count = len([issue for issue in relevant_consistency if issue.severity == "warning"])
            status = "error" if error_count else "warning"
            _add_check(
                report,
                name="project-consistency",
                command=f"check_consistency {project_root}",
                status=status,
                summary=f"{error_count} errors, {warning_count} warnings in cross-file consistency.",
                details="\n".join(str(issue) for issue in relevant_consistency[:20]),
            )
        else:
            _add_check(
                report,
                name="project-consistency",
                command=f"check_consistency {project_root}",
                status="pass",
                summary="No relevant cross-file consistency issues found.",
            )

    cached = validation_suite.get("dependency-graph")
    if cached:
        _use_cached(report, cached, f"build_dependency_graph {project_root}")
    else:
        graph = build_dependency_graph(project_root)
        orphaned_changed = [path for path in graph.orphans() if path.replace("res://", "") in rel_changed]
        if orphaned_changed:
            _add_check(
                report,
                name="dependency-graph",
                command=f"build_dependency_graph {project_root}",
                status="warning",
                summary=f"{len(orphaned_changed)} changed files are unreferenced.",
                details="\n".join(orphaned_changed),
            )
        else:
            _add_check(
                report,
                name="dependency-graph",
                command=f"build_dependency_graph {project_root}",
                status="pass",
                summary="Changed files are connected to the current project dependency graph.",
            )

    cached = validation_suite.get("pattern-advisor")
    if cached:
        _use_cached(report, cached, f"analyze_project {project_root}")
    else:
        pattern_advice = analyze_project(project_root)
        relevant_advice = [advice for advice in pattern_advice if advice.file in rel_changed]
        if relevant_advice:
            _add_check(
                report,
                name="pattern-advisor",
                command=f"analyze_project {project_root}",
                status="warning",
                summary=f"{len(relevant_advice)} architectural quality suggestions for changed scripts.",
                details="\n".join(
                    f"[{advice.severity}] {advice.file} [{advice.pattern}] {advice.message}"
                    for advice in relevant_advice[:20]
                ),
            )
        else:
            _add_check(
                report,
                name="pattern-advisor",
                command=f"analyze_project {project_root}",
                status="pass",
                summary="No structural pattern warnings for changed scripts.",
            )

    cached = validation_suite.get("godot-validate")
    if cached:
        _use_cached(report, cached, f"{godot_path} --headless --quit")
    else:
        validation = await validate_project(str(project_root), godot_path=godot_path, timeout=30)
        validation_status = "pass" if validation.success else "error"
        _add_check(
            report,
            name="godot-validate",
            command=f"{godot_path} --headless --quit",
            status=validation_status,
            summary="Godot headless validation passed." if validation.success else "Godot headless validation failed.",
            details=format_validation_for_llm(validation),
        )

    return report


def format_quality_gate_report(report: QualityGateReport) -> str:
    """Format quality gate output for prompt injection and user-visible logs."""

    if not report.changed_files:
        return "Quality gate skipped — no changed files."

    lines = [
        f"Quality gate verdict: {report.verdict.upper()}",
        f"Changed files: {', '.join(report.changed_files)}",
    ]
    for check in report.checks:
        lines.append(
            f"- [{check.status.upper()}] {check.name}: {check.summary}"
            + (f" ({check.file})" if check.file else "")
        )
        if check.details:
            lines.append(check.details[:2000])
    return "\n".join(lines)
