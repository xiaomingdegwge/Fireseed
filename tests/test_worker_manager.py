import threading
import time

from engine import Engine
from permissions import PermissionChecker
from tools import AgentTool, SendMessageTool, TaskStopTool
from worker_manager import WorkerManager


def _build_mock_worker() -> Engine:
    return Engine(
        tools=[],
        system_prompt="worker",
        permission_checker=PermissionChecker(auto_approve=True),
        provider="mock",
    )


def test_worker_manager_runs_task_and_emits_notification() -> None:
    manager = WorkerManager(_build_mock_worker)

    task = manager.spawn(description="Inspect files", prompt="hello worker")
    manager.wait_for_all(timeout=5)
    notifications = manager.drain_notifications()

    assert task.task_id == "worker-1"
    assert task.status == "completed"
    assert len(notifications) == 1
    assert "<worker_result>" in notifications[0]
    assert "<task_id>worker-1</task_id>" in notifications[0]
    assert "Mock assistant: hello worker" in notifications[0]


def test_agent_tool_starts_background_worker() -> None:
    manager = WorkerManager(_build_mock_worker)
    tool = AgentTool(manager)

    result = tool.execute(description="Check docs", prompt="summarize docs")
    manager.wait_for_all(timeout=5)

    assert not result.is_error
    assert "Started background worker worker-1" in result.content
    assert manager.drain_notifications()


def test_worker_manager_continues_completed_task() -> None:
    manager = WorkerManager(_build_mock_worker)
    task = manager.spawn(description="Inspect files", prompt="first")
    manager.wait_for_all(timeout=5)
    manager.drain_notifications()

    continued = manager.continue_task(task_id=task.task_id, message="second")
    manager.wait_for_all(timeout=5)
    notifications = manager.drain_notifications()

    assert continued is task
    assert task.status == "completed"
    assert len(notifications) == 1
    assert "Mock assistant: second" in notifications[0]


def test_send_message_tool_continues_worker() -> None:
    manager = WorkerManager(_build_mock_worker)
    task = manager.spawn(description="Check docs", prompt="first")
    manager.wait_for_all(timeout=5)
    manager.drain_notifications()
    tool = SendMessageTool(manager)

    result = tool.execute(task_id=task.task_id, message="follow up")
    manager.wait_for_all(timeout=5)

    assert not result.is_error
    assert "Sent follow-up message to worker-1" in result.content
    assert "follow up" in manager.drain_notifications()[0]


class _BlockingEngine:
    def __init__(self) -> None:
        self.aborted = threading.Event()

    def submit(self, _prompt):
        yield ("text", "started")
        while not self.aborted.is_set():
            time.sleep(0.01)
        raise RuntimeError("aborted")

    def abort(self) -> None:
        self.aborted.set()


def test_task_stop_tool_stops_running_worker() -> None:
    manager = WorkerManager(lambda: _BlockingEngine())  # type: ignore[return-value]
    task = manager.spawn(description="Long task", prompt="run")
    tool = TaskStopTool(manager)
    for _ in range(100):
        if task.status == "running":
            break
        time.sleep(0.01)

    result = tool.execute(task_id=task.task_id)
    manager.wait_for_all(timeout=5)
    notifications = manager.drain_notifications()

    assert not result.is_error
    assert task.status == "stopped"
    assert "<status>stopped</status>" in notifications[0]
