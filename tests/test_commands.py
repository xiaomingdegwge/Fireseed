from commands import CommandContext, handle_command, parse_command


class DummyEngine:
    def __init__(self) -> None:
        self.messages = [{"role": "user", "content": "hello"}]

    def set_messages(self, messages):
        self.messages = messages


def test_parse_command_detects_slash_command() -> None:
    assert parse_command("/compact keep important files") == (
        "compact",
        "keep important files",
    )


def test_parse_command_ignores_normal_input() -> None:
    assert parse_command("hello /compact") is None


def test_clear_command_resets_in_memory_messages(capsys, tmp_path) -> None:
    engine = DummyEngine()
    ctx = CommandContext(
        engine=engine,  # type: ignore[arg-type]
        session_store=None,  # type: ignore[arg-type]
        session_dir=str(tmp_path),
        cwd=str(tmp_path),
        model="mock-sonnet",
    )

    result = handle_command("clear", "", ctx)

    assert result.handled
    assert engine.messages == []
    assert "conversation reset" in capsys.readouterr().out


def test_unknown_command_prints_help_hint(capsys, tmp_path) -> None:
    ctx = CommandContext(
        engine=DummyEngine(),  # type: ignore[arg-type]
        session_store=None,  # type: ignore[arg-type]
        session_dir=str(tmp_path),
        cwd=str(tmp_path),
        model="mock-sonnet",
    )

    result = handle_command("missing", "", ctx)

    assert result.handled
    assert "unknown command" in capsys.readouterr().out
