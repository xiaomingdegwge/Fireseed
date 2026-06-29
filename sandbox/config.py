from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import re

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


def save_sandbox_config(config: SandboxConfig, path: Path) -> None:
    """把当前 SandboxConfig 写回 TOML，只替换 [sandbox] 相关段。"""
    section = _render_sandbox_section(config)
    try:
        original = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        original = ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_replace_sandbox_section(original, section), encoding="utf-8")


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


def _render_sandbox_section(config: SandboxConfig) -> str:
    lines = [
        "[sandbox]",
        f"enabled = {_toml_bool(config.enabled)}",
        f"auto_allow_bash = {_toml_bool(config.auto_allow_bash)}",
        f"allow_unsandboxed = {_toml_bool(config.allow_unsandboxed)}",
        f"excluded_commands = {_toml_list(config.excluded_commands)}",
        f"unshare_net = {_toml_bool(config.unshare_net)}",
        "",
        "[sandbox.filesystem]",
        f"allow_write = {_toml_list(config.filesystem.allow_write)}",
        f"deny_write = {_toml_list(config.filesystem.deny_write)}",
        f"deny_read = {_toml_list(config.filesystem.deny_read)}",
        f"allow_read = {_toml_list(config.filesystem.allow_read)}",
    ]
    return "\n".join(lines) + "\n"


def _replace_sandbox_section(original: str, sandbox_section: str) -> str:
    if not original.strip():
        return sandbox_section

    header_re = re.compile(r"^\[(.+)\]\s*$")
    kept: list[str] = []
    insert_at: int | None = None
    in_sandbox = False

    for line in original.splitlines(keepends=True):
        match = header_re.match(line.strip())
        if match:
            name = match.group(1).strip()
            if name == "sandbox" or name.startswith("sandbox."):
                in_sandbox = True
                if insert_at is None:
                    insert_at = len(kept)
                continue
            in_sandbox = False
        if not in_sandbox:
            kept.append(line)

    if insert_at is None:
        return original.rstrip("\n") + "\n\n" + sandbox_section

    before = "".join(kept[:insert_at]).rstrip("\n")
    after = "".join(kept[insert_at:]).lstrip("\n")
    parts = [part for part in (before, sandbox_section.strip(), after) if part]
    return "\n\n".join(parts) + "\n"


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _toml_list(values: list[str]) -> str:
    return "[" + ", ".join(f'"{value}"' for value in values) + "]"
