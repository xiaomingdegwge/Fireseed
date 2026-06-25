from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class SandboxFilesystemConfig:
    # 沙箱文件系统策略：默认只允许当前工作目录可写，其它根路径只读。
    allow_write: list[str] = field(default_factory=lambda: ["."])
    deny_write: list[str] = field(default_factory=list)
    deny_read: list[str] = field(default_factory=list)
    allow_read: list[str] = field(default_factory=list)


@dataclass
class SandboxConfig:
    # Sandbox 主配置，对齐 cc-mini 的 [sandbox] TOML 段。
    enabled: bool = False
    auto_allow_bash: bool = False
    allow_unsandboxed: bool = False
    excluded_commands: list[str] = field(default_factory=list)
    filesystem: SandboxFilesystemConfig = field(default_factory=SandboxFilesystemConfig)
    unshare_net: bool = True


def load_sandbox_config(config_paths: tuple[Path, ...] = ()) -> SandboxConfig:
    if not config_paths:
        config_paths = (
            Path.home() / ".config" / "fireseed" / "config.toml",
            Path.cwd() / ".fireseed.toml",
        )

    merged: dict[str, Any] = {}
    for path in config_paths:
        if not path.exists():
            continue
        try:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        sandbox_section = data.get("sandbox")
        if isinstance(sandbox_section, dict):
            merged.update(sandbox_section)

    return _dict_to_config(merged)


def _dict_to_config(raw: dict[str, Any]) -> SandboxConfig:
    filesystem_raw = raw.get("filesystem", {})
    if not isinstance(filesystem_raw, dict):
        filesystem_raw = {}

    filesystem = SandboxFilesystemConfig(
        allow_write=_string_list(filesystem_raw.get("allow_write"), default=["."]),
        deny_write=_string_list(filesystem_raw.get("deny_write")),
        deny_read=_string_list(filesystem_raw.get("deny_read")),
        allow_read=_string_list(filesystem_raw.get("allow_read")),
    )
    return SandboxConfig(
        enabled=bool(raw.get("enabled", False)),
        auto_allow_bash=bool(raw.get("auto_allow_bash", False)),
        allow_unsandboxed=bool(raw.get("allow_unsandboxed", False)),
        excluded_commands=_string_list(raw.get("excluded_commands")),
        filesystem=filesystem,
        unshare_net=bool(raw.get("unshare_net", True)),
    )


def _string_list(value: Any, default: list[str] | None = None) -> list[str]:
    if value is None:
        return list(default or [])
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]
