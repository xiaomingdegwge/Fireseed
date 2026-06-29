import pytest

import _keylistener


class _FakeStdin:
    def fileno(self) -> int:
        return 123


class _FakeThread:
    def __init__(self, target, daemon=False):
        self.target = target
        self.daemon = daemon

    def start(self):
        pass

    def join(self, timeout=None):
        pass


@pytest.mark.skipif(not _keylistener._HAS_TERMIOS, reason="termios-only behavior")
def test_pause_for_input_restores_terminal(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(_keylistener.sys, "stdin", _FakeStdin())
    monkeypatch.setattr(_keylistener.os, "isatty", lambda fd: True)
    monkeypatch.setattr(_keylistener.threading, "Thread", _FakeThread)
    monkeypatch.setattr(_keylistener.termios, "tcgetattr", lambda fd: ["old"])
    monkeypatch.setattr(_keylistener.tty, "setcbreak", lambda fd: calls.append(("cbreak", fd)))
    monkeypatch.setattr(
        _keylistener.termios,
        "tcsetattr",
        lambda fd, when, settings: calls.append(("restore", fd, when, settings)),
    )

    listener = _keylistener.EscListener()
    with listener:
        listener.pause()
        listener.resume()

    assert calls == [
        ("cbreak", 123),
        ("restore", 123, _keylistener.termios.TCSANOW, ["old"]),
        ("cbreak", 123),
        ("restore", 123, _keylistener.termios.TCSANOW, ["old"]),
    ]


@pytest.mark.skipif(not _keylistener._HAS_TERMIOS, reason="termios-only behavior")
def test_pause_for_streaming_keeps_cbreak(monkeypatch) -> None:
    calls = []

    monkeypatch.setattr(_keylistener.sys, "stdin", _FakeStdin())
    monkeypatch.setattr(_keylistener.os, "isatty", lambda fd: True)
    monkeypatch.setattr(_keylistener.threading, "Thread", _FakeThread)
    monkeypatch.setattr(_keylistener.termios, "tcgetattr", lambda fd: ["old"])
    monkeypatch.setattr(_keylistener.tty, "setcbreak", lambda fd: calls.append(("cbreak", fd)))
    monkeypatch.setattr(
        _keylistener.termios,
        "tcsetattr",
        lambda fd, when, settings: calls.append(("restore", fd, when, settings)),
    )

    listener = _keylistener.EscListener()
    with listener:
        listener.pause(restore_terminal=False)

    assert calls == [
        ("cbreak", 123),
        ("restore", 123, _keylistener.termios.TCSANOW, ["old"]),
    ]
