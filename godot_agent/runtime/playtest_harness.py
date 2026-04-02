"""Scenario-driven playtest harness."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from godot_agent.godot.impact_analysis import ImpactAnalysisReport
from godot_agent.runtime.runtime_bridge import RuntimeSnapshot


SCENARIO_DIR = Path(__file__).with_name("scenario_specs")


@dataclass
class ScenarioSpec:
    id: str
    title: str
    description: str
    path_contains: list[str] = field(default_factory=list)
    required_scene: str = ""
    required_nodes: list[str] = field(default_factory=list)
    required_events: list[str] = field(default_factory=list)
    required_inputs: list[str] = field(default_factory=list)
    forbid_runtime_errors: bool = True


@dataclass
class ScenarioResult:
    id: str
    title: str
    status: str
    observations: list[str] = field(default_factory=list)


@dataclass
class PlaytestReport:
    scenarios: list[ScenarioResult] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        statuses = {scenario.status for scenario in self.scenarios}
        if "FAIL" in statuses:
            return "FAIL"
        if "PARTIAL" in statuses:
            return "PARTIAL"
        return "PASS"


def _load_scenario_specs(directory: Path = SCENARIO_DIR) -> list[ScenarioSpec]:
    specs: list[ScenarioSpec] = []
    if not directory.exists():
        return specs
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        specs.append(ScenarioSpec(**data))
    return specs


def select_relevant_scenarios(
    changed_files: set[str],
    impact_report: ImpactAnalysisReport | None = None,
    directory: Path = SCENARIO_DIR,
) -> list[ScenarioSpec]:
    changed_paths = {Path(path).name.lower() for path in changed_files}
    if impact_report is not None:
        changed_paths.update(path.lower() for path in impact_report.affected_files)

    relevant: list[ScenarioSpec] = []
    for spec in _load_scenario_specs(directory):
        triggers = [token.lower() for token in spec.path_contains]
        if not triggers or any(token in path for token in triggers for path in changed_paths):
            relevant.append(spec)
    return relevant


def _evaluate_scenario(spec: ScenarioSpec, snapshot: RuntimeSnapshot | None) -> ScenarioResult:
    if snapshot is None:
        return ScenarioResult(
            id=spec.id,
            title=spec.title,
            status="PARTIAL",
            observations=["No runtime snapshot available for this scenario."],
        )

    observations: list[str] = []
    status = "PASS"
    node_paths = {node.path for node in snapshot.nodes}
    node_names = {node.path.split("/")[-1] for node in snapshot.nodes}
    event_names = {event.name for event in snapshot.events}
    input_names = set(snapshot.input_actions)

    if spec.required_scene and snapshot.active_scene != spec.required_scene:
        status = "FAIL"
        observations.append(f"Expected active scene {spec.required_scene}, got {snapshot.active_scene or '(none)'}")
    if spec.required_nodes:
        missing_nodes = [node for node in spec.required_nodes if node not in node_paths and node not in node_names]
        if missing_nodes:
            status = "FAIL"
            observations.append("Missing nodes: " + ", ".join(missing_nodes))
    if spec.required_events:
        missing_events = [event for event in spec.required_events if event not in event_names]
        if missing_events:
            status = "PARTIAL" if status == "PASS" else status
            observations.append("Missing events: " + ", ".join(missing_events))
    if spec.required_inputs:
        missing_inputs = [action for action in spec.required_inputs if action not in input_names]
        if missing_inputs:
            status = "PARTIAL" if status == "PASS" else status
            observations.append("Missing input evidence: " + ", ".join(missing_inputs))
    if spec.forbid_runtime_errors and snapshot.errors:
        status = "FAIL"
        observations.append("Runtime errors present: " + " | ".join(snapshot.errors[:5]))

    if not observations:
        observations.append("Scenario expectations satisfied.")
    return ScenarioResult(id=spec.id, title=spec.title, status=status, observations=observations)


def run_playtest_harness(
    *,
    project_root: Path,
    changed_files: set[str],
    impact_report: ImpactAnalysisReport | None = None,
    runtime_snapshot: RuntimeSnapshot | None = None,
    directory: Path = SCENARIO_DIR,
) -> PlaytestReport:
    _ = project_root
    scenarios = select_relevant_scenarios(changed_files, impact_report, directory=directory)
    if not scenarios:
        return PlaytestReport(scenarios=[ScenarioResult(id="none", title="No matching scenarios", status="PASS", observations=["No scenario matched the current change set."])])
    return PlaytestReport(scenarios=[_evaluate_scenario(spec, runtime_snapshot) for spec in scenarios])


def format_playtest_report(report: PlaytestReport) -> str:
    lines = [f"Playtest VERDICT: {report.verdict}"]
    for scenario in report.scenarios:
        lines.append(f"- {scenario.title} [{scenario.status}]")
        for observation in scenario.observations:
            lines.append(f"  {observation}")
    return "\n".join(lines)
