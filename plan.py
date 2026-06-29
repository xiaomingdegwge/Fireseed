from __future__ import annotations

import random
from pathlib import Path

from tools.base import Tool

_ADJECTIVES = [
    "amber", "azure", "bright", "calm", "clear", "crisp", "fresh", "gentle",
    "golden", "green", "keen", "quiet", "rapid", "sharp", "steady", "vivid",
]
_NOUNS = [
    "arrow", "brook", "cloud", "comet", "dawn", "ember", "forge", "garden",
    "harbor", "lake", "leaf", "moon", "river", "spark", "stone", "wave",
]


def _generate_slug() -> str:
    return f"{random.choice(_ADJECTIVES)}-{random.choice(_NOUNS)}-{random.choice(_NOUNS)}"


def _get_plans_dir() -> Path:
    plans_dir = Path.home() / ".fireseed" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    return plans_dir


class PlanModeManager:
    """管理 Plan Mode 生命周期：进入、退出、切换工具集和注入计划提示词。"""

    def __init__(self) -> None:
        self._engine = None
        self._active = False
        self._plan_file: Path | None = None
        self._saved_tools: list[Tool] | None = None
        self._saved_prompt: str | None = None

    def bind_engine(self, engine) -> None:
        self._engine = engine

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def plan_file_path(self) -> str | None:
        return str(self._plan_file) if self._plan_file else None

    def get_plan_content(self) -> str | None:
        if self._plan_file is None or not self._plan_file.exists():
            return None
        try:
            return self._plan_file.read_text(encoding="utf-8")
        except OSError:
            return None

    def enter(self) -> str:
        assert self._engine is not None, "PlanModeManager not bound to engine"
        if self._active:
            return f"Already in plan mode. Plan file: {self._plan_file}"

        self._plan_file = self._new_plan_file()
        self._saved_tools = self._engine.get_tools()
        self._saved_prompt = self._engine.get_system_prompt()

        from context import get_plan_mode_section
        from tools import AskUserQuestionTool, EditTool, GlobTool, GrepTool, ReadTool, WriteTool
        from tools.plan_tools import EnterPlanModeTool, ExitPlanModeTool

        # Plan Mode 只保留读代码、写计划文件、提问和退出计划的工具。
        # Edit/Write 是否能改目标文件，由 PermissionChecker 按 plan_file_path 再拦一层。
        self._engine.set_tools([
            ReadTool(),
            GlobTool(),
            GrepTool(),
            EditTool(),
            WriteTool(),
            AskUserQuestionTool(),
            EnterPlanModeTool(self),
            ExitPlanModeTool(self),
        ])
        self._engine.set_system_prompt(self._saved_prompt + "\n\n" + get_plan_mode_section(str(self._plan_file)))
        self._active = True
        return f"Entered plan mode. Plan file: {self._plan_file}"

    def exit(self) -> tuple[str, str | None]:
        assert self._engine is not None, "PlanModeManager not bound to engine"
        if not self._active:
            return "Not in plan mode.", None

        plan_content = self.get_plan_content()
        if self._saved_tools is not None:
            self._engine.set_tools(self._saved_tools)
        if self._saved_prompt is not None:
            self._engine.set_system_prompt(self._saved_prompt)

        plan_path = str(self._plan_file) if self._plan_file else "unknown"
        self._active = False
        self._saved_tools = None
        self._saved_prompt = None

        if plan_content:
            return (
                "Exited plan mode. Present this plan to the user for approval before coding.\n\n"
                f"Plan file: {plan_path}\n\n"
                f"## Plan\n{plan_content}",
                plan_content,
            )
        return f"Exited plan mode. No plan was written to {plan_path}.", None

    @staticmethod
    def _new_plan_file() -> Path:
        plans_dir = _get_plans_dir()
        for _ in range(10):
            path = plans_dir / f"{_generate_slug()}.md"
            if not path.exists():
                return path
        return plans_dir / "plan.md"
