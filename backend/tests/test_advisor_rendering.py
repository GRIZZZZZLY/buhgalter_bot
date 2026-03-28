from app.telegram.runtime import _format_advisor_payload


def test_format_advisor_payload_with_sections() -> None:
    text = _format_advisor_payload(
        "Главный вывод",
        basis=["Факт 1", "Факт 2"],
        warnings=["Риск 1"],
        confidence="high",
        recommendations=["Шаг 1"],
    )

    assert "Главный вывод" in text
    assert "Следующий ход:" in text
    assert "• Шаг 1" in text
    assert "Основа:" in text
    assert "• Факт 1" in text
    assert "Риски / ограничения:" in text
    assert "• Риск 1" in text
    assert "Уверенность: высокая" in text
