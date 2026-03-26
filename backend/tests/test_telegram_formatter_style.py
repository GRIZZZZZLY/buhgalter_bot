from app.telegram.formatter import TreasuryFormatter


def test_formatter_uses_consistent_success_verbs() -> None:
    f = TreasuryFormatter()

    assert f.format_delete_done() == "✅ Удалил запись."
    assert f.format_planned_cancelled("Маникюр").startswith("✅ Отменил")
    assert f.format_recurring_deleted("Аренда").startswith("✅ Отключил")


def test_formatter_uses_consistent_not_found_errors() -> None:
    f = TreasuryFormatter()

    assert "Не нашёл" in f.format_delete_missing()


def test_voice_edit_prompt_is_short_and_actionable() -> None:
    f = TreasuryFormatter()

    msg = f.format_voice_edit_prompt("купил кофе 200")
    assert msg.startswith("✏️ Исправь текст")
    assert "следующим сообщением" in msg
