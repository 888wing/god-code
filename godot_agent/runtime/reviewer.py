"""Deterministic reviewer pass for Godot project changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from godot_agent.godot.audio_scaffolder import validate_audio_nodes
from godot_agent.godot.consistency_checker import check_consistency
from godot_agent.godot.dependency_graph import build_dependency_graph
from godot_agent.godot.gdscript_linter import format_lint_report, lint_gdscript
from godot_agent.godot.impact_analysis import ImpactAnalysisReport, analyze_change_impact, format_impact_report
from godot_agent.godot.resource_validator import validate_resources
from godot_agent.godot.scene_parser import parse_tscn
from godot_agent.godot.tscn_validator import validate_tscn
from godot_agent.godot.ui_layout_advisor import validate_ui_layout
from godot_agent.runtime.design_memory import DesignMemory, GameplayIntentProfile, load_design_memory
from godot_agent.runtime.error_loop import format_validation_for_llm, validate_project
from godot_agent.runtime.gameplay_reviewer import review_gameplay_constraints
from godot_agent.runtime.playtest_harness import PlaytestReport, run_playtest_harness
from godot_agent.runtime.quality_gate import QualityGateReport
from godot_agent.runtime.runtime_bridge import RuntimeSnapshot
from godot_agent.runtime.validation_checks import ValidationSuite


@dataclass
class ReviewCheck:
    description: str
    command: str
    observed_output: str
    status: str  # PASS / FAIL / PARTIAL


@dataclass
class ReviewReport:
    checks: list[ReviewCheck] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        statuses = {check.status for check in self.checks}
        if "FAIL" in statuses:
            return "FAIL"
        if "PARTIAL" in statuses or "WARN" in statuses:
            return "PARTIAL"
        return "PASS"

    @property
    def requires_fix(self) -> bool:
        return self.verdict == "FAIL"


def _relative_to(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _append(report: ReviewReport, description: str, command: str, observed_output: str, status: str) -> None:
    report.checks.append(
        ReviewCheck(
            description=description,
            command=command,
            observed_output=observed_output.strip(),
            status=status,
        )
    )


async def review_changes(
    *,
    project_root: Path,
    changed_files: set[str],
    godot_path: str,
    quality_report: QualityGateReport | None = None,
    design_memory: DesignMemory | None = None,
    intent_profile: GameplayIntentProfile | None = None,
    impact_report: ImpactAnalysisReport | None = None,
    runtime_snapshot: RuntimeSnapshot | None = None,
    playtest_report: PlaytestReport | None = None,
    validation_suite: ValidationSuite | None = None,
) -> ReviewReport:
    """Run a read-only verification pass over changed files."""

    report = ReviewReport()
    if not changed_files:
        _append(
            report,
            "No file mutations to review",
            "review_changes(no-op)",
            "No changes were made in this turn.",
            "PASS",
        )
        return report

    if quality_report is not None:
        status = "FAIL" if quality_report.verdict == "fail" else "PARTIAL" if quality_report.verdict == "partial" else "PASS"
        _append(
            report,
            "Review quality gate output",
            "quality_gate(previous step)",
            f"Quality gate verdict was {quality_report.verdict.upper()} across {len(quality_report.checks)} checks.",
            status,
        )

    rel_changed = {
        _relative_to(project_root, Path(path)): Path(path).resolve()
        for path in changed_files
    }
    if impact_report is None:
        impact_report = analyze_change_impact(project_root, changed_files)
    _append(
        report,
        "Analyze affected systems before final verdict",
        f"analyze_change_impact {project_root}",
        format_impact_report(impact_report),
        "PASS",
    )

    for rel_path, abs_path in sorted(rel_changed.items()):
        if not abs_path.exists():
            _append(
                report,
                f"Verify changed file still exists for {rel_path}",
                f"stat {abs_path}",
                "Changed file is missing after the write step.",
                "FAIL",
            )
            continue

        if abs_path.suffix == ".gd":
            issues = lint_gdscript(abs_path.read_text(encoding="utf-8", errors="replace"), rel_path)
            status = "FAIL" if any(issue.severity == "error" for issue in issues) else "PARTIAL" if issues else "PASS"
            observed = format_lint_report(issues, rel_path) if issues else "No lint issues found."
            _append(
                report,
                f"Lint changed script {rel_path}",
                f"lint_gdscript {abs_path}",
                observed,
                status,
            )

        if abs_path.suffix == ".tscn":
            text = abs_path.read_text(encoding="utf-8", errors="replace")
            tscn_issues = validate_tscn(text)
            scene = parse_tscn(text)
            status = "FAIL" if any(issue.severity == "error" for issue in tscn_issues) else "PARTIAL" if tscn_issues else "PASS"
            observed = "\n".join(str(issue) for issue in tscn_issues) if tscn_issues else "Scene format validation passed."
            _append(
                report,
                f"Validate changed scene file {rel_path}",
                f"validate_tscn {abs_path}",
                observed,
                status,
            )

            resource_issues = validate_resources(abs_path, project_root)
            _append(
                report,
                f"Validate scene resources for {rel_path}",
                f"validate_resources {abs_path}",
                "\n".join(resource_issues) if resource_issues else "All scene resources resolved successfully.",
                "FAIL" if resource_issues else "PASS",
            )

            ui_warnings = validate_ui_layout(scene)
            if any(node.type == "Control" or node.type.endswith("Container") for node in scene.nodes):
                _append(
                    report,
                    f"Validate UI layout conventions for {rel_path}",
                    f"validate_ui_layout {abs_path}",
                    "\n".join(ui_warnings) if ui_warnings else "UI layout checks passed.",
                    "PARTIAL" if ui_warnings else "PASS",
                )

            audio_warnings = validate_audio_nodes(scene, project_root)
            if any("AudioStreamPlayer" in (node.type or "") for node in scene.nodes):
                _append(
                    report,
                    f"Validate audio nodes for {rel_path}",
                    f"validate_audio_nodes {abs_path}",
                    "\n".join(audio_warnings) if audio_warnings else "Audio node checks passed.",
                    "PARTIAL" if audio_warnings else "PASS",
                )

    consistency = check_consistency(project_root)
    relevant_consistency = [
        issue for issue in consistency
        if issue.file in rel_changed or any(rel in issue.file for rel in rel_changed)
    ]
    _append(
        report,
        "Check cross-file consistency around the changed systems",
        f"check_consistency {project_root}",
        "\n".join(str(issue) for issue in relevant_consistency[:20]) if relevant_consistency else "No relevant consistency issues found.",
        "FAIL" if any(issue.severity == "error" for issue in relevant_consistency) else "PARTIAL" if relevant_consistency else "PASS",
    )

    graph = build_dependency_graph(project_root)
    orphaned_changed = [path for path in graph.orphans() if path.replace("res://", "") in rel_changed]
    _append(
        report,
        "Check whether changed assets are still connected to the project graph",
        f"build_dependency_graph {project_root}",
        "\n".join(orphaned_changed) if orphaned_changed else "Changed assets remain reachable from the project graph.",
        "PARTIAL" if orphaned_changed else "PASS",
    )

    validation = await validate_project(str(project_root), godot_path=godot_path, timeout=30)
    _append(
        report,
        "Launch Godot headless to verify the project still loads",
        f"{godot_path} --headless --quit",
        format_validation_for_llm(validation),
        "PASS" if validation.success else "FAIL",
    )

    design_memory = design_memory or load_design_memory(project_root)
    runtime_snapshot = runtime_snapshot
    should_run_gameplay_review = (
        not design_memory.is_empty
        or runtime_snapshot is not None
        or playtest_report is not None
        or (intent_profile is not None and not intent_profile.is_empty)
    )
    if should_run_gameplay_review:
        if playtest_report is None and runtime_snapshot is not None:
            playtest_report = run_playtest_harness(
                project_root=project_root,
                changed_files=changed_files,
                impact_report=impact_report,
                runtime_snapshot=runtime_snapshot,
                design_memory=design_memory,
            )
        gameplay_report = review_gameplay_constraints(
            project_root=project_root,
            changed_files=changed_files,
            design_memory=design_memory,
            intent_profile=intent_profile or design_memory.gameplay_intent,
            impact_report=impact_report,
            runtime_snapshot=runtime_snapshot,
            playtest_report=playtest_report,
        )
        for check in gameplay_report.checks:
            _append(
                report,
                check.description,
                "gameplay_review",
                check.observed_output,
                check.status,
            )

    return report


def format_review_report(report: ReviewReport) -> str:
    """Render reviewer output for prompt injection."""

    lines = [f"Reviewer VERDICT: {report.verdict}"]
    for index, check in enumerate(report.checks, 1):
        lines.append(f"{index}. {check.description}")
        lines.append(f"Command: {check.command}")
        lines.append(f"Observed: {check.observed_output[:2000]}")
        lines.append(f"Result: {check.status}")
    return "\n".join(lines)
