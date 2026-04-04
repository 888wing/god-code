from rich.console import Console

from godot_agent.runtime.events import EngineEvent
from godot_agent.tui.display import ChatDisplay


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
