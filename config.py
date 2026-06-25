from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llm import default_model_for_provider, validate_provider

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = default_model_for_provider(DEFAULT_PROVIDER)
_DEFAULT_CONFIG_PATHS = (
    Path.home() / ".config" / "fireseed" / "config.toml",
    Path.cwd() / ".fireseed.toml",
)

_MODEL_ALIASES = {
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
    "haiku": "claude-haiku-4-5-20251001",
    "best": "claude-opus-4-6",
    "claude-opus-4.6": "claude-opus-4-6",
    "claude-opus-4.5": "claude-opus-4-5",
    "claude-opus-4.1": "claude-opus-4-1",
    "claude-sonnet-4.6": "claude-sonnet-4-6",
    "claude-sonnet-4.5": "claude-sonnet-4-5",
    "claude-3.7-sonnet": "claude-3-7-sonnet",
    "claude-3.5-sonnet": "claude-3-5-sonnet",
    "claude-3.5-haiku": "claude-3-5-haiku",
}

_MODEL_MAX_TOKENS = (
    ("claude-opus-4-6", 64_000),
    ("claude-sonnet-4-6", 32_000),
    ("claude-opus-4-5", 32_000),
    ("claude-sonnet-4-5", 32_000),
    ("claude-sonnet-4", 32_000),
    ("claude-haiku-4", 32_000),
    ("claude-opus-4-1", 32_000),
    ("claude-opus-4", 32_000),
    ("claude-3-7-sonnet", 32_000),
    ("claude-3-5-sonnet", 8_192),
    ("claude-3-5-haiku", 8_192),
    ("claude-3-haiku", 4_096),
)


@dataclass(frozen=True)
class AppConfig:
    provider: str
    api_key: str | None
    base_url: str | None
    model: str
    max_tokens: int
    effort: str | None
    auto_approve: bool
    session_dir: str
    config_paths: tuple[Path, ...] = ()


def resolve_model(model: str | None, provider: str = DEFAULT_PROVIDER) -> str:
    provider = validate_provider(provider)
    if not model:
        return default_model_for_provider(provider)
    normalized = model.strip()
    if provider != "anthropic":
        return normalized
    return _MODEL_ALIASES.get(normalized, normalized)


def default_max_tokens_for_model(model: str | None, provider: str = DEFAULT_PROVIDER) -> int:
    provider = validate_provider(provider)
    resolved = resolve_model(model, provider=provider)
    if provider == "mock":
        return 1024
    if provider == "openai":
        for prefix, limit in (
            ("gpt-5", 8192),
            ("gpt-4.1", 16_384),
            ("gpt-4o", 16_384),
            ("o1", 32_768),
            ("o3", 32_768),
            ("o4", 32_768),
        ):
            if resolved.startswith(prefix):
                return limit
        return 8192

    for prefix, limit in _MODEL_MAX_TOKENS:
        if resolved.startswith(prefix):
            return limit
    return 32_000


def load_app_config(args: argparse.Namespace) -> AppConfig:
    # 配置优先级：CLI 参数 > 环境变量 > TOML 文件 > 默认值。
    # FIRESEED_* 是独立仓库的新变量；CC_DUP_* 保留给旧配置兼容。
    file_values, config_paths = _load_file_values(getattr(args, "config", None))
    env_values = _load_env_values()
    bashrc_exports = _read_bashrc_exports(os.path.expanduser("~/.bashrc"))

    raw_provider = (
        getattr(args, "provider", None)
        or env_values.get("provider")
        or file_values["top"].get("provider")
        or _infer_provider(file_values["providers"])
    )
    provider = validate_provider(raw_provider)

    provider_file_values = file_values["providers"].get(provider, {})

    def file_value(key: str) -> Any:
        if key in file_values["top"]:
            return file_values["top"][key]
        return provider_file_values.get(key)

    raw_model = getattr(args, "model", None) or env_values.get("model") or file_value("model")
    model = resolve_model(raw_model, provider=provider)

    raw_max_tokens = (
        getattr(args, "max_tokens", None)
        if getattr(args, "max_tokens", None) is not None
        else env_values.get("max_tokens", file_value("max_tokens"))
    )
    max_tokens = _parse_max_tokens(
        raw_max_tokens,
        default=default_max_tokens_for_model(model, provider=provider),
    )

    raw_effort = getattr(args, "effort", None)
    if raw_effort is None:
        raw_effort = env_values.get("effort", file_value("effort"))

    session_dir = (
        getattr(args, "session_dir", None)
        or env_values.get("session_dir")
        or file_value("session_dir")
        or ".cc_dup_sessions"
    )

    api_key = (
        getattr(args, "api_key", None)
        or _provider_env_value(env_values, provider, "api_key")
        or file_value("api_key")
        or _resolve_api_key_from_bashrc(provider, bashrc_exports)
    )
    base_url = (
        getattr(args, "base_url", None)
        or _provider_env_value(env_values, provider, "base_url")
        or file_value("base_url")
        or _resolve_base_url_from_bashrc(provider, bashrc_exports)
    )

    return AppConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_tokens=max_tokens,
        effort=_parse_effort(raw_effort),
        auto_approve=bool(getattr(args, "auto_approve", False)),
        session_dir=str(Path(str(session_dir)).expanduser()),
        config_paths=config_paths,
    )


