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
