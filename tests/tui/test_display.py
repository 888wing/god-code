from unittest.mock import MagicMock

from rich.console import Console
from rich.spinner import Spinner

from godot_agent.runtime.events import EngineEvent
from godot_agent.tui.display import ChatDisplay


def test_streaming_start_shows_thinking_spinner_not_empty_panel():
    """Regression v1.0.0/A1: agent_streaming_start must show a thinking
    spinner immediately, not an empty Markdown(' ') placeholder.

    Without this, gpt-5.4's 30-60s silent reasoning phase before the
    first streamed token left users staring at an empty cyan panel,
    indistinguishable from a frozen CLI.
    """
    display = ChatDisplay(console=Console(record=True))
    display.agent_streaming_start()
    assert display._stream_live is not None, "stream_live not initialised"
    # Live wraps the panel in a Group; navigate to the Panel then its inner.
    group = display._stream_live.renderable
    panels = [r for r in group.renderables if hasattr(r, "renderable")]
    assert panels, "no Panel inside Live's render group"
    inner = panels[0].renderable
    assert isinstance(inner, Spinner), (
        f"expected Spinner during initial render, got {type(inner).__name__}"
    )
    display.agent_streaming_end(finalize=False)


def test_streaming_end_prints_blank_line_separator():
    """Regression v1.0.0/A3: after a streaming turn ends, a blank line
    must be printed so successive assistant panels don't visually blur
    together. Verifies via spy on console.print.
    """
    console = Console(record=True)
    display = ChatDisplay(console=console)
    display.agent_streaming_start()
    print_spy = MagicMock()
    display.console.print = print_spy
    display.agent_streaming_end(finalize=False)
    no_arg_calls = [c for c in print_spy.call_args_list if c.args == () and not c.kwargs]
    assert no_arg_calls, (
        "agent_streaming_end must call console.print() with no args to insert "
        f"a blank line separator; calls were: {print_spy.call_args_list}"
    )


def test_tool_start_caps_long_args_at_100_chars():
    """Regression v1.0.0/B4: tool_start used to print the entire
    args_summary, which for grep regexes or large file content could
    overflow the terminal and corrupt the TUI rendering. Cap at 100.
    """
    display = ChatDisplay(console=Console(record=True))
    long_args = "x" * 500
    display.tool_start("grep", long_args)
    captured = display.console.export_text()
    # The rendered tool line should not contain the full 500 chars.
    assert "x" * 500 not in captured, "tool_start failed to cap long args"
    assert "…" in captured, "truncated args should end with an ellipsis marker"


def test_tool_start_opens_status_spinner_and_result_closes_it():
    """Regression v1.0.0/A2: tool_start should open a status spinner
    that shows movement during long-running tools (validation, sprite
    gen can take 30-60s); tool_result must close it. Without this,
    users see 'tool: started' then nothing for a minute.
    """
    display = ChatDisplay(console=Console(record=True))
    assert getattr(display, "_tool_status", None) is None
    display.tool_start("run_godot", "validate")
    assert display._tool_status is not None, "tool_start did not open a status spinner"
    display.tool_result("run_godot", success=True, summary="ok")
    assert display._tool_status is None, "tool_result did not close the status spinner"


def test_handle_diff_failed_event_logs_to_activity():
    """Regression v1.0.0/C1: diff_failed event must be visible in
    activity log so users know the modification happened but the
    diff couldn't be rendered (instead of silent except: pass).
    """
    display = ChatDisplay(console=Console(record=True))
    display.handle_event(
        EngineEvent(
            kind="diff_failed",
            message="diff: failed for /tmp/x.gd",
            data={"path": "/tmp/x.gd", "reason": "Permission denied"},
        )
    )
    assert any("diff" in line and "failed" in line for line in display.activity_log), (
        f"diff_failed event did not produce an activity line; log: {display.activity_log}"
    )


def test_handle_intent_event_updates_display_state():
    display = ChatDisplay(console=Console(record=True))

    display.handle_event(
        EngineEvent(
            kind="intent_inferred",
            data={"profile": {"genre": "bullet_hell", "enemy_model": "scripted_patterns", "confidence": 0.84}},
        )
    )

    assert display.intent_profile["genre"] == "bullet_hell"
    assert display.intent_profile["enemy_model"] == "scripted_patterns"
