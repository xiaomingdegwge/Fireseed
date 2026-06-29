from __future__ import annotations

import argparse
import html
import json
import textwrap
from pathlib import Path
from typing import Any


ROLE_LABELS = {
    "user": "User",
    "assistant": "Assistant",
    "system": "System",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="View Fireseed JSONL session files as a readable timeline."
    )
    parser.add_argument("session_file", help="Path to a .jsonl session file")
    parser.add_argument(
        "--html",
        nargs="?",
        const="",
        help="Write an HTML timeline. Optional path defaults next to the session file.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=100,
        help="Terminal wrap width for text blocks.",
    )
    parser.add_argument(
        "--max-tool-chars",
        type=int,
        default=700,
        help="Maximum tool result characters shown in terminal output.",
    )
    args = parser.parse_args()

    path = Path(args.session_file).expanduser()
    messages = load_messages(path)

    if args.html is not None:
        output = (
            Path(args.html).expanduser()
            if args.html
            else path.with_suffix(path.suffix + ".html")
        )
        write_html(output, path, messages)
        print(f"[viewer] wrote {output}")
        return

    print(render_terminal(path, messages, width=args.width, max_tool_chars=args.max_tool_chars))


def load_messages(path: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if isinstance(message, dict):
                messages.append(message)
    return messages


def render_terminal(
    path: Path, messages: list[dict[str, Any]], *, width: int, max_tool_chars: int
) -> str:
    lines = [
        f"Session: {path}",
        f"Messages: {len(messages)}",
        "",
    ]
    for index, message in enumerate(messages, start=1):
        role = ROLE_LABELS.get(str(message.get("role", "")), str(message.get("role", "")))
        lines.append(f"{index:02d}. {role}")
        for block in iter_blocks(message.get("content")):
            lines.extend(render_terminal_block(block, width=width, max_tool_chars=max_tool_chars))
        lines.append("")
    return "\n".join(lines).rstrip()


def render_terminal_block(block: dict[str, Any], *, width: int, max_tool_chars: int) -> list[str]:
    block_type = block.get("type")
    if block_type == "text":
        return indent_wrap(block.get("text", ""), width=width)
    if block_type == "tool_use":
        tool_name = block.get("name", "tool")
        tool_id = block.get("id", "")
        payload = pretty_json(block.get("input", {}))
        return [f"  -> {tool_name} {tool_id}".rstrip(), *indent_wrap(payload, width=width, prefix="     ")]
    if block_type == "tool_result":
        tool_id = block.get("tool_use_id", "")
        content = stringify_content(block.get("content", ""))
        clipped = clip(content, max_tool_chars)
        status = "error" if block.get("is_error") else "ok"
        return [
            f"  <- tool_result {tool_id} [{status}]".rstrip(),
            *indent_wrap(clipped, width=width, prefix="     "),
        ]
    return indent_wrap(stringify_content(block), width=width)


def iter_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        blocks = []
        for item in content:
            if isinstance(item, dict):
                blocks.append(item)
            else:
                blocks.append({"type": "text", "text": stringify_content(item)})
        return blocks
    return [{"type": "text", "text": stringify_content(content)}]


def write_html(output: Path, source: Path, messages: list[dict[str, Any]]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(source, messages), encoding="utf-8")


def render_html(source: Path, messages: list[dict[str, Any]]) -> str:
    items = "\n".join(
        render_html_message(index, message) for index, message in enumerate(messages, start=1)
    )
    nav_items = "\n".join(
        render_nav_item(index, message) for index, message in enumerate(messages, start=1)
    )
    tool_uses = sum(
        1
        for message in messages
        for block in iter_blocks(message.get("content"))
        if block.get("type") == "tool_use"
    )
    tool_results = sum(
        1
        for message in messages
        for block in iter_blocks(message.get("content"))
        if block.get("type") == "tool_result"
    )
    title = f"Fireseed Session - {source.name}"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --fg: #202124;
      --muted: #6b6f76;
      --line: #d8dadf;
      --user: #eaf4ff;
      --assistant: #f2f3f5;
      --tool: #fff4cf;
      --result: #e8f7ee;
      --error: #ffeceb;
      --accent: #2563eb;
      --shadow: 0 12px 30px rgb(20 24 31 / 8%);
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #171717;
        --panel: #202124;
        --fg: #eeeeee;
        --muted: #a1a1aa;
        --line: #34343a;
        --user: #11283d;
        --assistant: #242421;
        --tool: #3a2f12;
        --result: #173221;
        --error: #3b1716;
        --accent: #60a5fa;
        --shadow: 0 12px 30px rgb(0 0 0 / 25%);
      }}
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font: 14px/1.55 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 3;
      padding: 12px 18px;
      border-bottom: 1px solid var(--line);
      background: color-mix(in srgb, var(--panel) 92%, transparent);
      backdrop-filter: blur(10px);
    }}
    h1 {{ margin: 0; font-size: 16px; }}
    .meta {{ color: var(--muted); margin-top: 3px; font-size: 12px; }}
    .toolbar {{
      display: grid;
      grid-template-columns: minmax(220px, 1fr) auto auto;
      gap: 10px;
      margin-top: 10px;
      align-items: center;
    }}
    input[type="search"] {{
      width: 100%;
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 0 12px;
      background: var(--bg);
      color: var(--fg);
      font: inherit;
    }}
    .chips {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    button {{
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--panel);
      color: var(--fg);
      padding: 0 10px;
      font: inherit;
      cursor: pointer;
    }}
    button.active {{
      border-color: var(--accent);
      color: var(--accent);
      font-weight: 650;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 250px minmax(0, 1fr);
      gap: 18px;
      max-width: 1440px;
      margin: 0 auto;
      padding: 18px;
    }}
    aside {{
      position: sticky;
      top: 112px;
      align-self: start;
      max-height: calc(100vh - 132px);
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }}
    .nav-item {{
      display: grid;
      grid-template-columns: 38px minmax(0, 1fr);
      gap: 8px;
      padding: 9px 10px;
      color: var(--fg);
      text-decoration: none;
      border-bottom: 1px solid var(--line);
    }}
    .nav-item:hover {{ background: var(--bg); }}
    .nav-index {{ color: var(--muted); font-variant-numeric: tabular-nums; }}
    .nav-role {{ display: block; font-size: 12px; font-weight: 650; }}
    .nav-preview {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    main {{ min-width: 0; }}
    .message {{
      display: grid;
      grid-template-columns: 86px minmax(0, 1fr);
      gap: 16px;
      margin-bottom: 12px;
      scroll-margin-top: 128px;
    }}
    .badge {{
      position: sticky;
      top: 128px;
      align-self: start;
      color: var(--muted);
      font-size: 12px;
      text-align: right;
      padding-top: 10px;
    }}
    .role {{ display: block; color: var(--fg); font-weight: 650; }}
    .block {{
      margin: 0 0 10px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 7px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }}
    .user {{ background: var(--user); }}
    .assistant {{ background: var(--assistant); }}
    .tool-use {{ background: var(--tool); }}
    .tool-result {{ background: var(--result); }}
    .tool-error {{ background: var(--error); }}
    .label {{ color: var(--muted); font-size: 12px; margin-bottom: 6px; }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    details summary {{
      cursor: pointer;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }}
    .hidden {{ display: none !important; }}
    mark {{ background: #fde68a; color: #111827; padding: 0 2px; border-radius: 3px; }}
    @media (max-width: 920px) {{
      .toolbar {{ grid-template-columns: 1fr; }}
      .layout {{ grid-template-columns: 1fr; padding: 12px; }}
      aside {{ display: none; }}
      .message {{ grid-template-columns: 1fr; gap: 6px; }}
      .badge {{ position: static; text-align: left; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(source.name)}</h1>
    <div class="meta">{html.escape(str(source))} · {len(messages)} messages · {tool_uses} tool calls · {tool_results} tool results</div>
    <div class="toolbar">
      <input id="search" type="search" placeholder="搜索对话、工具名、文件路径或结果内容">
      <div class="chips" aria-label="role filters">
        <button type="button" class="active" data-filter="all">全部</button>
        <button type="button" data-filter="user">User</button>
        <button type="button" data-filter="assistant">Assistant</button>
        <button type="button" data-filter="tools">Tools</button>
      </div>
      <div class="chips">
        <button type="button" id="expand-all">展开结果</button>
        <button type="button" id="collapse-all">折叠结果</button>
      </div>
    </div>
  </header>
  <div class="layout">
    <aside aria-label="message index">
      {nav_items}
    </aside>
    <main>
      {items}
    </main>
  </div>
  <script>
    const search = document.querySelector('#search');
    const filterButtons = [...document.querySelectorAll('[data-filter]')];
    const messages = [...document.querySelectorAll('.message')];
    let activeFilter = 'all';

    function applyFilters() {{
      const query = search.value.trim().toLowerCase();
      for (const message of messages) {{
        const role = message.dataset.role;
        const haystack = message.dataset.search;
        const hasTools = message.dataset.tools === 'true';
        const roleMatch =
          activeFilter === 'all' ||
          role === activeFilter ||
          (activeFilter === 'tools' && hasTools);
        const textMatch = !query || haystack.includes(query);
        message.classList.toggle('hidden', !(roleMatch && textMatch));
      }}
    }}

    search.addEventListener('input', applyFilters);
    for (const button of filterButtons) {{
      button.addEventListener('click', () => {{
        activeFilter = button.dataset.filter;
        for (const item of filterButtons) item.classList.toggle('active', item === button);
        applyFilters();
      }});
    }}

    document.querySelector('#expand-all').addEventListener('click', () => {{
      document.querySelectorAll('details').forEach((item) => item.open = true);
    }});
    document.querySelector('#collapse-all').addEventListener('click', () => {{
      document.querySelectorAll('details').forEach((item) => item.open = false);
    }});
  </script>
</body>
</html>
"""


def render_nav_item(index: int, message: dict[str, Any]) -> str:
    role = str(message.get("role", ""))
    label = ROLE_LABELS.get(role, role or "Message")
    preview = clip(message_plain_text(message), 72).replace("\n", " ")
    return (
        f'<a class="nav-item" href="#m{index:02d}">'
        f'<span class="nav-index">#{index:02d}</span>'
        f"<span>"
        f'<span class="nav-role">{html.escape(label)}</span>'
        f'<span class="nav-preview">{html.escape(preview)}</span>'
        f"</span>"
        f"</a>"
    )


def render_html_message(index: int, message: dict[str, Any]) -> str:
    role = str(message.get("role", ""))
    label = ROLE_LABELS.get(role, role or "Message")
    blocks_list = iter_blocks(message.get("content"))
    blocks = "\n".join(render_html_block(block, role) for block in blocks_list)
    has_tools = any(block.get("type") in {"tool_use", "tool_result"} for block in blocks_list)
    search_text = message_plain_text(message).lower()
    return f"""<section id="m{index:02d}" class="message" data-role="{html.escape(role)}" data-tools="{str(has_tools).lower()}" data-search="{html.escape(search_text)}">
  <div class="badge"><span class="role">{html.escape(label)}</span>#{index:02d}</div>
  <div>{blocks}</div>
</section>"""


def render_html_block(block: dict[str, Any], role: str) -> str:
    block_type = block.get("type")
    if block_type == "text":
        css = "user" if role == "user" else "assistant"
        return html_block(css, "text", block.get("text", ""))
    if block_type == "tool_use":
        title = f"tool_use · {block.get('name', 'tool')} · {block.get('id', '')}".strip()
        return html_block("tool-use", title, pretty_json(block.get("input", {})))
    if block_type == "tool_result":
        status = "error" if block.get("is_error") else "ok"
        title = f"tool_result · {block.get('tool_use_id', '')} · {status}".strip()
        body = stringify_content(block.get("content", ""))
        return collapsible_html_block(
            "tool-error" if block.get("is_error") else "tool-result",
            title,
            body,
        )
    return html_block("assistant", str(block_type or "block"), stringify_content(block))


def html_block(css_class: str, label: str, text: str) -> str:
    return (
        f'<div class="block {css_class}">'
        f'<div class="label">{html.escape(label)}</div>'
        f"<pre>{html.escape(str(text))}</pre>"
        "</div>"
    )


def collapsible_html_block(css_class: str, label: str, text: str) -> str:
    preview = clip(text, 180).replace("\n", " ")
    return (
        f'<details class="block {css_class}">'
        f"<summary>{html.escape(label)} · {html.escape(preview)}</summary>"
        f"<pre>{html.escape(text)}</pre>"
        "</details>"
    )


def message_plain_text(message: dict[str, Any]) -> str:
    parts = [str(message.get("role", ""))]
    for block in iter_blocks(message.get("content")):
        block_type = str(block.get("type", ""))
        parts.append(block_type)
        if block_type == "tool_use":
            parts.append(str(block.get("name", "")))
            parts.append(str(block.get("id", "")))
            parts.append(pretty_json(block.get("input", {})))
        elif block_type == "tool_result":
            parts.append(str(block.get("tool_use_id", "")))
            parts.append(stringify_content(block.get("content", "")))
        else:
            parts.append(stringify_content(block.get("text", block)))
    return "\n".join(parts)


def indent_wrap(text: Any, *, width: int, prefix: str = "  ") -> list[str]:
    raw = stringify_content(text)
    if not raw:
        return [prefix.rstrip()]
    lines: list[str] = []
    for part in raw.splitlines() or [""]:
        wrapped = textwrap.wrap(
            part,
            width=max(20, width - len(prefix)),
            replace_whitespace=False,
            drop_whitespace=False,
        )
        if not wrapped:
            lines.append(prefix)
        else:
            lines.extend(prefix + line for line in wrapped)
    return lines


def pretty_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except TypeError:
        return stringify_content(value)


def stringify_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            else:
                parts.append(stringify_content(item))
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        return pretty_json(value)
    return "" if value is None else str(value)


def clip(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n... clipped {len(text) - limit} chars ..."


if __name__ == "__main__":
    main()
