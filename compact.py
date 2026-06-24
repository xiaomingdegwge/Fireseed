from __future__ import annotations

from typing import Any

from llm import LLMClient

CHARS_PER_TOKEN = 4
MIN_RECENT_MESSAGES = 6
COMPACT_MAX_OUTPUT_TOKENS = 2048

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

    keep_start = max(0, len(messages) - MIN_RECENT_MESSAGES)
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
