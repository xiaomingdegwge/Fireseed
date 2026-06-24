from __future__ import annotations

from dataclasses import dataclass

from engine import Engine
from session import SessionStore


@dataclass
class CommandContext:
    # 命令处理所需的运行时上下文。
    # REPL 主循环创建它，命令函数通过它操作 Engine、会话目录和当前模型。
    engine: Engine
    session_store: SessionStore
    session_dir: str
    cwd: str
    model: str


@dataclass
class CommandResult:
    # 命令执行后的返回值。当前主要用于 /resume：
    # 如果切换了会话，就把新的 SessionStore 交还给 app.py。
    handled: bool = True
    session_store: SessionStore | None = None


_COMMANDS: list[tuple[str, str]] = [
    ("help", "Show available slash commands"),
    ("sessions", "List saved sessions"),
    ("history", "Alias for /sessions"),
    ("resume <id|number>", "Resume a saved session"),
    ("clear", "Clear in-memory conversation"),
]


def parse_command(text: str) -> tuple[str, str] | None:
    """解析 slash command；普通用户输入返回 None，继续交给模型。"""
    text = text.strip()
    if not text.startswith("/"):
        return None
    name, _, args = text[1:].partition(" ")
    return name.lower(), args.strip()


def handle_command(name: str, args: str, ctx: CommandContext) -> CommandResult:
    # MAMBA2A: Slash command dispatch. REPL commands are handled here
    # before normal user input enters the model/tool loop.
    # 新增命令时优先在这里挂入口，再把具体逻辑拆到 _cmd_xxx。
    if name == "help":
        _cmd_help()
        return CommandResult()
    if name in {"sessions", "history"}:
        _cmd_sessions(ctx.session_dir)
        return CommandResult()
    if name == "resume":
        return _cmd_resume(args, ctx)
    if name == "clear":
        ctx.engine.set_messages([])
        print("[clear] conversation reset in memory (session file unchanged)")
        return CommandResult()

    print(f"[command] unknown command: /{name}")
    print("Use /help to list commands.")
    return CommandResult()


def _cmd_help() -> None:
    print("Available commands:")
    for name, description in _COMMANDS:
        print(f"  /{name:<18} {description}")


def _cmd_sessions(session_dir: str) -> None:
    sessions = SessionStore.list_sessions(session_dir)
    if not sessions:
        print("[sessions] none")
        return
    for idx, session in enumerate(sessions, start=1):
        print(f"{idx}. {session.session_id} ({session.model})")


def _cmd_resume(args: str, ctx: CommandContext) -> CommandResult:
    # /resume 支持两种定位方式：数字序号，或 session_id 前缀。
    # 找到后把历史消息装回 Engine，并把持久化目标切到旧 session。
    sessions = SessionStore.list_sessions(ctx.session_dir)
    if not sessions:
        print("[resume] no saved sessions")
        return CommandResult()
    if not args:
        _cmd_sessions(ctx.session_dir)
        print("Usage: /resume <number> or /resume <session-id-prefix>")
        return CommandResult()

    target = None
    try:
        index = int(args) - 1
        if 0 <= index < len(sessions):
            target = sessions[index]
    except ValueError:
        needle = args.lower()
        for session in sessions:
            if session.session_id.lower().startswith(needle):
                target = session
                break

    if target is None:
        print(f"[resume] session not found: {args}")
        return CommandResult()

    _meta, messages = SessionStore.load_session(target.session_id, ctx.session_dir)
    if not messages:
        print(f"[resume] session has no messages: {target.session_id}")
        return CommandResult()

    new_store = SessionStore(
        cwd=ctx.cwd,
        model=ctx.model,
        session_dir=ctx.session_dir,
        session_id=target.session_id,
    )
    ctx.engine.set_messages(messages)
    ctx.engine.set_session_store(new_store)
    print(f"[resume] loaded session {target.session_id} ({len(messages)} messages)")
    return CommandResult(session_store=new_store)
