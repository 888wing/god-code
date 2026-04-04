from __future__ import annotations

import json
from pathlib import Path

import httpx
from click.testing import CliRunner

from godot_agent.cli import main
from godot_agent.runtime.config import AgentConfig
from godot_agent.runtime.session import save_session
from godot_agent.llm.types import Message
from tests.cli_test_utils import build_engine_factory, scripted_async_inputs


def _project(tmp_path: Path, name: str = "Demo") -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "project.godot").write_text(
        f'config_version=5\n\n[application]\nconfig/name="{name}"\n',
        encoding="utf-8",
    )
    return tmp_path


def _config(
    *,
    api_key: str = "sk-test",
    provider: str = "openai",
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-5.4",
    streaming: bool = False,
    session_dir: str = ".agent_sessions",
) -> AgentConfig:
    return AgentConfig(
        api_key=api_key,
        provider=provider,
        base_url=base_url,
        model=model,
        streaming=streaming,
        session_dir=session_dir,
    )


def test_chat_menu_set_api_key_persists_masked_value(monkeypatch, tmp_path: Path) -> None:
    project_root = _project(tmp_path / "project")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"api_key": "sk-old", "provider": "openai", "model": "gpt-5.4"}), encoding="utf-8")
    cfg = _config(api_key="sk-old")

    build_engine, created = build_engine_factory([[], []])
    monkeypatch.setattr("godot_agent.cli._check_update", lambda: None)
    monkeypatch.setattr("godot_agent.cli._load_or_setup_config", lambda path: cfg.model_copy(deep=True))
    monkeypatch.setattr("godot_agent.cli.build_engine", build_engine)
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_input_async",
        scripted_async_inputs(["/menu", "set", "api_key", "sk-new-12345678", None]),
    )
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_multiline_continuation_async",
        scripted_async_inputs([]),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--project", str(project_root), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert len(created) == 2
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["api_key"] == "sk-new-12345678"
    assert "sk-new-12345678" not in result.output
    assert "sk-n...5678" in result.output


def test_chat_provider_switch_prompts_for_new_key_and_persists(monkeypatch, tmp_path: Path) -> None:
    project_root = _project(tmp_path / "project")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"api_key": "sk-old", "provider": "openai", "model": "gpt-5.4"}), encoding="utf-8")
    cfg = _config(api_key="sk-old")

    build_engine, created = build_engine_factory([[], [], []])
    monkeypatch.setattr("godot_agent.cli._check_update", lambda: None)
    monkeypatch.setattr("godot_agent.cli._load_or_setup_config", lambda path: cfg.model_copy(deep=True))
    monkeypatch.setattr("godot_agent.cli.build_engine", build_engine)
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_input_async",
        scripted_async_inputs(["/menu", "provider", "anthropic", "sk-ant-12345678", None]),
    )
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_multiline_continuation_async",
        scripted_async_inputs([]),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--project", str(project_root), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert len(created) == 3
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["provider"] == "anthropic"
    assert saved["model"] == "claude-sonnet-4.6"
    assert saved["base_url"] == "https://api.anthropic.com/v1"
    assert saved["api_key"] == "sk-ant-12345678"
    assert "sk-ant-12345678" not in result.output
    assert (
        "requires an API key" in result.output
        or "does not look like a Anthropic key" in result.output
    )


def test_chat_multiline_cancel_does_not_submit(monkeypatch, tmp_path: Path) -> None:
    project_root = _project(tmp_path / "project")
    config_path = tmp_path / "config.json"
    cfg = _config()

    build_engine, created = build_engine_factory([[]])
    monkeypatch.setattr("godot_agent.cli._check_update", lambda: None)
    monkeypatch.setattr("godot_agent.cli._load_or_setup_config", lambda path: cfg.model_copy(deep=True))
    monkeypatch.setattr("godot_agent.cli.build_engine", build_engine)
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_input_async",
        scripted_async_inputs(['"""', None]),
    )
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_multiline_continuation_async",
        scripted_async_inputs([None]),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--project", str(project_root), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert created[0].submissions == []


def test_chat_multiline_submit_collects_lines(monkeypatch, tmp_path: Path) -> None:
    project_root = _project(tmp_path / "project")
    config_path = tmp_path / "config.json"
    cfg = _config()

    build_engine, created = build_engine_factory([["done"]])
    monkeypatch.setattr("godot_agent.cli._check_update", lambda: None)
    monkeypatch.setattr("godot_agent.cli._load_or_setup_config", lambda path: cfg.model_copy(deep=True))
    monkeypatch.setattr("godot_agent.cli.build_engine", build_engine)
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_input_async",
        scripted_async_inputs(['"""line1', None]),
    )
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_multiline_continuation_async",
        scripted_async_inputs(["line2", '"""']),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--project", str(project_root), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert created[0].submissions == ["line1\nline2"]


