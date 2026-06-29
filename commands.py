from __future__ import annotations

from dataclasses import dataclass

from compact import CompactService, estimate_tokens
from cost_tracker import CostTracker
from engine import Engine
from sandbox import SandboxManager
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
    compact_service: CompactService | None = None
    cost_tracker: CostTracker | None = None
    sandbox_manager: SandboxManager | None = None
    sandbox_config_path: str | None = None


@dataclass
class CommandResult:
    # 命令执行后的返回值。当前主要用于 /resume：
    # 如果切换了会话，就把新的 SessionStore 交还给 app.py。
    handled: bool = True
    session_store: SessionStore | None = None
    pending_query: str | None = None


_COMMANDS: list[tuple[str, str]] = [
    ("help", "Show available slash commands"),
    ("sessions", "List saved sessions"),
    ("history", "Alias for /sessions"),
    ("resume <id|number>", "Resume a saved session"),
    ("compact [note]", "Summarize older context and keep recent messages"),
    ("cost", "Show token usage and estimated cost"),
    ("skills", "List available skills"),
    ("sandbox [deps|mode|exclude]", "Show or change sandbox settings"),
    ("clear", "Clear in-memory conversation"),
]


def command_specs() -> list[tuple[str, str]]:
    """给 help、补全等 UI 层复用的 slash command 清单。"""
    specs = list(_COMMANDS)
    try:
        from skills import list_skills

        for skill in list_skills(user_invocable_only=True):
            hint = f" <{skill.argument_hint}>" if skill.argument_hint else ""
            specs.append((f"{skill.name}{hint}", skill.description or "Run skill"))
    except Exception:
        pass
    return specs


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
    if name == "compact":
        return _cmd_compact(args, ctx)
    if name == "cost":
        return _cmd_cost(ctx)
    if name == "skills":
        return _cmd_skills()
    if name == "sandbox":
        return _cmd_sandbox(args, ctx)
    if name == "clear":
        ctx.engine.set_messages([])
        print("[clear] conversation reset in memory (session file unchanged)")
        return CommandResult()

    skill_result = _cmd_skill(name, args)
    if skill_result is not None:
        return skill_result

    print(f"[command] unknown command: /{name}")
    print("Use /help or /skills to list commands.")
    return CommandResult()


def _cmd_help() -> None:
    print("Available commands:")
    for name, description in command_specs():
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


def _cmd_compact(args: str, ctx: CommandContext) -> CommandResult:
    if ctx.compact_service is None:
        print("[compact] compact service is not configured")
        return CommandResult()

    messages = ctx.engine.get_messages()
    if len(messages) <= 6:
        print("[compact] too few messages to compact")
        return CommandResult()

    before_tokens = estimate_tokens(messages)
    before_count = len(messages)
    print(f"[compact] summarizing {before_count} messages (~{before_tokens} tokens)")

    try:
        new_messages, _summary = ctx.compact_service.compact(messages, custom_instructions=args)
    except Exception as exc:
        print(f"[compact] failed: {exc}")
        return CommandResult()

    ctx.engine.set_messages(new_messages) #压缩后的信息
    ctx.session_store.replace_messages(new_messages) #更新会话文件中的消息

    after_tokens = estimate_tokens(new_messages)
    print(
        f"[compact] done: {before_count} -> {len(new_messages)} messages, "
        f"~{before_tokens} -> ~{after_tokens} tokens"
    )
    return CommandResult()


def _cmd_cost(ctx: CommandContext) -> CommandResult:
    if ctx.cost_tracker is None:
        print("[cost] cost tracker is not configured")
        return CommandResult()
    print(ctx.cost_tracker.format_cost())
    return CommandResult()


def _cmd_skills() -> CommandResult:
    from skills import list_skills

    skills = list_skills(user_invocable_only=True)
    if not skills:
        print("[skills] none")
        return CommandResult()
    print("Available skills:")
    for skill in skills:
        hint = f" <{skill.argument_hint}>" if skill.argument_hint else ""
        print(f"  /{skill.name}{hint:<14} {skill.description} ({skill.source})")
    return CommandResult()


def _cmd_skill(name: str, args: str) -> CommandResult | None:
    from skills import get_skill

    skill = get_skill(name)
    if skill is None:
        return None
    prompt = skill.get_prompt(args)
    if not prompt:
        print(f"[skills] /{name} produced no prompt")
        return CommandResult()
    # MAMBA2D: Skill dispatch. Slash command 只负责把 skill 变成 prompt；
    # app.py 随后把 pending_query 交给 run_query，复用完整 agent/tool 主循环。
    print(f"[skills] running /{name}")
    return CommandResult(pending_query=prompt)


def _cmd_sandbox(args: str, ctx: CommandContext) -> CommandResult:
    if ctx.sandbox_manager is None:
        print("[sandbox] sandbox manager is not configured")
        return CommandResult()

    parts = args.split()
    action = parts[0] if parts else "status"
    manager = ctx.sandbox_manager

    if action in {"status", ""}:
        _print_sandbox_status(manager, ctx.sandbox_config_path)
        return CommandResult()

    if action == "deps":
        check = manager.check_dependencies()
        print("[sandbox] dependencies:", "ok" if check.ok else "failed")
        for error in check.errors:
            print(f"  error: {error}")
        for warning in check.warnings:
            print(f"  warning: {warning}")
        return CommandResult()

    if action == "mode":
        if len(parts) < 2:
            print("Usage: /sandbox mode <auto-allow|regular|disabled>")
            return CommandResult()
        print(f"[sandbox] {manager.set_mode(parts[1])}")
        _save_sandbox_config(manager, ctx.sandbox_config_path)
        return CommandResult()

    if action == "exclude":
        pattern = args.partition("exclude")[2].strip()
        if not pattern:
            print("Usage: /sandbox exclude <pattern>")
            return CommandResult()
        print(f"[sandbox] {manager.add_excluded_command(pattern)}")
        _save_sandbox_config(manager, ctx.sandbox_config_path)
        return CommandResult()

    print("Usage: /sandbox [status|deps|mode <auto-allow|regular|disabled>|exclude <pattern>]")
    return CommandResult()


def _print_sandbox_status(manager: SandboxManager, config_path: str | None) -> None:
    config = manager.config
    check = manager.check_dependencies()
    mode = "disabled"
    if config.enabled:
        mode = "auto-allow" if config.auto_allow_bash else "regular"
    print("[sandbox] status")
    print(f"  config: {config_path or '(not persisted)'}")
    print(f"  configured: {'on' if config.enabled else 'off'}")
    print(f"  effective: {'on' if manager.is_enabled() else 'off'}")
    print(f"  mode: {mode}")
    print(f"  dependencies: {'ok' if check.ok else 'failed'}")
    print(f"  network isolated: {'yes' if config.unshare_net else 'no'}")
    print(f"  allow_write: {', '.join(config.filesystem.allow_write) or '(none)'}")
    print(f"  deny_write: {', '.join(config.filesystem.deny_write) or '(none)'}")
    print(f"  deny_read: {', '.join(config.filesystem.deny_read) or '(none)'}")
    print(f"  excluded: {', '.join(config.excluded_commands) or '(none)'}")


def _save_sandbox_config(manager: SandboxManager, config_path: str | None) -> None:
    if not config_path:
        print("[sandbox] config path is not configured; change kept in memory only")
        return
    try:
        from pathlib import Path

        manager.save(Path(config_path))
        print(f"[sandbox] saved {config_path}")
    except Exception as exc:
        print(f"[sandbox] save failed: {exc}")
