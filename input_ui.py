from __future__ import annotations

from pathlib import Path

from commands import command_specs

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings

    _HAS_PROMPT_TOOLKIT = True
except ImportError:  # pragma: no cover - depends on optional local install
    PromptSession = None  # type: ignore[assignment]
    AutoSuggestFromHistory = None  # type: ignore[assignment]
    WordCompleter = None  # type: ignore[assignment]
    FileHistory = None  # type: ignore[assignment]
    KeyBindings = None  # type: ignore[assignment]
    _HAS_PROMPT_TOOLKIT = False


_HISTORY_FILE = Path.home() / ".config" / "fireseed" / "history"


def has_prompt_toolkit() -> bool:
    return _HAS_PROMPT_TOOLKIT


def slash_command_words() -> list[str]:
    words: list[str] = []
    for spec, _description in command_specs():
        command = spec.split()[0]
        words.append(f"/{command}")
    return words

# 构建交互输入层，重写基类方法
def build_prompt_session():
    """构建交互输入层。

    这里是输入体验迁移入口：prompt_toolkit 可用时启用历史记录、
    slash command 补全和多行输入；不可用时 app.py 会回退到 input()。
    """
    if not _HAS_PROMPT_TOOLKIT:
        return None
    #历史记录持久化  ~/.config/fireseed/history
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    bindings = KeyBindings()
    #自定义按键绑定
    @bindings.add("enter")
    def _(event):
        # Fireseed 的默认体验保持 Enter 发送，避免 multiline=True 后
        # 普通回车只换行；需要换行时使用 Alt+Enter。
        event.current_buffer.validate_and_handle()

    @bindings.add("escape", "enter")
    def _(event):
        event.current_buffer.insert_text("\n")

    return PromptSession(
        history=FileHistory(str(_HISTORY_FILE)),
        completer=WordCompleter(slash_command_words(), ignore_case=True), #自动补全，对斜杠命令补全等
        auto_suggest=AutoSuggestFromHistory(), #自动建议，历史记录自动显示灰色建议文本
        complete_while_typing=True,
        key_bindings=bindings,
        multiline=True,
    )


def read_user_input(session) -> str:
    if session is None:
        return input("\n> ").strip()
    return session.prompt("\n> ").strip() # 使用 prompt_toolkit 的输入接口
