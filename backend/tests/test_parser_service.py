from decimal import Decimal

import pytest

from app.services.parser_service import ParserService


@pytest.fixture(scope="module")
def parser() -> ParserService:
    return ParserService()


@pytest.mark.parametrize(
    ("text", "expected_type", "expected_amount", "expected_category", "expected_confidence"),
    [
        ("расход 500 еда", "expense", Decimal("500"), "food", "high"),
        ("доход 3000 аванс", "income", Decimal("3000"), "salary", "high"),
        ("500 еда", "expense", Decimal("500"), "food", "high"),
        ("1200 на транспорт", "expense", Decimal("1200"), "transport", "high"),
        ("потратил 500 на такси", "expense", Decimal("500"), "transport", "high"),
        ("еда 350", "expense", Decimal("350"), "food", "high"),
        ("+5000 зарплата", "income", Decimal("5000"), "salary", "high"),
        ("получил 3000 за заказ", "income", Decimal("3000"), "freelance", "high"),
        ("заплатил 700 на парковка", "expense", Decimal("700"), "transport", "high"),
        ("получил 12500 клиент", "income", Decimal("12500"), "freelance", "high"),
        ("кофе 199", "expense", Decimal("199"), "food", "high"),
        ("-1500 бар", "expense", Decimal("1500"), "entertainment", "high"),
        ("купил продукты в самокате на 750 рублей", "expense", Decimal("750"), "food", "high"),
        ("купил шаурму на 250", "expense", Decimal("250"), "food", "high"),
        ("заказал такси на 430 рублей", "expense", Decimal("430"), "transport", "high"),
        ("заправка на 2200", "expense", Decimal("2200"), "transport", "high"),
        ("получил зп 45000", "income", Decimal("45000"), "salary", "high"),
        ("пришло 12000 от клиента", "income", Decimal("12000"), "freelance", "high"),
        ("капнуло 5000 зарплата", "income", Decimal("5000"), "salary", "high"),
        ("вкинул в стим 900", "expense", Decimal("900"), "entertainment", "high"),
        ("заплатил за интернет 800", "expense", Decimal("800"), "telecom", "high"),
        ("заплатил за spotify 299", "expense", Decimal("299"), "subscriptions", "high"),
        ("потратила на ресницы 2300", "expense", Decimal("2300"), "beauty", "high"),
        ("купил курсы на 5000", "expense", Decimal("5000"), "education", "high"),
        ("заплатил комиссию 150", "expense", Decimal("150"), "fees", "high"),
        ("купил одежду на 3200", "expense", Decimal("3200"), "shopping", "high"),
        ("оплатил хостинг 1200", "expense", Decimal("1200"), "work", "high"),
        ("пришел кэшбек 450", "income", Decimal("450"), "bonus", "high"),
        ("вернули 900 за подписку", "income", Decimal("900"), "refund", "high"),
        # Regression: income categories without explicit verb must NOT be saved as expense
        ("зарплата 45000", "income", Decimal("45000"), "salary", "high"),
        ("45000 зарплата", "income", Decimal("45000"), "salary", "high"),
        ("зп 80000", "income", Decimal("80000"), "salary", "high"),
        ("аванс 20000", "income", Decimal("20000"), "salary", "high"),
        ("премия 5000", "income", Decimal("5000"), "bonus", "high"),
        ("кэшбек 450", "income", Decimal("450"), "bonus", "high"),
        ("фриланс 15000", "income", Decimal("15000"), "freelance", "high"),
        ("перевод 3000", "income", Decimal("3000"), "transfer", "high"),
        ("возврат 1200", "income", Decimal("1200"), "refund", "high"),
    ],
)
def test_parser_happy_path(parser: ParserService, text: str, expected_type: str, expected_amount: Decimal, expected_category: str, expected_confidence: str) -> None:
    result = parser.parse(text)
    assert result.transaction_type == expected_type
    assert result.amount == expected_amount
    assert result.category == expected_category
    assert result.confidence_label == expected_confidence


@pytest.mark.parametrize(
    "text",
    [
        "500",
        "1200.50",
        "нашел 1000",
        "   777   ",
    ],
)
def test_parser_low_confidence_when_only_amount(parser: ParserService, text: str) -> None:
    result = parser.parse(text)
    assert result.confidence_label == "low"
    assert result.amount is not None
    assert result.category is None


@pytest.mark.parametrize(
    "text",
    [
        "потратил 500 на подарки маме",
        "+2500 премия",
        "доход 7000 бонус",
        "заказ 900",
        "700 на кота",
        "купил что-то прикольное на 1300",
    ],
)
def test_parser_medium_confidence_when_category_unknown(parser: ParserService, text: str) -> None:
    result = parser.parse(text)
    assert result.confidence_label in {"medium", "high"}
    if result.confidence_label == "medium":
        assert result.category == "other"


@pytest.mark.parametrize(
    ("text", "expected_type"),
    [
        # Short patterns (P2/P5) — category-only, no verb
        ("зарплата 45000", "income"),
        ("45000 зарплата", "income"),
        ("зп 80000", "income"),
        ("аванс 20000", "income"),
        ("премия 5000", "income"),
        ("кэшбек 450", "income"),
        ("фриланс 15000", "income"),
        ("перевод 3000", "income"),
        ("возврат 1200", "income"),
        # Expense categories must still be expense
        ("еда 350", "expense"),
        ("такси 500", "expense"),
        ("аренда 30000", "expense"),
    ],
)
def test_income_category_not_saved_as_expense(parser: ParserService, text: str, expected_type: str) -> None:
    """Regression: income categories without explicit verb must resolve to 'income', not 'expense'."""
    result = parser.parse(text)
    assert result.transaction_type == expected_type, (
        f"Input '{text}': expected type '{expected_type}', got '{result.transaction_type}'"
    )


def test_parser_keeps_brand_as_description_for_known_category(parser: ParserService) -> None:
    result = parser.parse('1312 на золотое яблоко')
    assert result.confidence_label == 'medium'
    assert result.category == 'other'
    assert result.description == 'золотое яблоко'


def test_parser_keeps_store_as_description_when_category_detected(parser: ParserService) -> None:
    result = parser.parse('купил косметику в золотом яблоке на 1312')
    assert result.confidence_label == 'high'
    assert result.category == 'beauty'
    assert result.description == 'Золотое яблоко'


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "🙂🙂🙂",
        "абракадабра",
        "стикер",
        "купил",
    ],
)
def test_parser_fallback(parser: ParserService, text: str) -> None:
    result = parser.parse(text)
    assert result.confidence_label == "fallback"
    assert result.amount is None


@pytest.mark.parametrize(
    ("text", "expected_amount"),
    [
        ("потратил 21 1000 рублей", Decimal("21000")),   # "двадцать одну тысячу"
        ("потратил 5 1000 рублей", Decimal("5000")),     # "пять тысяч"
        ("потратил 100 1000 рублей", Decimal("100000")), # "сто тысяч"
        ("заплатил 3 1000 за еду", Decimal("3000")),     # "три тысячи"
        ("потратил 2 1000000 рублей", Decimal("2000000")), # "два миллиона"
    ],
)
def test_parser_stt_compound_number(parser: ParserService, text: str, expected_amount: Decimal) -> None:
    """Regression: STT (Whisper) транскрибирует устные числительные как составные числа.
    'двадцать одну тысячу' → '21 1000'. Парсер должен распознавать N 1000 как N*1000."""
    result = parser.parse(text)
    assert result.amount == expected_amount, (
        f"Input '{text}': expected {expected_amount}, got {result.amount}"
    )
