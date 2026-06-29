from __future__ import annotations

from .base import Tool, ToolResult

_OTHER = "__other__"


def _select_one(question: str, labels: list[str], descriptions: list[str]) -> str | None:
    """Single-select terminal menu; returns label/custom text, or None when cancelled."""
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    other_idx = len(labels) - 1
    cursor = [0]
    text_buf = [""]
    result: list[str] = []
    kb = KeyBindings()

    def on_other() -> bool:
        return cursor[0] == other_idx

    @kb.add("up")
    def _up(event):
        cursor[0] = (cursor[0] - 1) % len(labels)

    @kb.add("down")
    def _down(event):
        cursor[0] = (cursor[0] + 1) % len(labels)

    @kb.add("enter")
    def _enter(event):
        if on_other():
            result.append(text_buf[0] if text_buf[0] else _OTHER)
        else:
            result.append(labels[cursor[0]])
        event.app.exit()

    @kb.add("c-c")
    def _cancel(event):
        event.app.exit()

    @kb.add("escape")
    def _esc(event):
        if on_other() and text_buf[0]:
            text_buf[0] = ""
            cursor[0] = max(other_idx - 1, 0)
        else:
            event.app.exit()

    @kb.add("backspace")
    def _backspace(event):
        if on_other():
            text_buf[0] = text_buf[0][:-1]

    @kb.add("<any>")
    def _char(event):
        ch = event.data
        if not ch or not ch.isprintable():
            return
        if on_other():
            text_buf[0] += ch
            return
        if ch.isdigit():
            idx = int(ch) - 1
            if 0 <= idx < len(labels):
                if idx == other_idx:
                    cursor[0] = other_idx
                else:
                    result.append(labels[idx])
                    event.app.exit()
            return
        cursor[0] = other_idx
        text_buf[0] += ch

    def get_tokens():
        # prompt_toolkit 的 FormattedTextControl 需要这种格式:
        # [(style, text), ...]，每一段文本可以单独指定颜色/粗体。
        tokens = [("bold", f"? {question}\n")]
        for i, (label, desc) in enumerate(zip(labels, descriptions)):
            # cursor[0] 保存当前光标所在选项；当前行会显示 > 并用青色高亮。
            is_current = i == cursor[0]
            prefix = "  > " if is_current else "    "
            style = "ansibrightcyan" if is_current else ""
            # 最后一个选项是 Other，用 text_buf[0] 保存用户输入的自定义内容。
            if i == other_idx:
                if text_buf[0]:
                    tokens.append((style, f"{prefix}{i + 1}) "))
                    tokens.append(("ansibrightgreen bold", text_buf[0]))
                    if is_current:
                        # 用一个灰色下划线模拟正在输入的光标。
                        tokens.append(("ansigray", "_"))
                elif is_current:
                    tokens.append((style, f"{prefix}{i + 1}) "))
                    tokens.append(("ansigray", "Type something."))
                else:
                    tokens.append(("ansigray", f"{prefix}{i + 1}) {label}"))
            else:
                # 普通选项显示序号、标题；有描述时在后面追加灰色说明。
                tokens.append((style, f"{prefix}{i + 1}) {label}"))
                if desc:
                    tokens.append(("ansigray", f" - {desc}"))
            tokens.append(("", "\n"))
        tokens.append(("ansigray", "  up/down navigate - enter select"))
        return tokens

    app = Application(
        layout=Layout(Window(FormattedTextControl(get_tokens))),
        key_bindings=kb,
        full_screen=False,
    )
    try:
        app.run()
    except (EOFError, KeyboardInterrupt):
        return None

    if not result or result[0] == _OTHER:
        return None
    return result[0]

