from engine import Engine
from permissions import PermissionChecker
from tools import AgentTool
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
