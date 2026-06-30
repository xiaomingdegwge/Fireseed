from __future__ import annotations

from tools.base import Tool, ToolResult


class AgentTool(Tool):
    name = "Agent"
    description = (
        "Start a read-only background worker for codebase exploration or research. "
        "Use this when independent investigation can run in parallel. The worker "
        "will report back to the main conversation when it finishes."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Short label for the worker task.",
            },
            "prompt": {
                "type": "string",
                "description": "Detailed instructions for the worker.",
            },
        },
        "required": ["description", "prompt"],
    }

    def __init__(self, worker_manager) -> None:
        """保存 worker 管理器，后续工具调用时通过它派发后台任务。"""
        self._worker_manager = worker_manager

    def get_activity_description(self, **kwargs) -> str | None:
        """返回终端 spinner 展示的短活动说明。"""
        description = str(kwargs.get("description", "")).strip()
        return f"Starting worker: {description}" if description else "Starting worker"

    def execute(self, **kwargs) -> ToolResult:
        """启动一个只读后台 worker，并返回任务已派发的工具结果。"""
        # SUBAGENT2: 主模型调用 Agent 工具，这里解析参数并派发后台 worker。
        description = str(kwargs.get("description", "")).strip()
        prompt = str(kwargs.get("prompt", "")).strip()
        if not prompt:
            return ToolResult(content="Missing prompt for worker task.", is_error=True)
        # Agent 工具只负责“派发任务”，不在这里等待结果。
        # 等 worker 完成后，WorkerManager 会生成通知，由 app.py 回灌给主模型。
        task = self._worker_manager.spawn(description=description, prompt=prompt)
        #工具返回结果，以user身份，投喂LLM，提示后台worker已启动，后续会有通知回灌
        return ToolResult(
            content=(
                f"Started background worker {task.task_id}: {task.description}\n"
                "The worker will send a <worker_result> notification when finished."
            )
        )
