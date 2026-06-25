from __future__ import annotations

from typing import Any

from llm import LLMClient

CHARS_PER_TOKEN = 4
COMPACT_THRESHOLD_TOKENS = 100_000
MIN_RECENT_MESSAGES = 6
MIN_RECENT_TOKENS = 10_000
COMPACT_MAX_OUTPUT_TOKENS = 2048
AUTOCOMPACT_BUFFER_TOKENS = 13_000  # token 统计不是永远精确可控的 误差值

_CONTEXT_WINDOWS: list[tuple[str, int]] = [
    ("claude-opus-4-6", 1_000_000),
    ("claude-opus-4-5", 1_000_000),
    ("claude-opus-4", 200_000),
    ("claude-sonnet-4-6", 1_000_000),
    ("claude-sonnet-4-5", 1_000_000),
    ("claude-sonnet-4", 200_000),
    ("claude-sonnet", 200_000),
    ("claude-3-7-sonnet", 200_000),
    ("claude-3-5-sonnet", 200_000),
    ("claude-haiku-4-5", 200_000),
    ("claude-3-5-haiku", 200_000),
]
_DEFAULT_CONTEXT_WINDOW = 200_000

COMPACT_SYSTEM = "You are a careful conversation summarizer."
COMPACT_PROMPT = """\
Summarize the earlier conversation so the assistant can continue later.

Preserve:
- the user's main goal
- important files, commands, and decisions
- tool results that matter
- current status and next steps

Be concise but specific.
"""


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(len(_text_of(message.get("content", ""))) for message in messages) // CHARS_PER_TOKEN

#查询此模型上下文窗口大小值
def _context_window_for_model(model: str) -> int:
    model_lower = model.lower()
    for prefix, window in _CONTEXT_WINDOWS:
        if prefix in model_lower:
            return window
    return _DEFAULT_CONTEXT_WINDOW


def _auto_compact_threshold(model: str) -> int:
    context_window = _context_window_for_model(model)
    max_output_reserve = min(20_000, context_window // 5) #给模型“本轮回答”预留的输出空间（压缩本身输出）
    return context_window - max_output_reserve - AUTOCOMPACT_BUFFER_TOKENS


def should_compact(
    messages: list[dict[str, Any]],
    model: str | None = None,
    last_input_tokens: int | None = None,
) -> bool:
    """判断是否需要自动压缩上下文。

    优先使用 API 返回的 input_tokens 做模型窗口判断；没有 usage 时，
    退回到字符估算，保证 mock 或兼容端也能触发保护。
    """
    if model and last_input_tokens:
        return last_input_tokens >= _auto_compact_threshold(model) #本轮发给模型的输入（总的） token 数”已经接近该模型的上下文窗口上限时，就触发自动 compact
    return estimate_tokens(messages) > COMPACT_THRESHOLD_TOKENS


class CompactService:
    def __init__(self, client: LLMClient, model: str, effort: str | None = None):
        self._client = client
        self._model = model
        self._effort = effort

    def compact(
        self,
        messages: list[dict[str, Any]],
        custom_instructions: str = "",
    ) -> tuple[list[dict[str, Any]], str]:
        # MAMBA2B: Compact command core. Summarize older messages, then
        # replace them with a compact summary while keeping recent context.
        history, recent = _split_recent(messages)
        if not history:
            return list(messages), "(nothing to compact)"

        prompt = COMPACT_PROMPT
        if custom_instructions:
            prompt += f"\nExtra instructions from user: {custom_instructions}\n"
         #规则方式简化数据
        compact_messages = _fix_alternation(_strip_media(history))
        compact_messages.append({"role": "user", "content": prompt})

        response = self._client.create_message(
            model=self._model,
            max_tokens=COMPACT_MAX_OUTPUT_TOKENS,
            system=COMPACT_SYSTEM,
            messages=compact_messages,
            effort=self._effort,
        )
        summary = _message_text(response.content).strip() or "(empty compact summary)"

        new_messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    "[Earlier conversation was compacted into this summary.]\n\n"
                    + summary
                ),
            },
            {
                "role": "assistant",
                "content": "Understood. I will continue from the compacted summary.",
            },
        ]
        new_messages.extend(recent)
        return new_messages, summary


def _split_recent(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(messages) <= MIN_RECENT_MESSAGES:
        return [], list(messages)

    keep_start = len(messages)
    kept_tokens = 0
    kept_messages = 0

    for index in range(len(messages) - 1, -1, -1):
        kept_tokens += len(_text_of(messages[index].get("content", ""))) // CHARS_PER_TOKEN
        kept_messages += 1
        keep_start = index
        if kept_messages >= MIN_RECENT_MESSAGES and kept_tokens >= MIN_RECENT_TOKENS:
            break

    if keep_start > 0:
        first_recent = messages[keep_start]
        content = first_recent.get("content", "")
        is_tool_results = (
            first_recent.get("role") == "user"
            and isinstance(content, list)
            and all(isinstance(block, dict) and block.get("type") == "tool_result" for block in content)
        )
        if is_tool_results:
            keep_start -= 1

    return messages[:keep_start], messages[keep_start:]


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
                parts.append(str(block.get("content", "")))
                parts.append(str(block.get("input", "")))
            else:
                parts.append(str(block))
        return " ".join(parts)
    return str(content)


def _message_text(content: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in content:
        if block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)

#"剥离媒体内容" —— 从消息中移除图片、文档等非文本的媒体元素
def _strip_media(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content", "")
        if not isinstance(content, list):
            cleaned.append(dict(message))
            continue
        blocks = [
            block for block in content
            if not (isinstance(block, dict) and block.get("type") in {"image", "document"})
        ]
        cleaned.append({**message, "content": blocks})
    return cleaned

#function：修复消息列表中 user/assistant 角色不交替的问题。
# 角色必须交替：user → assistant → user → assistant ...
# 必须以 user 开头
def _fix_alternation(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fixed: list[dict[str, Any]] = []
    last_role = None
    for message in messages:
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        if role == last_role: #当前角色和上一条相同，具体：当前是 user 就插入 assistant，当前是 assistant 就插入 user，内容为 "(continued)"
            fixed.append({"role": "assistant" if role == "user" else "user", "content": "(continued)"})
        fixed.append(message)
        last_role = role
    if fixed and fixed[0].get("role") != "user": #如果第一条有效消息不是 user（比如以 assistant 开头），则在开头插入一条 user 占位消息。
        fixed.insert(0, {"role": "user", "content": "(conversation start)"})
    return fixed
