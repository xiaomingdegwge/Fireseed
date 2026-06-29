from permissions import PermissionChecker
from tools import BashTool, EditTool


class _FakeStdin:
    def fileno(self) -> int:
        return 123


class _FakeEscListener:
    def __init__(self):
        self.pause_calls = []
        self.resumed = False
        self.pressed = False

    def pause(self, **kwargs):
        self.pause_calls.append(kwargs)

    def resume(self):
        self.resumed = True


def test_permission_prompt_reads_single_key_yes(monkeypatch, capsys) -> None:
    checker = PermissionChecker()
    listener = _FakeEscListener()
    checker.set_esc_listener(listener)

    monkeypatch.setattr("permissions.sys.stdin", _FakeStdin())
    monkeypatch.setattr("permissions.os.isatty", lambda fd: True)
    monkeypatch.setattr("permissions.os.read", lambda fd, n: b"y")

    assert checker.check(BashTool(), {"command": "echo ok"}) == "allow"
    assert listener.pause_calls == [{"restore_terminal": False}]
    assert listener.resumed
    assert "Allow? [y]es / [n]o / [a]lways: y" in capsys.readouterr().out


def test_permission_prompt_reads_single_key_no(monkeypatch) -> None:
    checker = PermissionChecker()
    checker.set_esc_listener(_FakeEscListener())

    monkeypatch.setattr("permissions.sys.stdin", _FakeStdin())
    monkeypatch.setattr("permissions.os.isatty", lambda fd: True)
    monkeypatch.setattr("permissions.os.read", lambda fd, n: b"n")

    assert checker.check(BashTool(), {"command": "rm file"}) == "deny"


def test_permission_prompt_always_caches_current_tool(monkeypatch) -> None:
    checker = PermissionChecker()
    checker.set_esc_listener(_FakeEscListener())

    monkeypatch.setattr("permissions.sys.stdin", _FakeStdin())
    monkeypatch.setattr("permissions.os.isatty", lambda fd: True)
    monkeypatch.setattr("permissions.os.read", lambda fd, n: b"a")

    assert checker.check(EditTool(), {"file_path": "x", "old_string": "a", "new_string": "b"}) == "allow"
    assert checker.check(EditTool(), {"file_path": "x", "old_string": "b", "new_string": "c"}) == "allow"


def test_permission_prompt_esc_denies_and_marks_listener(monkeypatch) -> None:
    checker = PermissionChecker()
    listener = _FakeEscListener()
    checker.set_esc_listener(listener)

    monkeypatch.setattr("permissions.sys.stdin", _FakeStdin())
    monkeypatch.setattr("permissions.os.isatty", lambda fd: True)
    monkeypatch.setattr("permissions.os.read", lambda fd, n: b"\x1b")
    monkeypatch.setattr("permissions.select.select", lambda r, w, x, timeout: ([], [], []))

    assert checker.check(BashTool(), {"command": "echo no"}) == "deny"
    assert listener.pressed
    assert listener.resumed