def _load_file_values(explicit_path: str | None) -> tuple[dict[str, Any], tuple[Path, ...]]:
    values: dict[str, Any] = {
        "top": {},
        "providers": {"anthropic": {}, "openai": {}, "mock": {}},
    }
    loaded_paths: list[Path] = []

    paths = [Path(explicit_path).expanduser()] if explicit_path else list(_DEFAULT_CONFIG_PATHS)
    for path in paths:
        if not path.exists():
            if explicit_path:
                raise ValueError(f"Config file not found: {path}")
            continue
        _merge_file_values(values, _read_config_file(path))
        loaded_paths.append(path)
        if explicit_path:
            break

    return values, tuple(loaded_paths)


def _read_config_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML in config file {path}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read config file {path}: {exc}") from exc

    values: dict[str, Any] = {
        "top": {},
        "providers": {"anthropic": {}, "openai": {}, "mock": {}},
    }
    for provider in ("anthropic", "openai", "mock"):
        section = data.get(provider, {})
        if isinstance(section, dict):
            values["providers"][provider].update(section)

    for key in ("provider", "api_key", "base_url", "model", "max_tokens", "effort", "session_dir"):
        if key in data:
            values["top"][key] = data[key]
    return values


def _load_env_values() -> dict[str, Any]:
    values: dict[str, Any] = {}
    mapping = {
        "provider": ("FIRESEED_PROVIDER", "CC_DUP_PROVIDER"),
        "model": ("FIRESEED_MODEL", "CC_DUP_MODEL"),
        "max_tokens": ("FIRESEED_MAX_TOKENS", "CC_DUP_MAX_TOKENS"),
        "effort": ("FIRESEED_EFFORT", "CC_DUP_EFFORT"),
        "session_dir": ("FIRESEED_SESSION_DIR", "CC_DUP_SESSION_DIR"),
        "api_key": ("FIRESEED_API_KEY", "CC_DUP_API_KEY"),
        "base_url": ("FIRESEED_BASE_URL", "CC_DUP_BASE_URL"),
    }
    for key, env_names in mapping.items():
        value = _first_env(env_names)
        if value:
            values[key] = value

    provider_specific = {
        "anthropic_api_key": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
        "anthropic_base_url": ("ANTHROPIC_BASE_URL",),
        "openai_api_key": ("OPENAI_API_KEY",),
        "openai_base_url": ("OPENAI_BASE_URL",),
    }
    for key, env_names in provider_specific.items():
        value = _first_env(env_names)
        if value:
            values[key] = value
    return values


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _parse_max_tokens(raw_value: Any, default: int) -> int:
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid max_tokens value: {raw_value!r}") from exc
    if value <= 0:
        raise ValueError("max_tokens must be a positive integer")
    return value


def _parse_effort(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    normalized = str(raw_value).strip().lower()
    if normalized not in {"low", "medium", "high"}:
        raise ValueError("effort must be one of: low, medium, high")
    return normalized


def _infer_provider(provider_values: dict[str, dict[str, Any]]) -> str:
    if provider_values.get("openai") and not provider_values.get("anthropic"):
        return "openai"
    if provider_values.get("mock") and not provider_values.get("anthropic"):
        return "mock"
    return DEFAULT_PROVIDER


def _merge_file_values(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    target["top"].update(incoming.get("top", {}))
    for provider in ("anthropic", "openai", "mock"):
        target["providers"][provider].update(incoming.get("providers", {}).get(provider, {}))


def _provider_env_value(env_values: dict[str, Any], provider: str, key: str) -> str | None:
    generic = env_values.get(key)
    if generic:
        return str(generic)
    provider_key = f"{provider}_{key}"
    value = env_values.get(provider_key)
    return str(value) if value else None


def _resolve_api_key_from_bashrc(provider: str, bashrc_exports: dict[str, str]) -> str | None:
    if provider == "openai":
        candidates = ("FIRESEED_API_KEY", "CC_DUP_API_KEY", "OPENAI_API_KEY")
    elif provider == "anthropic":
        candidates = (
            "FIRESEED_API_KEY",
            "CC_DUP_API_KEY",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
        )
    else:
        candidates = ("FIRESEED_API_KEY", "CC_DUP_API_KEY")
    for key in candidates:
        if bashrc_exports.get(key):
            return bashrc_exports[key]
    return None


def _resolve_base_url_from_bashrc(provider: str, bashrc_exports: dict[str, str]) -> str | None:
    candidates = ["FIRESEED_BASE_URL", "CC_DUP_BASE_URL"]
    if provider == "openai":
        candidates.append("OPENAI_BASE_URL")
    if provider == "anthropic":
        candidates.append("ANTHROPIC_BASE_URL")
    for key in candidates:
        if bashrc_exports.get(key):
            return bashrc_exports[key]
    return None


def _read_bashrc_exports(path: str) -> dict[str, str]:
    exports: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except Exception:
        return exports

    pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = pattern.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        exports[key] = value
    return exports
