from __future__ import annotations

from engine import Engine
from permissions import PermissionChecker
from plan import PlanModeManager
from tools import (
    AskUserQuestionTool,
    BashTool,
    EditTool,
    EnterPlanModeTool,
    ExitPlanModeTool,
    GlobTool,
    GrepTool,
    ReadTool,
    WriteTool,
)


def _make_engine(tmp_path):
    plan_manager = PlanModeManager()
    permissions = PermissionChecker(auto_approve=True)
    permissions.set_plan_manager(plan_manager)
    tools = [
        ReadTool(),
        EditTool(),
        WriteTool(),
        GlobTool(),
        GrepTool(),
        AskUserQuestionTool(),
        EnterPlanModeTool(plan_manager),
        ExitPlanModeTool(plan_manager),
        BashTool(cwd=str(tmp_path)),
    ]
    engine = Engine(
        tools=tools,
        system_prompt="base prompt",
        permission_checker=permissions,
        provider="mock",
    )
    plan_manager.bind_engine(engine)
    return engine, permissions, plan_manager


def test_plan_mode_enters_with_plan_file_and_limited_tools(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    engine, _permissions, plan_manager = _make_engine(tmp_path)

    message = plan_manager.enter()

    assert plan_manager.is_active
    assert "Entered plan mode" in message
    assert plan_manager.plan_file_path is not None
    assert plan_manager.plan_file_path.startswith(str(tmp_path / ".fireseed" / "plans"))
    assert "PLAN MODE IS ACTIVE" in engine.get_system_prompt()
    assert plan_manager.plan_file_path in engine.get_system_prompt()
    assert {tool.name for tool in engine.get_tools()} == {
        "Read",
        "Glob",
        "Grep",
        "Edit",
        "Write",
        "AskUserQuestion",
        "EnterPlanMode",
        "ExitPlanMode",
    }


def test_plan_mode_permissions_only_allow_plan_file_writes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _engine, permissions, plan_manager = _make_engine(tmp_path)
    plan_manager.enter()
    assert plan_manager.plan_file_path is not None

    assert permissions.check(ReadTool(), {"file_path": "README.md"}) == "allow"
    assert permissions.check(WriteTool(), {"file_path": plan_manager.plan_file_path, "content": "plan"}) == "allow"
    assert permissions.check(WriteTool(), {"file_path": str(tmp_path / "app.py"), "content": "code"}) == "deny"
    assert permissions.check(BashTool(cwd=str(tmp_path)), {"command": "pwd"}) == "deny"


def test_plan_mode_exit_restores_tools_and_prompt(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    engine, _permissions, plan_manager = _make_engine(tmp_path)
    original_tools = {tool.name for tool in engine.get_tools()}

    plan_manager.enter()
    plan_path = plan_manager.plan_file_path
    assert plan_path is not None
    WriteTool().execute(file_path=plan_path, content="1. Read files\n2. Make change\n")

    message, plan_content = plan_manager.exit()

    assert not plan_manager.is_active
    assert "Exited plan mode" in message
    assert "Read files" in (plan_content or "")
    assert engine.get_system_prompt() == "base prompt"
    assert {tool.name for tool in engine.get_tools()} == original_tools
