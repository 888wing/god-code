# godot_agent/cli/__init__.py
"""CLI package for god-code.

Re-exports public symbols so that ``from godot_agent.cli import main``
(and all existing test imports) continue to work after the split.

Monkeypatch compatibility: tests patch names on ``godot_agent.cli``
(e.g. ``monkeypatch.setattr("godot_agent.cli.build_engine", ...)``).
For this to take effect at call time, the actual call sites in the
sub-modules resolve these names via ``sys.modules["godot_agent.cli"]``
rather than using a direct import binding.
"""
from godot_agent.cli.commands import main  # noqa: F401 – entry-point

# ── re-exports consumed by tests and entrypoint.py ─────────────

from godot_agent.cli.engine_wiring import (  # noqa: F401
    _apply_provider_preset,
    _has_usable_provider_auth,
    _is_interactive_terminal,
    _load_or_setup_config,
    _normalize_reasoning_effort,
    _persist_config_updates,
    _provider_auth_issue,
    _save_config_data,
    _sync_provider_from_model,
    _wire_engine_callbacks,
    build_engine,
    build_registry,
)

# Re-export load_config so tests can monkeypatch it on this module.
from godot_agent.runtime.config import load_config  # noqa: F401

from godot_agent.cli.commands import (  # noqa: F401
    _check_update,
    _run_setup_wizard,
)

from godot_agent.cli.helpers import (  # noqa: F401
    _cd_argument,
    _command_argument,
    _format_skill_list,
    _has_meaningful_input,
    _is_multiline_terminator,
    _multiline_initial_fragment,
    _set_arguments,
    _starts_multiline_input,
)

from godot_agent.cli.menus import (  # noqa: F401
    _effort_menu_options,
    _format_setting_display_value,
    _main_menu_options,
    _mode_menu_options,
    _model_menu_options,
    _provider_menu_options,
    _setting_value_menu_options,
    _settings_menu_options,
    _skill_menu_options,
)
