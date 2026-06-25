from cost_tracker import CostTracker


def test_cost_tracker_records_last_input_tokens() -> None:
    tracker = CostTracker()

    tracker.add_usage(
        "claude-sonnet-4-20250514",
        {"input_tokens": 123, "output_tokens": 45},
    )

    assert tracker.last_input_tokens == 123
    assert tracker.total_cost_usd > 0


def test_cost_tracker_formats_empty_state() -> None:
    tracker = CostTracker()

    assert tracker.format_cost() == "No API usage recorded."


def test_cost_tracker_tracks_cache_tokens() -> None:
    tracker = CostTracker()

    tracker.add_usage(
        "claude-sonnet-4-20250514",
        {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_read_input_tokens": 300,
            "cache_creation_input_tokens": 400,
        },
    )

    output = tracker.format_cost()
    assert "1k input" in output
    assert "200 output" in output
    assert "300 cache read" in output
    assert "400 cache write" in output
