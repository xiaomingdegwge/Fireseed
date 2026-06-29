from commands import CommandContext, handle_command, parse_command
from sandbox import SandboxConfig, SandboxManager


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


def test_sandbox_status_command(capsys, tmp_path, monkeypatch) -> None:
    manager = SandboxManager(SandboxConfig(enabled=True, auto_allow_bash=True))
    monkeypatch.setattr(manager, "check_dependencies", lambda: type("Check", (), {"ok": True, "errors": [], "warnings": []})())
    ctx = CommandContext(
        engine=DummyEngine(),  # type: ignore[arg-type]
        session_store=None,  # type: ignore[arg-type]
        session_dir=str(tmp_path),
        cwd=str(tmp_path),
        model="mock-sonnet",
        sandbox_manager=manager,
        sandbox_config_path=str(tmp_path / ".fireseed.toml"),
    )

    handle_command("sandbox", "", ctx)

    output = capsys.readouterr().out
    assert "effective: on" in output
    assert "mode: auto-allow" in output


def test_sandbox_mode_command_saves_config(capsys, tmp_path, monkeypatch) -> None:
    manager = SandboxManager(SandboxConfig())
    monkeypatch.setattr(manager, "check_dependencies", lambda: type("Check", (), {"ok": True, "errors": [], "warnings": []})())
    config_path = tmp_path / ".fireseed.toml"
    ctx = CommandContext(
        engine=DummyEngine(),  # type: ignore[arg-type]
        session_store=None,  # type: ignore[arg-type]
        session_dir=str(tmp_path),
        cwd=str(tmp_path),
        model="mock-sonnet",
        sandbox_manager=manager,
        sandbox_config_path=str(config_path),
    )

    handle_command("sandbox", "mode regular", ctx)

    assert manager.config.enabled
    assert not manager.config.auto_allow_bash
    assert "enabled = true" in config_path.read_text(encoding="utf-8")
    assert "saved" in capsys.readouterr().out


def test_sandbox_exclude_command_saves_pattern(tmp_path) -> None:
    manager = SandboxManager(SandboxConfig())
    config_path = tmp_path / ".fireseed.toml"
    ctx = CommandContext(
        engine=DummyEngine(),  # type: ignore[arg-type]
        session_store=None,  # type: ignore[arg-type]
        session_dir=str(tmp_path),
        cwd=str(tmp_path),
        model="mock-sonnet",
        sandbox_manager=manager,
        sandbox_config_path=str(config_path),
    )

    handle_command("sandbox", "exclude docker *", ctx)

    assert manager.config.excluded_commands == ["docker *"]
    assert 'excluded_commands = ["docker *"]' in config_path.read_text(encoding="utf-8")
