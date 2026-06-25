from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

from .base import Tool, ToolResult

if TYPE_CHECKING:
    from sandbox import SandboxManager


class BashTool(Tool):
    name = "Bash"
    description = "Execute a shell command."
    input_schema = {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    }

    def __init__(self, sandbox_manager: SandboxManager | None = None, cwd: str | None = None):
        self._sandbox_manager = sandbox_manager
        self._cwd = cwd or os.getcwd()

    def is_read_only(self) -> bool:
        return False

    def get_activity_description(self, **kwargs):
        return "Running shell command"

    def execute(self, **kwargs):
        command = kwargs.get("command", "")
        if not command:
            return ToolResult("Missing command", is_error=True)
        # MAMBA8B: Bash sandbox hook. 权限通过后，BashTool 在真正执行前
        # 根据 SandboxManager 决定是否把命令包进 bubblewrap；核心目的是限制写入、
        # 隐藏敏感文件、可选断网，让模型生成的 Bash 不直接裸跑在宿主机上。
        sandboxed = False
        if self._sandbox_manager is not None and self._sandbox_manager.should_sandbox(command):
            command = self._sandbox_manager.wrap(command, cwd=self._cwd)
            sandboxed = True
        try:
            completed = subprocess.run(
                command,
                shell=True,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
            )
            output = completed.stdout or ""
            if completed.returncode != 0:
                return ToolResult(
                    content=f"{'[sandboxed] ' if sandboxed else ''}[exit {completed.returncode}]\n{output}",
                    is_error=True,
                )
            content = output if output else "(no output)"
            if sandboxed:
                content = "[sandboxed]\n" + content
            return ToolResult(content=content)
        except Exception as exc:
            return ToolResult(content=f"Bash error: {exc}", is_error=True)
