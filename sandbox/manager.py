from __future__ import annotations

from .checker import DependencyCheck, check_dependencies
from .command_matcher import contains_excluded_command
from .config import SandboxConfig, save_sandbox_config
from .wrapper import build_bwrap_args, wrap_command


class SandboxManager:
    # Sandbox 对外门面：app.py 创建一次，然后 BashTool/PermissionChecker 通过它查询策略。
    # 业务链路：配置启用且 bwrap 可用 -> 命令不在排除列表 -> BashTool 执行前包进 bwrap。
    def __init__(self, config: SandboxConfig | None = None):
        self._config = config or SandboxConfig()
        self._dependency_check: DependencyCheck | None = None

    @property
    def config(self) -> SandboxConfig:
        return self._config

    def check_dependencies(self) -> DependencyCheck:
        if self._dependency_check is None:
            self._dependency_check = check_dependencies()
        return self._dependency_check

    def is_enabled(self) -> bool:
        return self._config.enabled and self.check_dependencies().ok

    def is_auto_allow(self) -> bool:
        return self.is_enabled() and self._config.auto_allow_bash

    def should_sandbox(self, command: str, dangerously_disable: bool = False) -> bool:
        # 是否进入 sandbox 的唯一判断口；excluded_commands 用于保留少量必须裸跑的命令。
        if not self.is_enabled():
            return False
        if dangerously_disable and self._config.allow_unsandboxed:
            return False
        if not command.strip():
            return False
        if contains_excluded_command(command, self._config.excluded_commands):
            return False
        return True

    def wrap(self, command: str, cwd: str | None = None) -> str:
        return wrap_command(command, self._config, cwd)

    def build_args(self, command: str, cwd: str | None = None) -> list[str]:
        return build_bwrap_args(command, self._config, cwd)

    def set_mode(self, mode: str) -> str:
        if mode == "auto-allow":
            self._config.enabled = True
            self._config.auto_allow_bash = True
            return "sandbox mode: auto-allow"
        if mode == "regular":
            self._config.enabled = True
            self._config.auto_allow_bash = False
            return "sandbox mode: regular"
        if mode == "disabled":
            self._config.enabled = False
            self._config.auto_allow_bash = False
            return "sandbox mode: disabled"
        return f"unknown sandbox mode: {mode}"

    def add_excluded_command(self, pattern: str) -> str:
        if pattern and pattern not in self._config.excluded_commands:
            self._config.excluded_commands.append(pattern)
        return f"excluded command pattern: {pattern}"

    def save(self, path) -> None:
        save_sandbox_config(self._config, path)
