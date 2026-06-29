from __future__ import annotations

import os
import select
import sys
from typing import TYPE_CHECKING, Literal

from tools.base import Tool

if TYPE_CHECKING:
    from _keylistener import EscListener
    from plan import PlanModeManager
    from sandbox import SandboxManager

PermissionBehavior = Literal["allow", "deny"]
_PLAN_MODE_ALLOWED_TOOLS = {"Read", "Glob", "Grep", "AskUserQuestion", "EnterPlanMode", "ExitPlanMode"}
_PLAN_MODE_WRITE_TOOLS = {"Edit", "Write"}


class PermissionChecker:
    """Read-only tools are auto-allowed; mutating tools need confirmation."""

    def __init__(self, auto_approve: bool = False, sandbox_manager: SandboxManager | None = None):
        self._auto_approve = auto_approve
        self._sandbox_manager = sandbox_manager
        self._always_allow: set[str] = set()
        self._esc_listener: EscListener | None = None
        self._plan_manager: PlanModeManager | None = None

    def set_plan_manager(self, plan_manager: PlanModeManager) -> None:
        self._plan_manager = plan_manager

    def set_esc_listener(self, listener: EscListener | None) -> None:
        self._esc_listener = listener

    def check(self, tool: Tool, inputs: dict) -> PermissionBehavior:
        if self._plan_manager is not None and self._plan_manager.is_active:
            return self._check_plan_mode(tool, inputs)
        if tool.is_read_only():
            return "allow"
        if (
            tool.name == "Bash"
            and self._sandbox_manager is not None
            and self._sandbox_manager.is_auto_allow()
            and self._sandbox_manager.should_sandbox(str(inputs.get("command", "")))
        ):
            # sandbox + auto_allow_bash 表示：Bash 已被隔离到受限环境，可跳过人工确认。
            return "allow"
        if self._auto_approve or tool.name in self._always_allow:
            return "allow"
        return self._prompt_user(tool, inputs)

    def _check_plan_mode(self, tool: Tool, inputs: dict) -> PermissionBehavior:
        if tool.name in _PLAN_MODE_ALLOWED_TOOLS:
            return "allow"
        if tool.name in _PLAN_MODE_WRITE_TOOLS:
            file_path = str(inputs.get("file_path", ""))
            plan_path = self._plan_manager.plan_file_path if self._plan_manager is not None else None
            if plan_path and file_path == plan_path:
                return "allow"
            print(f"[plan] blocked {tool.name}: plan mode can only write the plan file ({plan_path})")
            return "deny"
        # Plan Mode 的核心隔离：禁止 Bash 和普通写入，避免“还没确认计划就动代码”。
        print(f"[plan] blocked {tool.name}: plan mode only allows read tools, questions, and plan-file edits")
        return "deny"

    def _prompt_user(self, tool: Tool, inputs: dict) -> PermissionBehavior:
        print(f"\n[permission] Tool={tool.name}")
        for key, value in inputs.items():
            print(f"  - {key}: {value}")
        print("Allow? [y]es / [n]o / [a]lways: ", end="", flush=True)

        if self._esc_listener is None or not os.isatty(sys.stdin.fileno()):
            return self._prompt_user_with_input(tool.name)

        self._pause_esc_listener_for_keypress()
        try:
            return self._read_single_key_choice(tool.name)
        finally:
            self._esc_listener.resume()

    def _prompt_user_with_input(self, tool_name: str) -> PermissionBehavior:
        choice = input().strip().lower()
        if choice == "a":
            self._always_allow.add(tool_name)
            return "allow"
        if choice == "y":
            return "allow"
        return "deny"

    def _pause_esc_listener_for_keypress(self) -> None:
        assert self._esc_listener is not None
        try:
            self._esc_listener.pause(restore_terminal=False)
        except TypeError:
            self._esc_listener.pause()

    def _read_single_key_choice(self, tool_name: str) -> PermissionBehavior:
        fd = sys.stdin.fileno()
        while True:
            key = os.read(fd, 1)
            if key == b"\x1b":
                if select.select([fd], [], [], 0.05)[0]:
                    self._drain_pending_input(fd)
                    continue
                print()
                if self._esc_listener is not None:
                    self._esc_listener.pressed = True
                return "deny"

            choice = key.decode("utf-8", errors="ignore").lower()
            print(choice)

            if choice == "a":
                self._always_allow.add(tool_name)
                return "allow"
            if choice == "y":
                return "allow"
            if choice == "n":
                return "deny"
            print("Please enter y, n, or a: ", end="", flush=True)

    @staticmethod
    def _drain_pending_input(fd: int) -> None:
        while select.select([fd], [], [], 0.01)[0]:
            os.read(fd, 64)
