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


class SendMessageTool(Tool):
    name = "SendMessage"
    description = (
        "Send a follow-up message to an existing idle background worker. Use this "
        "after a worker has finished if more focused investigation is needed."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "Worker task id, such as worker-1.",
            },
            "message": {
                "type": "string",
                "description": "Follow-up instruction for the worker.",
            },
        },
        "required": ["task_id", "message"],
    }

    def __init__(self, worker_manager) -> None:
        """保存 worker 管理器，后续工具调用时通过它继续已有 worker。"""
        self._worker_manager = worker_manager

    def get_activity_description(self, **kwargs) -> str | None:
        """返回终端 spinner 展示的短活动说明。"""
        task_id = str(kwargs.get("task_id", "")).strip()
        return f"Sending message to {task_id}" if task_id else "Sending worker message"

    def execute(self, **kwargs) -> ToolResult:
        """向已空闲的 worker 追加一轮消息，并返回派发结果。"""
        # SUBAGENT9A: 主模型调用 SendMessage，继续一个已有 worker 的上下文。
        task_id = str(kwargs.get("task_id", "")).strip()
        message = str(kwargs.get("message", "")).strip()
        if not task_id or not message:
            return ToolResult(content="Missing task_id or message.", is_error=True)
        task = self._worker_manager.continue_task(task_id=task_id, message=message)
        if task is None:
            return ToolResult(
                content=f"Worker {task_id} is not available or is currently running.",
                is_error=True,
            )
        return ToolResult(
            content=(
                f"Sent follow-up message to {task.task_id}: {task.description}\n"
                "The worker will send another <worker_result> notification when finished."
            )
        )


class TaskStopTool(Tool):
    name = "TaskStop"
    description = "Request cancellation of a running background worker task."
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "Worker task id, such as worker-1.",
            },
        },
        "required": ["task_id"],
    }

    def __init__(self, worker_manager) -> None:
        """保存 worker 管理器，后续工具调用时通过它停止运行中的 worker。"""
        self._worker_manager = worker_manager

    def get_activity_description(self, **kwargs) -> str | None:
        """返回终端 spinner 展示的短活动说明。"""
        task_id = str(kwargs.get("task_id", "")).strip()
        return f"Stopping {task_id}" if task_id else "Stopping worker"

    def execute(self, **kwargs) -> ToolResult:
        """请求停止正在运行的 worker，并返回是否成功发出停止请求。"""
        # SUBAGENT10A: 主模型调用 TaskStop，向 worker Engine 发出 abort 请求。
        task_id = str(kwargs.get("task_id", "")).strip()
        if not task_id:
            return ToolResult(content="Missing task_id.", is_error=True)
        if not self._worker_manager.stop_task(task_id):
            return ToolResult(
                content=f"Worker {task_id} is not running or does not exist.",
                is_error=True,
            )
        return ToolResult(content=f"Requested stop for worker {task_id}.")
