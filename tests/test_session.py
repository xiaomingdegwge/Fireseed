from session import SessionStore


def test_list_sessions_skips_meta_only_sessions(tmp_path) -> None:
    empty = SessionStore(cwd="/tmp", model="mock-sonnet", session_dir=str(tmp_path), session_id="empty")
    active = SessionStore(cwd="/tmp", model="mock-sonnet", session_dir=str(tmp_path), session_id="active")
    active.append_message({"role": "user", "content": "hello"})

    sessions = SessionStore.list_sessions(str(tmp_path))

    assert [session.session_id for session in sessions] == ["active"]
    assert empty.session_id == "empty"


def test_list_sessions_skips_blank_message_files(tmp_path) -> None:
    store = SessionStore(cwd="/tmp", model="mock-sonnet", session_dir=str(tmp_path), session_id="blank")
    (tmp_path / "blank.jsonl").write_text("\n\n", encoding="utf-8")

    assert SessionStore.list_sessions(str(tmp_path)) == []
    assert store.session_id == "blank"
