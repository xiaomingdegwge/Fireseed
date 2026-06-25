from __future__ import annotations

import os
import shlex
from pathlib import Path

from .config import SandboxConfig


def build_bwrap_args(command: str, config: SandboxConfig, cwd: str | None = None) -> list[str]:
    cwd = cwd or os.getcwd()
    args = ["bwrap"]
    # 隔离核心：根目录默认只读，避免 Bash 裸跑时误改系统文件。
    args.extend(["--ro-bind", "/", "/"])
    args.extend(["--dev", "/dev"])
    args.extend(["--proc", "/proc"])
    # /tmp 使用临时内存文件系统，命令写临时文件不会污染宿主机 /tmp。
    args.extend(["--tmpfs", "/tmp"])

    filesystem = config.filesystem
    # allow_write 再把指定路径重新挂成可写；默认 "." 表示当前项目目录可写。
    for write_path in _resolve_paths(filesystem.allow_write, cwd):
        if os.path.exists(write_path):
            args.extend(["--bind", write_path, write_path])

    # deny_write 可把 allow_write 中的敏感文件重新压回只读，比如 .fireseed.toml。
    for deny_path in _resolve_paths(filesystem.deny_write, cwd):
        if os.path.exists(deny_path):
            args.extend(["--ro-bind", deny_path, deny_path])

    # deny_read 遮住真实路径：目录用空 tmpfs，文件用 /dev/null 只读绑定。
    # 注意 bwrap 的 --tmpfs 只能挂目录，直接挂 .env 文件会报 "Not a directory"。
    for deny_path in _resolve_paths(filesystem.deny_read, cwd):
        if os.path.exists(deny_path):
            if os.path.isdir(deny_path):
                args.extend(["--tmpfs", deny_path])
            else:
                args.extend(["--ro-bind", "/dev/null", deny_path])

    args.extend(["--bind", cwd, cwd])
    args.extend(["--chdir", cwd])
    if config.unshare_net:
        # 网络 namespace 隔离：阻止 curl/wget/pip 等命令直接访问外网。
        args.append("--unshare-net")
    # 进程 namespace 隔离；父进程退出时，sandbox 内子进程也跟着退出。
    args.extend(["--die-with-parent", "--unshare-pid"])

    for protected_path in _get_protected_paths(cwd):
        if os.path.exists(protected_path):
            args.extend(["--ro-bind", protected_path, protected_path])

    args.extend(["--", "/bin/sh", "-c", command])
    return args


def wrap_command(command: str, config: SandboxConfig, cwd: str | None = None) -> str:
    return " ".join(shlex.quote(arg) for arg in build_bwrap_args(command, config, cwd))


def _resolve_paths(patterns: list[str], cwd: str) -> list[str]:
    resolved: list[str] = []
    for pattern in patterns:
        if pattern == ".":
            resolved.append(cwd)
        elif pattern.startswith("~/"):
            resolved.append(str(Path.home() / pattern[2:]))
        elif pattern.startswith("/"):
            resolved.append(pattern)
        else:
            resolved.append(str(Path(cwd) / pattern))
    return resolved


def _get_protected_paths(cwd: str) -> list[str]:
    candidates = [
        Path(cwd) / ".fireseed.toml",
        Path.home() / ".config" / "fireseed" / "config.toml",
        Path(cwd) / "CLAUDE.md",
    ]
    return [str(path) for path in candidates if path.exists()]
