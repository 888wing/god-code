"""Shared validation check runner with single-execution caching."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class CheckResult:
    """Result of a single validation check."""

    name: str
    status: str  # pass | warning | error
    summary: str
    details: str
    file: str | None = None


class ValidationSuite:
    """Run all validation checks once, cache results for shared use.

    Both quality_gate and reviewer can consume the same cached results
    instead of running duplicate checks.
    """

    def __init__(self, project_root: str | Path, changed_files: set[str]) -> None:
        self.project_root = Path(project_root)
        self.changed_files = changed_files
        self._results: dict[str, CheckResult] | None = None

    async def run_all(self) -> dict[str, CheckResult]:
        """Execute all checks and cache. Subsequent calls return the cache."""
        if self._results is not None:
            return self._results
        self._results = {}
        for check_name in self._check_names():
            result = await self._run_check(check_name)
            self._results[check_name] = result
        return self._results

    def get(self, check_name: str) -> CheckResult | None:
        """Retrieve a single cached result, or None if run_all hasn't been called."""
        if self._results is None:
            return None
        return self._results.get(check_name)

    def _check_names(self) -> list[str]:
        """Registry of all check categories to run."""
        return [
            "file_exists",
            "gdscript_lint",
            "tscn_validate",
            "scene_resources",
            "ui_layout",
            "audio_nodes",
            "project_consistency",
            "dependency_graph",
            "pattern_advisor",
        ]

    async def _run_check(self, name: str) -> CheckResult:
        """Run a single check by name.

        Delegates to existing validation functions from quality_gate.py.
        Concrete implementations will be wired in Task 2.
        """
        return CheckResult(name=name, status="pass", summary="", details="")
