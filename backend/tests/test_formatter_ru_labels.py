from app.telegram.formatter import TreasuryFormatter


def test_category_labels_are_russian() -> None:
    formatter = TreasuryFormatter()

    assert formatter.category_label("food") == "Еда"
    assert formatter.category_label("transport") == "Транспорт"
    assert formatter.category_label("salary") == "Зарплата"


def test_saved_message_uses_russian_category_label() -> None:
    formatter = TreasuryFormatter()

    message = formatter.format_saved("расход", "500.00", "food", "+100.00")

    assert "Еда" in message
    assert "food" not in message
