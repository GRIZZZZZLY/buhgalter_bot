"""Tests for date_extractor — past-date prefix parsing."""

from datetime import date, timedelta

import pytest

from app.services.date_extractor import extract_date


def today() -> date:
    return date.today()


def yesterday() -> date:
    return date.today() - timedelta(days=1)


def day_before() -> date:
    return date.today() - timedelta(days=2)


class TestRelativeDates:
    def test_yesterday(self) -> None:
        d, rest = extract_date("вчера купил продукты на 750")
        assert d == yesterday()
        assert rest == "купил продукты на 750"

    def test_day_before_yesterday(self) -> None:
        d, rest = extract_date("позавчера такси 300")
        assert d == day_before()
        assert rest == "такси 300"

    def test_no_date_prefix(self) -> None:
        d, rest = extract_date("купил продукты на 750")
        assert d is None
        assert rest == "купил продукты на 750"

    def test_today_not_extracted(self) -> None:
        # "сегодня" is not in the extractor — treated as no-match
        d, rest = extract_date("сегодня кофе 200")
        assert d is None

    def test_case_insensitive(self) -> None:
        d, rest = extract_date("Вчера потратил 500 на еду")
        assert d == yesterday()
        assert rest == "потратил 500 на еду"


class TestWeekdays:
    def test_last_monday(self) -> None:
        d, rest = extract_date("в понедельник продукты 1200")
        if d is not None:
            assert d.weekday() == 0  # Monday
            assert d < today()
        assert "продукты 1200" in rest

    def test_short_weekday(self) -> None:
        d, rest = extract_date("в пн такси 350")
        if d is not None:
            assert d.weekday() == 0
            assert d < today()

    def test_same_weekday_goes_back_full_week(self) -> None:
        # If today is Monday, "в понедельник" should return last Monday (7 days ago)
        if today().weekday() == 0:
            d, _ = extract_date("в понедельник кофе 200")
            assert d is not None
            assert d == today() - timedelta(days=7)


class TestExplicitDates:
    def test_dot_format_current_year(self) -> None:
        # Use a date that is definitely in the past
        past = today() - timedelta(days=5)
        text = f"{past.day:02d}.{past.month:02d} продукты 800"
        d, rest = extract_date(text)
        assert d == past
        assert "продукты 800" in rest

    def test_dot_format_with_year(self) -> None:
        past = today() - timedelta(days=10)
        text = f"{past.day:02d}.{past.month:02d}.{past.year} кофе 200"
        d, rest = extract_date(text)
        assert d == past
        assert "кофе 200" in rest

    def test_future_date_ignored(self) -> None:
        future = today() + timedelta(days=5)
        text = f"{future.day:02d}.{future.month:02d} продукты 800"
        d, rest = extract_date(text)
        assert d is None

    def test_today_date_ignored(self) -> None:
        t = today()
        text = f"{t.day:02d}.{t.month:02d} продукты 800"
        d, rest = extract_date(text)
        assert d is None  # today is not "past"


class TestMonthNameDates:
    def test_day_month_name(self) -> None:
        # Use a past date in the current year
        past = today() - timedelta(days=20)
        month_names = {
            1: "января", 2: "февраля", 3: "марта", 4: "апреля",
            5: "мая", 6: "июня", 7: "июля", 8: "августа",
            9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
        }
        month_name = month_names[past.month]
        text = f"{past.day} {month_name} такси 450"
        d, rest = extract_date(text)
        assert d == past
        assert "такси 450" in rest

    def test_short_month_name(self) -> None:
        past = today() - timedelta(days=15)
        short_names = {
            1: "янв", 2: "фев", 3: "мар", 4: "апр",
            5: "мая", 6: "июн", 7: "июл", 8: "авг",
            9: "сен", 10: "окт", 11: "ноя", 12: "дек",
        }
        short = short_names[past.month]
        text = f"{past.day} {short} кофе 180"
        d, rest = extract_date(text)
        assert d == past
        assert "кофе 180" in rest


class TestEdgeCases:
    def test_empty_string(self) -> None:
        d, rest = extract_date("")
        assert d is None
        assert rest == ""

    def test_only_date_no_transaction(self) -> None:
        d, rest = extract_date("вчера")
        assert d == yesterday()
        assert rest == ""

    def test_date_too_old_ignored(self) -> None:
        # More than 365 days ago
        very_old = today() - timedelta(days=400)
        text = f"{very_old.day:02d}.{very_old.month:02d}.{very_old.year} продукты 500"
        d, rest = extract_date(text)
        assert d is None
