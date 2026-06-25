from __future__ import annotations

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
        if self._esc_listener is not None:
            self._esc_listener.pause()
        try:
            print(f"\n[permission] Tool={tool.name}")
            for key, value in inputs.items():
                print(f"  - {key}: {value}")
            choice = input("Allow? [y]es / [n]o / [a]lways: ").strip().lower()
            if choice == "a":
                self._always_allow.add(tool.name)
                return "allow"
            if choice == "y":
                return "allow"
            return "deny"
        finally:
            if self._esc_listener is not None:
                self._esc_listener.resume()
