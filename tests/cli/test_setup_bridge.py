"""Tests for the setup-bridge CLI command."""
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from godot_agent.cli import main


def _godot_project(tmp_path: Path, extra_sections: str = "") -> Path:
    """Create a minimal Godot project directory."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "project.godot").write_text(
        'config_version=5\n\n[application]\nconfig/name="TestProject"\n' + extra_sections,
        encoding="utf-8",
    )
    return tmp_path


def test_setup_bridge_command_exists() -> None:
    """The setup-bridge command is registered on the CLI group."""
    runner = CliRunner()
    result = runner.invoke(main, ["setup-bridge", "--help"])
    assert result.exit_code == 0
    assert "Install GodCodeBridge" in result.output


def test_setup_bridge_no_project_godot(tmp_path: Path) -> None:
    """Fails gracefully when project.godot is missing."""
    runner = CliRunner()
    result = runner.invoke(main, ["setup-bridge", str(tmp_path)])
    assert result.exit_code != 0
    assert "No project.godot found" in result.output


def test_setup_bridge_copies_plugin(tmp_path: Path) -> None:
    """Copies plugin files and adds autoload entry."""
    project = _godot_project(tmp_path / "game")
    runner = CliRunner()
    result = runner.invoke(main, ["setup-bridge", str(project)])
    assert result.exit_code == 0, result.output

    # Plugin files are copied
    bridge_gd = project / "addons" / "god_code_bridge" / "god_code_bridge.gd"
    plugin_cfg = project / "addons" / "god_code_bridge" / "plugin.cfg"
    assert bridge_gd.exists()
    assert plugin_cfg.exists()
    assert "GodCodeBridge" in bridge_gd.read_text()

    # Autoload entry added
    godot_text = (project / "project.godot").read_text()
    assert "[autoload]" in godot_text
    assert 'GodCodeBridge="*res://addons/god_code_bridge/god_code_bridge.gd"' in godot_text


def test_setup_bridge_existing_autoload_section(tmp_path: Path) -> None:
    """Appends to existing [autoload] section without duplicating."""
    project = _godot_project(
        tmp_path / "game",
        extra_sections='\n[autoload]\n\nMyPlugin="*res://addons/my_plugin/my_plugin.gd"\n',
    )
    runner = CliRunner()
    result = runner.invoke(main, ["setup-bridge", str(project)])
    assert result.exit_code == 0, result.output

    godot_text = (project / "project.godot").read_text()
    assert godot_text.count("[autoload]") == 1
    assert "GodCodeBridge" in godot_text
    assert "MyPlugin" in godot_text


def test_setup_bridge_already_installed(tmp_path: Path) -> None:
    """Skips autoload if GodCodeBridge already present."""
    project = _godot_project(
        tmp_path / "game",
        extra_sections='\n[autoload]\n\nGodCodeBridge="*res://addons/god_code_bridge/god_code_bridge.gd"\n',
    )
    runner = CliRunner()
    result = runner.invoke(main, ["setup-bridge", str(project)])
    assert result.exit_code == 0, result.output
    assert "already exists" in result.output

    # Autoload not duplicated
    godot_text = (project / "project.godot").read_text()
    assert godot_text.count("GodCodeBridge") == 1


def test_setup_bridge_updates_existing_plugin(tmp_path: Path) -> None:
    """Overwrites plugin files when already installed."""
    project = _godot_project(tmp_path / "game")
    dest = project / "addons" / "god_code_bridge"
    dest.mkdir(parents=True)
    (dest / "old_file.txt").write_text("stale")

    runner = CliRunner()
    result = runner.invoke(main, ["setup-bridge", str(project)])
    assert result.exit_code == 0, result.output
    assert "Updating" in result.output

    # Old file gone, new files present
    assert not (dest / "old_file.txt").exists()
    assert (dest / "god_code_bridge.gd").exists()
