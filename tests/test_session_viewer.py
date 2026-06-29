import json

from session_viewer import load_messages, render_html, render_terminal


def test_session_viewer_renders_text_and_tools(tmp_path) -> None:
    session_file = tmp_path / "demo.jsonl"
    messages = [
        {"role": "user", "content": "hello"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "checking"},
                {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "Read",
                    "input": {"file_path": "README.md"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tool-1",
                    "content": "long result",
                    "is_error": False,
                }
            ],
        },
    ]
    session_file.write_text(
        "\n".join(json.dumps(message) for message in messages),
        encoding="utf-8",
    )

    loaded = load_messages(session_file)
    terminal = render_terminal(session_file, loaded, width=80, max_tool_chars=20)
    page = render_html(session_file, loaded)

    assert len(loaded) == 3
    assert "-> Read tool-1" in terminal
    assert "<- tool_result tool-1 [ok]" in terminal
    assert "tool_use" in page
    assert "tool_result" in page
