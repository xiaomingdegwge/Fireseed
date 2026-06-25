import builtins

from input_ui import read_user_input, slash_command_words


def test_slash_command_words_match_registered_commands() -> None:
    words = slash_command_words()

    assert "/help" in words
    assert "/compact" in words
    assert "/cost" in words


def test_read_user_input_falls_back_to_builtin_input(monkeypatch) -> None:
    monkeypatch.setattr(builtins, "input", lambda _prompt: "  hello  ")

    assert read_user_input(None) == "hello"