def test_chat_resume_rebuilds_engine_for_saved_project(monkeypatch, tmp_path: Path) -> None:
    project_root = _project(tmp_path / "project", "Current")
    resume_root = _project(tmp_path / "resume_project", "Resume")
    session_dir = tmp_path / "sessions"
    save_session(
        str(session_dir),
        "resume01",
        [Message.system("system"), Message.user("Resume me"), Message.assistant(content="ok")],
        project_path=str(resume_root),
        project_name="Resume",
        model="gpt-5.4",
        mode="apply",
    )

    config_path = tmp_path / "config.json"
    cfg = _config(session_dir=str(session_dir))

    build_engine, created = build_engine_factory([[], []])
    monkeypatch.setattr("godot_agent.cli._check_update", lambda: None)
    monkeypatch.setattr("godot_agent.cli._load_or_setup_config", lambda path: cfg.model_copy(deep=True))
    monkeypatch.setattr("godot_agent.cli.build_engine", build_engine)
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_input_async",
        scripted_async_inputs(["/resume", "1", None]),
    )
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_multiline_continuation_async",
        scripted_async_inputs([]),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--project", str(project_root), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert len(created) == 2
    assert created[0].project_path == str(project_root)
    assert created[1].project_path == str(resume_root)
    assert "Resumed session resume01" in result.output


def test_chat_http_error_does_not_end_session(monkeypatch, tmp_path: Path) -> None:
    project_root = _project(tmp_path / "project")
    config_path = tmp_path / "config.json"
    cfg = _config()

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(429, request=request)
    error = httpx.HTTPStatusError("rate limited", request=request, response=response)

    build_engine, created = build_engine_factory([[error, "Recovered"]])
    monkeypatch.setattr("godot_agent.cli._check_update", lambda: None)
    monkeypatch.setattr("godot_agent.cli._load_or_setup_config", lambda path: cfg.model_copy(deep=True))
    monkeypatch.setattr("godot_agent.cli.build_engine", build_engine)
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_input_async",
        scripted_async_inputs(["hello", "retry", None]),
    )
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_multiline_continuation_async",
        scripted_async_inputs([]),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--project", str(project_root), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert created[0].submissions == ["hello", "retry"]
    assert "API request failed (429)" in result.output


def test_chat_resume_missing_session_stays_alive(monkeypatch, tmp_path: Path) -> None:
    project_root = _project(tmp_path / "project")
    config_path = tmp_path / "config.json"
    cfg = _config(session_dir=str(tmp_path / "empty_sessions"))

    build_engine, created = build_engine_factory([[]])
    monkeypatch.setattr("godot_agent.cli._check_update", lambda: None)
    monkeypatch.setattr("godot_agent.cli._load_or_setup_config", lambda path: cfg.model_copy(deep=True))
    monkeypatch.setattr("godot_agent.cli.build_engine", build_engine)
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_input_async",
        scripted_async_inputs(["/resume latest", None]),
    )
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_multiline_continuation_async",
        scripted_async_inputs([]),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--project", str(project_root), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert "No saved sessions found" in result.output
    assert created[0].submissions == []


def test_chat_cd_switches_to_non_project_dir_without_crashing(monkeypatch, tmp_path: Path) -> None:
    project_root = _project(tmp_path / "project")
    other_root = tmp_path / "plain_dir"
    other_root.mkdir()
    config_path = tmp_path / "config.json"
    cfg = _config()

    build_engine, created = build_engine_factory([[], []])
    monkeypatch.setattr("godot_agent.cli._check_update", lambda: None)
    monkeypatch.setattr("godot_agent.cli._load_or_setup_config", lambda path: cfg.model_copy(deep=True))
    monkeypatch.setattr("godot_agent.cli.build_engine", build_engine)
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_input_async",
        scripted_async_inputs([f"cd {other_root}", None]),
    )
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_multiline_continuation_async",
        scripted_async_inputs([]),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--project", str(project_root), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert len(created) == 2
    assert created[1].project_path == str(other_root.resolve())
    assert "Working dir:" in result.output


def test_chat_keyboard_interrupt_does_not_end_session(monkeypatch, tmp_path: Path) -> None:
    project_root = _project(tmp_path / "project")
    config_path = tmp_path / "config.json"
    cfg = _config()

    build_engine, created = build_engine_factory([[KeyboardInterrupt(), "Recovered"]])
    monkeypatch.setattr("godot_agent.cli._check_update", lambda: None)
    monkeypatch.setattr("godot_agent.cli._load_or_setup_config", lambda path: cfg.model_copy(deep=True))
    monkeypatch.setattr("godot_agent.cli.build_engine", build_engine)
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_input_async",
        scripted_async_inputs(["hello", "again", None]),
    )
    monkeypatch.setattr(
        "godot_agent.tui.input_handler.get_multiline_continuation_async",
        scripted_async_inputs([]),
    )

    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--project", str(project_root), "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert created[0].submissions == ["hello", "again"]
    assert "Cancelled" in result.output
