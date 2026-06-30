from unittest.mock import patch

from plan import PlanModeManager
from tools import (
    AgentTool,
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
from worker_manager import WorkerManager


def test_read_tool_reads_file(tmp_path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("hello\nworld\n", encoding="utf-8")

    result = ReadTool().execute(file_path=str(file_path))

    assert not result.is_error
    assert "hello" in result.content


def test_read_tool_reports_missing_file() -> None:
    result = ReadTool().execute(file_path="/no/such/file.txt")

    assert result.is_error
    assert "Read error" in result.content


def test_write_tool_creates_parent_dirs(tmp_path) -> None:
    file_path = tmp_path / "nested" / "out.txt"

    result = WriteTool().execute(file_path=str(file_path), content="one\ntwo\n")

    assert not result.is_error
    assert file_path.read_text(encoding="utf-8") == "one\ntwo\n"


def test_edit_tool_replaces_unique_string(tmp_path) -> None:
    file_path = tmp_path / "code.py"
    file_path.write_text("value = 1\n", encoding="utf-8")

    result = EditTool().execute(
        file_path=str(file_path),
        old_string="value = 1",
        new_string="value = 2",
    )

    assert not result.is_error
    assert file_path.read_text(encoding="utf-8") == "value = 2\n"


def test_edit_tool_rejects_ambiguous_match(tmp_path) -> None:
    file_path = tmp_path / "code.py"
    file_path.write_text("pass\npass\n", encoding="utf-8")

    result = EditTool().execute(
        file_path=str(file_path),
        old_string="pass",
        new_string="return",
    )

    assert result.is_error
    assert "found 2 times" in result.content


def test_glob_tool_finds_files(tmp_path) -> None:
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "b.txt").write_text("", encoding="utf-8")

    result = GlobTool().execute(pattern="*.py", path=str(tmp_path))

    assert not result.is_error
    assert "a.py" in result.content
    assert "b.txt" not in result.content


def test_grep_tool_finds_matching_lines(tmp_path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("alpha\nbeta\nalphabet\n", encoding="utf-8")

    result = GrepTool().execute(pattern="alpha", file_path=str(file_path))

    assert not result.is_error
    assert "1:alpha" in result.content
    assert "3:alphabet" in result.content


def test_bash_tool_runs_command() -> None:
    result = BashTool().execute(command="printf hello")

    assert not result.is_error
    assert result.content == "hello"


def test_ask_user_question_single_select() -> None:
    tool = AskUserQuestionTool()

    with patch("tools.ask_user._select_one", return_value="Python"):
        result = tool.execute(questions=[{
            "question": "Pick a language?",
            "options": [
                {"label": "Python", "description": "Simple"},
                {"label": "Go", "description": "Fast"},
            ],
        }])

    assert not result.is_error
    assert "Pick a language? => Python" in result.content


def test_ask_user_question_multi_select() -> None:
    tool = AskUserQuestionTool()

    with patch("tools.ask_user._select_multi", return_value=["Python", "Go"]):
        result = tool.execute(questions=[{
            "question": "Pick languages?",
            "options": [
                {"label": "Python", "description": "Simple"},
                {"label": "Go", "description": "Fast"},
            ],
            "multiSelect": True,
        }])

    assert not result.is_error
    assert "Python, Go" in result.content


def test_tool_read_only_flags() -> None:
    assert AgentTool(WorkerManager(lambda: None)).is_read_only()
    assert AskUserQuestionTool().is_read_only()
    assert EnterPlanModeTool(PlanModeManager()).is_read_only()
    assert ExitPlanModeTool(PlanModeManager()).is_read_only()
    assert ReadTool().is_read_only()
    assert GlobTool().is_read_only()
    assert GrepTool().is_read_only()
    assert not EditTool().is_read_only()
    assert not WriteTool().is_read_only()
    assert not BashTool().is_read_only()
