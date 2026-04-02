import random
import string

import pytest
from prompt_toolkit.document import Document

from godot_agent.tui.input_handler import CommandCompleter, MenuOption, resolve_menu_choice


_RANDOM = random.Random(1337)
_FUZZ_CASES = [
    "".join(_RANDOM.choice(string.ascii_letters + string.digits + " /_\t\x7f-") for _ in range(length))
    for length in range(0, 25)
]


def _completion_texts(text: str) -> list[str]:
    completer = CommandCompleter()
    document = Document(text=text, cursor_position=len(text))
    return [completion.text for completion in completer.get_completions(document, None)]


def _completion_texts_at(text: str, cursor_position: int) -> list[str]:
    completer = CommandCompleter()
    document = Document(text=text, cursor_position=cursor_position)
    return [completion.text for completion in completer.get_completions(document, None)]


def test_provider_completion_lists_known_providers():
    completions = _completion_texts("/provider a")
    assert "anthropic" in completions


def test_effort_completion_lists_known_levels():
    completions = _completion_texts("/effort x")
    assert "xhigh" in completions


def test_provider_completion_handles_trailing_space_without_crashing():
    completions = _completion_texts("/provider ")
    assert "anthropic" in completions


def test_cd_completion_handles_empty_argument_without_crashing():
    _completion_texts("cd ")


def test_plain_space_input_has_no_completion_crash():
    assert _completion_texts(" ") == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/set api", "api_key"),
        ("/set godot", "godot_path"),
        ("/set session", "session_dir"),
        ("/set oauth", "oauth_token"),
    ],
)
def test_set_completion_lists_extended_setting_keys(text: str, expected: str):
    completions = _completion_texts(text)
    assert expected in completions


def test_resolve_menu_choice_accepts_index_value_and_alias():
    options = [
        MenuOption("apply", "Apply", aliases=("a",)),
        MenuOption("review", "Review", aliases=("r",)),
    ]

    assert resolve_menu_choice("1", options) == "apply"
    assert resolve_menu_choice("review", options) == "review"
    assert resolve_menu_choice("r", options) == "review"
    assert resolve_menu_choice("", options) is None
    assert resolve_menu_choice("99", options) is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "  ",
        "\t",
        "\x7f",
        "/",
        "/p",
        "/provider ",
        "/provider  ",
        "/effort ",
        "/effort  ",
        "/set ",
        "/set  ",
        "/resume ",
        "/resume  ",
        "cd ",
        "cd  ",
        "/cd ",
        "/cd  ",
    ],
)
def test_completion_edge_inputs_do_not_crash(text: str):
    _completion_texts(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/", "/cd "),
        ("/m", "/mode "),
        ("/me", "/menu"),
        ("/pro", "/provider "),
        ("/eff", "/effort "),
        ("/wor", "/workspace"),
    ],
)
def test_command_prefix_completion_returns_expected_command(text: str, expected: str):
    completions = _completion_texts(text)
    assert expected in completions


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/provider ", {"anthropic", "openai"}),
        ("/effort ", {"low", "medium", "high", "xhigh"}),
    ],
)
def test_argument_completion_trailing_space_lists_candidates(text: str, expected: set[str]):
    completions = set(_completion_texts(text))
    assert expected.issubset(completions)


@pytest.mark.parametrize("text", _FUZZ_CASES)
def test_completion_fuzz_inputs_do_not_crash(text: str):
    _completion_texts(text)


@pytest.mark.parametrize(
    ("text", "cursor_position"),
    [
        ("/provider anthropic", 0),
        ("/provider anthropic", 5),
        ("/provider anthropic", 10),
        ("/provider anthropic", len("/provider anthropic")),
        ("cd /tmp/project", 2),
        ("cd /tmp/project", len("cd /tmp/project")),
        ('"""multiline', 3),
    ],
)
def test_completion_handles_mid_buffer_cursor_positions(text: str, cursor_position: int):
    _completion_texts_at(text, cursor_position)
