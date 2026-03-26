from datetime import date, timedelta

from app.services.planned_expense_service import parse_plan_args


def test_parse_plan_args_parses_dd_mm_format() -> None:
    result = parse_plan_args(["маникюр", "2100", "15.04", "красота"])

    assert isinstance(result, dict)
    assert result["title"] == "маникюр"
    assert result["amount"] == 2100.0
    assert result["category"] == "красота"
    assert result["planned_date"].month == 4
    assert result["planned_date"].day == 15


def test_parse_plan_args_parses_iso_date() -> None:
    result = parse_plan_args(["маникюр", "2100", "2030-04-15", "красота"])

    assert isinstance(result, dict)
    assert result["planned_date"].isoformat() == "2030-04-15"


def test_parse_plan_args_rejects_past_date() -> None:
    yesterday = (date.today() - timedelta(days=1)).strftime("%d.%m")
    result = parse_plan_args(["маникюр", "2100", yesterday, "красота"])

    assert isinstance(result, str)
    assert "Дата уже прошла" in result


def test_parse_plan_args_rejects_bad_amount() -> None:
    result = parse_plan_args(["маникюр", "abc", "15.04", "красота"])

    assert isinstance(result, str)
    assert "Не понял сумму" in result


def test_parse_plan_args_parses_tomorrow() -> None:
    result = parse_plan_args(["маникюр", "2100", "завтра", "красота"])

    assert isinstance(result, dict)
    assert result["planned_date"] == date.today() + timedelta(days=1)


def test_parse_plan_args_parses_in_n_days() -> None:
    result = parse_plan_args(["маникюр", "2100", "через", "10", "дней", "красота"])

    assert isinstance(result, dict)
    assert result["planned_date"] == date.today() + timedelta(days=10)


def test_parse_plan_args_parses_next_weekday() -> None:
    result = parse_plan_args(["маникюр", "2100", "в", "следующий", "вторник", "красота"])

    assert isinstance(result, dict)
    assert result["planned_date"] > date.today()
    assert result["planned_date"].weekday() == 1  # Tuesday


def test_parse_plan_args_parses_day_month_words() -> None:
    # future-friendly deterministic date
    result = parse_plan_args(["маникюр", "2100", "1", "мая", "красота"])

    assert isinstance(result, dict)
    assert result["planned_date"].day == 1
    assert result["planned_date"].month == 5
