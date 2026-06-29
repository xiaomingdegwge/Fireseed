from __future__ import annotations

import os
import select
import sys
from typing import TYPE_CHECKING, Literal

from tools.base import Tool

if TYPE_CHECKING:
    from _keylistener import EscListener
    from sandbox import SandboxManager

PermissionBehavior = Literal["allow", "deny"]


class PermissionChecker:
    """Read-only tools are auto-allowed; mutating tools need confirmation."""

    def __init__(self, auto_approve: bool = False, sandbox_manager: SandboxManager | None = None):
        self._auto_approve = auto_approve
        self._sandbox_manager = sandbox_manager
        self._always_allow: set[str] = set()
        self._esc_listener: EscListener | None = None

    def set_esc_listener(self, listener: EscListener | None) -> None:
        self._esc_listener = listener

    def check(self, tool: Tool, inputs: dict) -> PermissionBehavior:
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
