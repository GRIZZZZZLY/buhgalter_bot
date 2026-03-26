"""Extract a past date prefix from user input.

Supported formats (Russian):
  вчера                → yesterday
  позавчера            → 2 days ago
  в понедельник        → last Monday (or this Monday if today is Mon)
  в пн / вт / ср …    → short weekday aliases
  10.03 / 10.03.2026   → explicit date
  10 марта / 10 мар    → day + month name
"""

from __future__ import annotations

import re
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Weekday tables
# ---------------------------------------------------------------------------
_WEEKDAY_FULL: dict[str, int] = {
    "понедельник": 0,
    "вторник": 1,
    "среду": 2,
    "среда": 2,
    "четверг": 3,
    "пятницу": 4,
    "пятница": 4,
    "субботу": 5,
    "суббота": 5,
    "воскресенье": 6,
    "воскресенье": 6,
}

_WEEKDAY_SHORT: dict[str, int] = {
    "пн": 0,
    "вт": 1,
    "ср": 2,
    "чт": 3,
    "пт": 4,
    "сб": 5,
    "вс": 6,
}

_MONTH_NAMES: dict[str, int] = {
    "января": 1, "январе": 1, "январь": 1, "янв": 1,
    "февраля": 2, "феврале": 2, "февраль": 2, "фев": 2,
    "марта": 3, "марте": 3, "март": 3, "мар": 3,
    "апреля": 4, "апреле": 4, "апрель": 4, "апр": 4,
    "мая": 5, "мае": 5, "май": 5,
    "июня": 6, "июне": 6, "июнь": 6, "июн": 6,
    "июля": 7, "июле": 7, "июль": 7, "июл": 7,
    "августа": 8, "августе": 8, "август": 8, "авг": 8,
    "сентября": 9, "сентябре": 9, "сентябрь": 9, "сен": 9,
    "октября": 10, "октябре": 10, "октябрь": 10, "окт": 10,
    "ноября": 11, "ноябре": 11, "ноябрь": 11, "ноя": 11,
    "декабря": 12, "декабре": 12, "декабрь": 12, "дек": 12,
}

# ---------------------------------------------------------------------------
# Compiled patterns (order matters — most specific first)
# ---------------------------------------------------------------------------
_PAT_YESTERDAY = re.compile(r"^вчера\s*", re.IGNORECASE)
_PAT_DAY_BEFORE = re.compile(r"^позавчера\s*", re.IGNORECASE)

# "в понедельник", "в пн"
_PAT_WEEKDAY_FULL = re.compile(
    r"^в\s+(" + "|".join(re.escape(k) for k in _WEEKDAY_FULL) + r")\s+",
    re.IGNORECASE,
)
_PAT_WEEKDAY_SHORT = re.compile(
    r"^в\s+(" + "|".join(re.escape(k) for k in _WEEKDAY_SHORT) + r")\s+",
    re.IGNORECASE,
)

# "10.03" or "10.03.2026"
_PAT_DATE_DOT = re.compile(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s*")

# "10 марта", "10 мар"
_PAT_DATE_WORD = re.compile(
    r"^(\d{1,2})\s+(" + "|".join(re.escape(k) for k in _MONTH_NAMES) + r")\s*",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_date(text: str) -> tuple[date | None, str]:
    """
    Try to extract a past-date prefix from *text*.

    Returns ``(extracted_date, remaining_text)`` where *remaining_text* has
    the date prefix stripped.  If no date is found, returns ``(None, text)``.

    Only past dates (up to 365 days ago) are accepted; future dates are
    ignored and treated as no-match.
    """
    today = date.today()
    stripped = text.strip()

    # вчера
    m = _PAT_YESTERDAY.match(stripped)
    if m:
        return today - timedelta(days=1), stripped[m.end():]

    # позавчера
    m = _PAT_DAY_BEFORE.match(stripped)
    if m:
        return today - timedelta(days=2), stripped[m.end():]

    # в понедельник / в пн
    m = _PAT_WEEKDAY_FULL.match(stripped)
    if m:
        target_wd = _WEEKDAY_FULL[m.group(1).lower()]
        d = _last_weekday(today, target_wd)
        if d and d != today:
            return d, stripped[m.end():]

    m = _PAT_WEEKDAY_SHORT.match(stripped)
    if m:
        target_wd = _WEEKDAY_SHORT[m.group(1).lower()]
        d = _last_weekday(today, target_wd)
        if d and d != today:
            return d, stripped[m.end():]

    # 10.03 / 10.03.2026
    m = _PAT_DATE_DOT.match(stripped)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        d = _safe_date(year, month, day)
        if d and _is_valid_past(d, today):
            return d, stripped[m.end():]

    # 10 марта
    m = _PAT_DATE_WORD.match(stripped)
    if m:
        day = int(m.group(1))
        month = _MONTH_NAMES[m.group(2).lower()]
        d = _safe_date(today.year, month, day)
        if d is None or d > today:
            # Try previous year
            d = _safe_date(today.year - 1, month, day)
        if d and _is_valid_past(d, today):
            return d, stripped[m.end():]

    return None, text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _last_weekday(today: date, target_wd: int) -> date | None:
    """Return the most recent date with the given weekday (≤ today)."""
    days_back = (today.weekday() - target_wd) % 7
    if days_back == 0:
        days_back = 7  # same weekday → go back a full week
    candidate = today - timedelta(days=days_back)
    return candidate if _is_valid_past(candidate, today) else None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _is_valid_past(d: date, today: date) -> bool:
    return d < today and (today - d).days <= 365
