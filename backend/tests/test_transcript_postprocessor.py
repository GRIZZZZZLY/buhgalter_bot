from app.services.transcript_postprocessor import TranscriptPostprocessor


def test_normalize_store_and_slang() -> None:
    processor = TranscriptPostprocessor()

    result = processor.normalize("Заказал в самокате продуктосы на 755 р.")

    assert result == "заказал в самокат продукты на 755 рублей"


def test_normalize_number_words() -> None:
    processor = TranscriptPostprocessor()

    result = processor.normalize("купил продукты на семьсот пятьдесят рублей")

    assert result == "купил продукты на 750 рублей"


def test_normalize_salary_slang() -> None:
    processor = TranscriptPostprocessor()

    result = processor.normalize("пришло зп 45000")

    assert result == "пришло зарплата 45000"


def test_normalize_digit_thousand_hybrid() -> None:
    """Whisper often outputs digit + '1000' for spoken thousands, e.g. «15 1000»."""
    processor = TranscriptPostprocessor()

    result = processor.normalize("поставьте напоминание вечером заплатить 15 1000 за тренировки")

    assert "15000" in result
    assert "1000" not in result.replace("15000", "")


def test_normalize_digit_million_hybrid() -> None:
    processor = TranscriptPostprocessor()

    result = processor.normalize("получил 3 1000000 зарплата")

    assert "3000000" in result
