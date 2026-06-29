from __future__ import annotations

from tools.base import Tool, ToolResult


class EnterPlanModeTool(Tool):
    name = "EnterPlanMode"
    description = (
        "Enter plan mode before non-trivial implementation. In plan mode, explore "
        "with read-only tools, write the implementation plan to the plan file, ask "
        "clarifying questions if needed, then use ExitPlanMode."
    )
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, plan_manager) -> None:
        self._plan_manager = plan_manager

    def get_activity_description(self, **kwargs) -> str | None:
        return "Entering plan mode"

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(content=self._plan_manager.enter())


class ExitPlanModeTool(Tool):
    name = "ExitPlanMode"
    description = (
        "Exit plan mode after the plan has been written to the plan file. This "
        "restores normal tools and returns the saved plan content."
    )
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, plan_manager) -> None:
        self._plan_manager = plan_manager

    def get_activity_description(self, **kwargs) -> str | None:
        return "Exiting plan mode"

    def execute(self, **kwargs) -> ToolResult:
        message, _plan_content = self._plan_manager.exit()
        return ToolResult(content=message)
