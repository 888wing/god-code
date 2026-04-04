from __future__ import annotations

import random
from pathlib import Path

import pytest
from click.testing import CliRunner

from godot_agent.cli import main
from godot_agent.runtime.config import AgentConfig
from tests.cli_test_utils import build_engine_factory, scripted_async_inputs


_RANDOM = random.Random(404)
_TOKENS = [
    "",
    " ",
    "/menu",
    "mode",
    "provider",
    "model",
    "effort",
    "set",
    "status",
    "workspace",
    "help",
    "1",
    "2",
    "openai",
    "anthropic",
    "custom",
    "api_key",
    "base_url",
    "sk-ant-fuzz-key",
    "sk-test-fuzz-key",
    "/resume",
    "/resume latest",
    "/provider anthropic",
    "/model gpt-5.4-mini",
    "/set mode apply",
    "/set api_key sk-test-inline",
    "random text",
    "cd /tmp",
    "/cd ",
]
_SEQUENCES = [
    [_RANDOM.choice(_TOKENS) for _ in range(length)] + [None]
    for length in range(1, 12)
]


def _project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "project.godot").write_text(
        'config_version=5\n\n[application]\nconfig/name="Fuzz"\n',
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.parametrize("sequence", _SEQUENCES)
def test_chat_loop_fuzz_sequences_do_not_crash(monkeypatch, tmp_path: Path, sequence: list[str | None]) -> None:
    project_root = _project(tmp_path / "project")
    config_path = tmp_path / "config.json"
    cfg = AgentConfig(api_key="sk-test", provider="openai", model="gpt-5.4", streaming=False)

    build_engine, _created = build_engine_factory([["ok"]] * 8)
    monkeypatch.setattr("godot_agent.cli._check_update", lambda: None)
    monkeypatch.setattr("godot_agent.cli._load_or_setup_config", lambda path: cfg.model_copy(deep=True))
    monkeypatch.setattr("godot_agent.cli.build_engine", build_engine)
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_input_async",
        scripted_async_inputs(sequence),
    )
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_multiline_continuation_async",
        scripted_async_inputs(['"""']),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--project", str(project_root), "--config", str(config_path)])

    assert result.exit_code == 0, f"sequence={sequence!r}\n{result.output}"
