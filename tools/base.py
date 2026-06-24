from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    # 工具统一返回结构。content 会作为 tool_result 回填给模型；
    # is_error=True 时告诉模型这次工具调用失败，需要换策略。
    content: str
    is_error: bool = False


class Tool:
    # 所有工具的最小接口：名称、说明、JSON schema、只读标记和执行方法。
    # Engine 只依赖这个抽象，因此新增工具时继承 Tool 即可接入主循环。
    name: str = "Tool"
    description: str = ""
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}

    def to_api_schema(self) -> dict[str, Any]:
        # 转成模型 API 能识别的工具声明；每轮请求都会随 messages 一起发送。
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def is_read_only(self) -> bool:
        # 只读工具默认允许并发执行，也默认免权限确认。
        # Edit/Write/Bash 这类有副作用的工具需要重写为 False。
        return True

    def get_activity_description(self, **kwargs: Any) -> str | None:
        # 给终端 UI 展示的短状态文案，例如 "Editing app.py"。
        return None

    def execute(self, **kwargs: Any) -> ToolResult:
        # 子类必须实现真正的动作；Engine._execute_tool 会调用这里。
        raise NotImplementedError("Tool.execute() must be implemented by subclasses.")
