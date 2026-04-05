from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from godot_agent.runtime.validation_checks import CheckResult, ValidationSuite


@pytest.mark.asyncio
async def test_run_all_returns_cached_results():
    suite = ValidationSuite(project_root="/tmp/fake", changed_files={"test.gd"})
    with patch.object(
        suite,
        "_run_check",
        new_callable=AsyncMock,
        return_value=CheckResult(name="lint", status="pass", summary="ok", details=""),
    ):
        results = await suite.run_all()
        assert "gdscript-lint" in results
        # Second call returns cached, doesn't re-run
        results2 = await suite.run_all()
        assert results2 is results
        assert suite._run_check.call_count == 11


def test_get_returns_none_before_run():
    suite = ValidationSuite(project_root="/tmp/fake", changed_files=set())
    assert suite.get("gdscript-lint") is None


@pytest.mark.asyncio
async def test_check_result_has_required_fields():
    result = CheckResult(name="lint", status="pass", summary="0 issues", details="")
    assert result.name == "lint"
    assert result.status in ("pass", "warning", "error")