#选择一个建议，支持自定义输入，上下移动箭头选择
def _select_multi(question: str, labels: list[str], descriptions: list[str]) -> list[str] | None:
    """Multi-select terminal menu; space toggles options, enter confirms."""
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    other_idx = len(labels) - 1
    cursor = [0]
    checked: set[int] = set()
    text_buf = [""]
    confirmed = [False]
    kb = KeyBindings()

    def on_other() -> bool:
        return cursor[0] == other_idx

    @kb.add("up")
    def _up(event):
        cursor[0] = (cursor[0] - 1) % len(labels)

    @kb.add("down")
    def _down(event):
        cursor[0] = (cursor[0] + 1) % len(labels)

    @kb.add("space")
    def _toggle(event):
        if on_other():
            text_buf[0] += " "
            checked.add(other_idx)
            return
        if cursor[0] in checked:
            checked.discard(cursor[0])
        else:
            checked.add(cursor[0])
    # event.app.exit()退出表示选择完成。
    @kb.add("enter")
    def _enter(event):
        confirmed[0] = True
        event.app.exit()

    @kb.add("c-c")
    def _cancel(event):
        event.app.exit()
    #注册的回调函数，用来交互选择。
    @kb.add("escape")
    def _esc(event):
        if on_other() and text_buf[0]:
            text_buf[0] = ""
            checked.discard(other_idx)
            cursor[0] = max(other_idx - 1, 0)
        else:
            event.app.exit()

    @kb.add("backspace")
    def _backspace(event):
        if on_other():
            text_buf[0] = text_buf[0][:-1]
            if not text_buf[0]:
                checked.discard(other_idx)

    @kb.add("<any>")
    def _char(event):
        ch = event.data
        if not ch or not ch.isprintable():
            return
        if on_other():
            text_buf[0] += ch
            checked.add(other_idx)
            return
        if ch.isdigit():
            idx = int(ch) - 1
            if 0 <= idx < len(labels):
                cursor[0] = idx
            return
        cursor[0] = other_idx
        text_buf[0] += ch
        checked.add(other_idx)

    def get_tokens():
        # prompt_toolkit 的 FormattedTextControl 需要这种格式:
        # [(style, text), ...]，每一段文本可以单独指定颜色/粗体。
        tokens = [("bold", f"? {question}\n")]
        for i, (label, desc) in enumerate(zip(labels, descriptions)):
            # cursor[0] 保存当前光标所在选项；checked 保存已经勾选的选项下标。
            is_current = i == cursor[0]
            mark = "x" if i in checked else " "
            prefix = "  > " if is_current else "    "
            style = "ansibrightcyan" if is_current else ""
            # 最后一个选项是 Other，用 text_buf[0] 保存用户输入的自定义内容。
            if i == other_idx:
                if text_buf[0]:
                    tokens.append((style, f"{prefix}[{mark}] {i + 1}) "))
                    tokens.append(("ansibrightgreen bold", text_buf[0]))
                    if is_current:
                        # 用一个灰色下划线模拟正在输入的光标。
                        tokens.append(("ansigray", "_"))
                elif is_current:
                    tokens.append((style, f"{prefix}[{mark}] {i + 1}) "))
                    tokens.append(("ansigray", "Type something."))
                else:
                    tokens.append(("ansigray", f"{prefix}[{mark}] {i + 1}) {label}"))
            else:
                # 普通选项显示勾选状态、序号、标题；有描述时追加灰色说明。
                tokens.append((style, f"{prefix}[{mark}] {i + 1}) {label}"))
                if desc:
                    tokens.append(("ansigray", f" - {desc}"))
            tokens.append(("", "\n"))
        tokens.append(("ansigray", "  up/down navigate - space toggle - enter submit"))
        return tokens

    app = Application(
        layout=Layout(Window(FormattedTextControl(get_tokens))),
        key_bindings=kb,
        full_screen=False,
    )
    try:
        app.run()
    except (EOFError, KeyboardInterrupt):
        return None

    if not confirmed[0]:
        return None

    answers: list[str] = []
    for i in sorted(checked):
        if i == other_idx:
            if text_buf[0]:
                answers.append(text_buf[0])
        else:
            answers.append(labels[i])
    return answers


class AskUserQuestionTool(Tool):
    name = "AskUserQuestion"
    description = (
        "Ask the user clarifying multiple-choice questions. Use this when the "
        "model needs a concrete preference or decision before continuing."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                                "required": ["label", "description"],
                            },
                            "minItems": 2,
                            "maxItems": 4,
                        },
                        "multiSelect": {"type": "boolean", "default": False},
                    },
                    "required": ["question", "options"],
                },
                "minItems": 1,
                "maxItems": 4,
            }
        },
        "required": ["questions"],
    }

    def get_activity_description(self, **kwargs) -> str | None:
        questions = kwargs.get("questions") or []
        if questions:
            return f"Asking: {questions[0].get('question', '')}"
        return "Asking user"

    def execute(self, **kwargs) -> ToolResult:
        questions = kwargs.get("questions", [])
        if not questions:
            return ToolResult(content="No questions provided.", is_error=True)

        answers: list[str] = []
        for question in questions:
            question_text = question.get("question", "")
            options = question.get("options", [])
            labels = [option["label"] for option in options] + ["Other"]
            descriptions = [option.get("description", "") for option in options] + [""]

            # AskUserQuestion 是只读工具，但会暂停工具链等待用户选择；
            # 返回内容会作为 tool_result 回填给模型，让同一轮继续执行。
            if question.get("multiSelect", False):
                selected = _select_multi(question_text, labels, descriptions)
                if selected is None:
                    return ToolResult(content="User cancelled the question.", is_error=True)
                answer = ", ".join(selected) if selected else "(no selection)"
            else:
                #交互式选择一个选项
                selected_one = _select_one(question_text, labels, descriptions)
                if selected_one is None:
                    return ToolResult(content="User cancelled the question.", is_error=True)
                answer = selected_one
            answers.append(f"{question_text} => {answer}")

        return ToolResult(content="User answered:\n" + "\n".join(answers))
