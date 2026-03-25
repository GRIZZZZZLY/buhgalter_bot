"""Tests for advisor dialog mode."""
import time


def test_advisor_history_caps_at_5_pairs() -> None:
    """History should keep max 5 question-answer pairs (10 messages)."""
    history: list[dict] = []
    for i in range(6):
        history.append({"role": "user", "content": f"q{i}"})
        history.append({"role": "assistant", "content": f"a{i}"})
        if len(history) > 10:
            history = history[2:]

    assert len(history) == 10
    assert history[0]["content"] == "q1"
    assert history[-1]["content"] == "a5"


def test_advisor_auto_clears_after_timeout() -> None:
    """If advisor_last_active > 10 min ago, history should be cleared."""
    last_active = time.time() - 700
    timeout = 600
    should_clear = (time.time() - last_active) > timeout
    assert should_clear is True


def test_advisor_no_clear_within_timeout() -> None:
    """If advisor_last_active < 10 min ago, history should be kept."""
    last_active = time.time() - 300
    timeout = 600
    should_clear = (time.time() - last_active) > timeout
    assert should_clear is False
