from prompt_toolkit.document import Document

from godot_agent.tui.input_handler import CommandCompleter


def _completion_texts(text: str) -> list[str]:
    completer = CommandCompleter()
    document = Document(text=text, cursor_position=len(text))
    return [completion.text for completion in completer.get_completions(document, None)]


def test_provider_completion_lists_known_providers():
    completions = _completion_texts("/provider a")
    assert "anthropic" in completions


def test_effort_completion_lists_known_levels():
    completions = _completion_texts("/effort x")
    assert "xhigh" in completions
