from argparse import Namespace

import pytest

from config import default_max_tokens_for_model, load_app_config, resolve_model


_CONFIG_ENV_NAMES = (
    "FIRESEED_PROVIDER",
    "FIRESEED_MODEL",
    "FIRESEED_MAX_TOKENS",
    "FIRESEED_API_KEY",
    "FIRESEED_BASE_URL",
    "FIRESEED_EFFORT",
    "FIRESEED_SESSION_DIR",
    "CC_DUP_PROVIDER",
    "CC_DUP_MODEL",
    "CC_DUP_MAX_TOKENS",
    "CC_DUP_API_KEY",
    "CC_DUP_BASE_URL",
    "CC_DUP_EFFORT",
    "CC_DUP_SESSION_DIR",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
)


def _clear_config_env(monkeypatch) -> None:
    for name in _CONFIG_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def _args(**overrides):
    values = {
        "provider": None,
        "api_key": None,
        "base_url": None,
        "model": None,
        "max_tokens": None,
        "effort": None,
        "auto_approve": False,
        "session_dir": None,
        "config": None,
    }
    values.update(overrides)
    return Namespace(**values)


def test_resolve_model_supports_anthropic_aliases() -> None:
    assert resolve_model("sonnet") == "claude-sonnet-4-6"
    assert resolve_model("claude-3.7-sonnet") == "claude-3-7-sonnet"


def test_default_max_tokens_follow_model_family() -> None:
    assert default_max_tokens_for_model("claude-opus-4-6") == 64_000
    assert default_max_tokens_for_model("claude-sonnet-4") == 32_000
    assert default_max_tokens_for_model("claude-3-5-haiku") == 8_192
    assert default_max_tokens_for_model("gpt-4.1-mini", provider="openai") == 16_384


def test_load_app_config_reads_anthropic_toml_section(tmp_path, monkeypatch) -> None:
    _clear_config_env(monkeypatch)

    config_path = tmp_path / "fireseed.toml"
    config_path.write_text(
        '[anthropic]\n'
        'api_key = "file-key"\n'
        'base_url = "https://anthropic.test"\n'
        'model = "claude-3.7-sonnet"\n',
        encoding="utf-8",
    )

    config = load_app_config(_args(config=str(config_path)))

    assert config.provider == "anthropic"
    assert config.api_key == "file-key"
    assert config.base_url == "https://anthropic.test"
    assert config.model == "claude-3-7-sonnet"
    assert config.max_tokens == 32_000
    assert config.config_paths == (config_path,)


def test_load_app_config_reads_openai_toml_section(tmp_path, monkeypatch) -> None:
    _clear_config_env(monkeypatch)

    config_path = tmp_path / "fireseed.toml"
    config_path.write_text(
        'provider = "openai"\n'
        '[openai]\n'
        'api_key = "openai-key"\n'
        'base_url = "https://openai.test/v1"\n'
        'model = "gpt-4.1-mini"\n'
        'max_tokens = 4096\n'
        'effort = "low"\n',
        encoding="utf-8",
    )

    config = load_app_config(_args(config=str(config_path)))

    assert config.provider == "openai"
    assert config.api_key == "openai-key"
    assert config.base_url == "https://openai.test/v1"
    assert config.model == "gpt-4.1-mini"
    assert config.max_tokens == 4096
    assert config.effort == "low"


def test_cli_overrides_env_and_toml(tmp_path, monkeypatch) -> None:
    _clear_config_env(monkeypatch)
    config_path = tmp_path / "fireseed.toml"
    config_path.write_text(
        'model = "haiku"\n'
        'max_tokens = 2048\n'
        'api_key = "file-key"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("FIRESEED_MODEL", "opus")
    monkeypatch.setenv("FIRESEED_MAX_TOKENS", "1234")
    monkeypatch.setenv("FIRESEED_API_KEY", "env-key")

    config = load_app_config(
        _args(
            config=str(config_path),
            model="sonnet",
            max_tokens=999,
            api_key="cli-key",
        )
    )

    assert config.model == "claude-sonnet-4-6"
    assert config.max_tokens == 999
    assert config.api_key == "cli-key"


def test_load_app_config_rejects_invalid_max_tokens(tmp_path) -> None:
    config_path = tmp_path / "fireseed.toml"
    config_path.write_text('max_tokens = "nope"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid max_tokens"):
        load_app_config(_args(config=str(config_path)))
