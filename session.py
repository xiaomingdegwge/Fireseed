from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class SessionMeta:
    session_id: str
    model: str
    cwd: str


class SessionStore:
    def __init__(self, cwd: str, model: str, session_dir: str, session_id: str | None = None):
        self._base = Path(session_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self._messages_file = self._base / f"{self.session_id}.jsonl"
        self._meta_file = self._base / f"{self.session_id}.meta.json"
        meta = SessionMeta(session_id=self.session_id, model=model, cwd=cwd)
        self._meta_file.write_text(json.dumps(meta.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_message(self, message: dict) -> None:
        line = json.dumps(message, ensure_ascii=False)
        with self._messages_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def replace_messages(self, messages: list[dict[str, Any]]) -> None:
        with self._messages_file.open("w", encoding="utf-8") as handle:
            for message in messages:
                handle.write(json.dumps(message, ensure_ascii=False) + "\n")

    @staticmethod #第2波新增功能，恢复会话功能，列出所有会话
    def list_sessions(session_dir: str) -> list[SessionMeta]:
        base = Path(session_dir)
        if not base.exists():
            return []
        sessions: list[SessionMeta] = []
        for meta_path in sorted(base.glob("*.meta.json"), reverse=True):
            # /sessions 只展示可恢复的会话。程序启动时会先写 meta；
            # 如果用户没发过消息，就不会有 jsonl，列出来会导致 /resume 空转。
            session_id = meta_path.name.removesuffix(".meta.json")
            msg_path = base / f"{session_id}.jsonl"
            if not _has_persisted_messages(msg_path):
                continue
            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            sid = str(payload.get("session_id", session_id))
            sessions.append(
                SessionMeta(
                    session_id=sid,
                    model=str(payload.get("model", "")),
                    cwd=str(payload.get("cwd", "")),
                )
            )
        return sessions

    @staticmethod
    def load_session(session_id: str, session_dir: str) -> tuple[SessionMeta | None, list[dict[str, Any]]]:
        base = Path(session_dir)
        meta_path = base / f"{session_id}.meta.json"
        msg_path = base / f"{session_id}.jsonl"

        meta: SessionMeta | None = None
        if meta_path.exists():
            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
                meta = SessionMeta(
                    session_id=str(payload.get("session_id", session_id)),
                    model=str(payload.get("model", "")),
                    cwd=str(payload.get("cwd", "")),
                )
            except Exception:
                meta = None

        messages: list[dict[str, Any]] = []
        if msg_path.exists():
            try:
                for line in msg_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    messages.append(json.loads(line))
            except Exception:
                messages = []

        return meta, messages


def _has_persisted_messages(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                return True
    except Exception:
        return False
    return False
