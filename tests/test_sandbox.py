from sandbox.command_matcher import contains_excluded_command, parse_rule, RuleType
from sandbox.config import SandboxConfig, SandboxFilesystemConfig, load_sandbox_config, save_sandbox_config
from sandbox.manager import SandboxManager
from sandbox.wrapper import _resolve_paths, build_bwrap_args, wrap_command
from permissions import PermissionChecker
from tools import BashTool


def test_load_sandbox_config_from_toml(tmp_path) -> None:
    config_path = tmp_path / "fireseed.toml"
    config_path.write_text(
        "[sandbox]\n"
        "enabled = true\n"
        "auto_allow_bash = true\n"
        'excluded_commands = ["docker *"]\n'
        "unshare_net = false\n"
        "\n"
        "[sandbox.filesystem]\n"
        'allow_write = [".", "build"]\n'
        'deny_read = ["secret"]\n',
        encoding="utf-8",
    )

    config = load_sandbox_config((config_path,))

    assert config.enabled
    assert config.auto_allow_bash
    assert config.excluded_commands == ["docker *"]
    assert not config.unshare_net
    assert config.filesystem.allow_write == [".", "build"]
    assert config.filesystem.deny_read == ["secret"]


def test_command_matcher_supports_exact_prefix_wildcard_and_env_prefix() -> None:
    assert parse_rule("git").type == RuleType.EXACT
    assert parse_rule("npm run").type == RuleType.PREFIX
    assert parse_rule("docker *").type == RuleType.WILDCARD

    assert contains_excluded_command("docker build .", ["docker *"])
    assert contains_excluded_command("FOO=1 npm test", ["npm test"])
    assert contains_excluded_command("cd /tmp && npm test", ["npm test"])
    assert not contains_excluded_command("git status", ["git"])


def test_build_bwrap_args_contains_command_and_mounts(tmp_path) -> None:
    protected = tmp_path / ".fireseed.toml"
    protected.write_text("[sandbox]\n", encoding="utf-8")
    config = SandboxConfig(
        enabled=True,
        filesystem=SandboxFilesystemConfig(deny_write=[str(protected)]),
        unshare_net=False,
    )

    args = build_bwrap_args("echo hello", config, cwd=str(tmp_path))

    assert args[0] == "bwrap"
    assert "--chdir" in args
    assert "--unshare-net" not in args
    assert args[-4:] == ["--", "/bin/sh", "-c", "echo hello"]
    assert str(protected) in args


def test_deny_read_file_uses_dev_null_bind(tmp_path) -> None:
    secret = tmp_path / ".env"
    secret.write_text("SECRET=value\n", encoding="utf-8")
    config = SandboxConfig(
        enabled=True,
        filesystem=SandboxFilesystemConfig(deny_read=[str(secret)]),
    )

    args = build_bwrap_args("cat .env", config, cwd=str(tmp_path))

    assert ["--ro-bind", "/dev/null", str(secret)] == args[args.index("/dev/null") - 1:args.index("/dev/null") + 2]
    assert not any(args[index] == "--tmpfs" and args[index + 1] == str(secret) for index in range(len(args) - 1))


def test_wrap_command_quotes_shell_command(tmp_path) -> None:
    wrapped = wrap_command("echo 'hello world'", SandboxConfig(enabled=True), cwd=str(tmp_path))

    assert wrapped.startswith("bwrap ")
    assert "'echo '\"'\"'hello world'\"'\"''" in wrapped


def test_resolve_paths() -> None:
    assert _resolve_paths(["."], "/work") == ["/work"]
    assert _resolve_paths(["build"], "/work") == ["/work/build"]
    assert _resolve_paths(["/etc"], "/work") == ["/etc"]


def test_sandbox_manager_decides_when_to_sandbox(monkeypatch) -> None:
    manager = SandboxManager(SandboxConfig(enabled=True, excluded_commands=["docker *"]))
    monkeypatch.setattr(manager, "check_dependencies", lambda: type("Check", (), {"ok": True})())

    assert manager.should_sandbox("echo hello")
    assert not manager.should_sandbox("docker build .")


def test_sandbox_manager_mode_and_exclude() -> None:
    manager = SandboxManager(SandboxConfig())

    assert "auto-allow" in manager.set_mode("auto-allow")
    assert manager.config.enabled
    assert manager.config.auto_allow_bash

    manager.add_excluded_command("docker *")
    manager.add_excluded_command("docker *")
    assert manager.config.excluded_commands == ["docker *"]


def test_save_sandbox_config_preserves_other_sections(tmp_path) -> None:
    config_path = tmp_path / ".fireseed.toml"
    config_path.write_text('provider = "mock"\n\n[openai]\nmodel = "gpt-4.1-mini"\n', encoding="utf-8")
    config = SandboxConfig(enabled=True, auto_allow_bash=True, excluded_commands=["docker *"])

    save_sandbox_config(config, config_path)

    content = config_path.read_text(encoding="utf-8")
    assert 'provider = "mock"' in content
    assert "[openai]" in content
    assert "[sandbox]" in content
    assert "auto_allow_bash = true" in content
    assert 'excluded_commands = ["docker *"]' in content


def test_permission_auto_allows_sandboxed_bash(monkeypatch) -> None:
    manager = SandboxManager(SandboxConfig(enabled=True, auto_allow_bash=True))
    monkeypatch.setattr(manager, "check_dependencies", lambda: type("Check", (), {"ok": True})())
    checker = PermissionChecker(sandbox_manager=manager)

    assert checker.check(BashTool(manager), {"command": "echo hello"}) == "allow"


def test_bash_tool_wraps_command_when_sandbox_enabled(monkeypatch, tmp_path) -> None:
    manager = SandboxManager(SandboxConfig(enabled=True))
    monkeypatch.setattr(manager, "check_dependencies", lambda: type("Check", (), {"ok": True})())

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command

        class Completed:
            returncode = 0
            stdout = "ok"

        return Completed()

    monkeypatch.setattr("tools.bash.subprocess.run", fake_run)

    result = BashTool(manager, cwd=str(tmp_path)).execute(command="echo ok")

    assert not result.is_error
    assert captured["command"].startswith("bwrap ")
    assert result.content.startswith("[sandboxed]")
