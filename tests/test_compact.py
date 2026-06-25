from compact import _split_recent, estimate_tokens, should_compact


def test_should_compact_uses_model_usage_threshold() -> None:
    messages = [{"role": "user", "content": "small"}]

    assert not should_compact(
        messages,
        model="claude-sonnet-4-20250514",
        last_input_tokens=166_999,
    )
    assert should_compact(
        messages,
        model="claude-sonnet-4-20250514",
        last_input_tokens=167_000,
    )


def test_should_compact_falls_back_to_estimate() -> None:
    messages = [{"role": "user", "content": "x" * 400_004}]

    assert estimate_tokens(messages) > 100_000
    assert should_compact(messages)


def test_split_recent_keeps_tool_use_with_tool_result() -> None:
    messages = [
        {"role": "user", "content": "old" * 20_000},
        {"role": "assistant", "content": "old assistant"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "Read",
                    "input": {"file_path": "README.md"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": "read result" * 5000,
                }
            ],
        },
        {"role": "assistant", "content": "recent a" * 3000},
        {"role": "user", "content": "recent b" * 3000},
        {"role": "assistant", "content": "recent c" * 3000},
        {"role": "user", "content": "recent d" * 3000},
    ]

    history, recent = _split_recent(messages)

    assert history
    assert recent[0]["role"] == "assistant"
    assert recent[0]["content"][0]["type"] == "tool_use"
