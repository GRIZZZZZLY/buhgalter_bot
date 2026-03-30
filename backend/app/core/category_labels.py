"""Shared category slug → Russian label + emoji mapping."""
from __future__ import annotations

# slug -> (name_ru, emoji)
_CATEGORY_INFO: dict[str, tuple[str, str]] = {
    "food":          ("Еда",          "🍕"),
    "transport":     ("Транспорт",    "🚗"),
    "housing":       ("Жильё",        "🏠"),
    "telecom":       ("Связь",        "📱"),
    "entertainment": ("Развлечения",  "🎮"),
    "subscriptions": ("Подписки",     "📺"),
    "health":        ("Здоровье",     "💊"),
    "beauty":        ("Красота",      "💅"),
    "shopping":      ("Покупки",      "🛍"),
    "home":          ("Дом",          "🏡"),
    "work":          ("Работа",       "💼"),
    "education":     ("Обучение",     "📚"),
    "gifts":         ("Подарки",      "🎁"),
    "fees":          ("Комиссии",     "🏦"),
    "salary":        ("Зарплата",     "💰"),
    "freelance":     ("Фриланс",      "🧑‍💻"),
    "bonus":         ("Премии",       "🏆"),
    "transfer":      ("Переводы",     "↔️"),
    "refund":        ("Возвраты",     "↩️"),
    "other_income":  ("Прочий доход", "📦"),
    "other":         ("Прочее",       "📦"),
}


def cat_ru(slug: str) -> str:
    """Return Russian category name for slug, fallback to slug itself."""
    info = _CATEGORY_INFO.get(slug)
    return info[0] if info else slug


def cat_emoji(slug: str) -> str:
    """Return emoji for category slug, fallback to empty string."""
    info = _CATEGORY_INFO.get(slug)
    return info[1] if info else ""


def cat_label(slug: str) -> str:
    """Return 'emoji RuName' for category slug, e.g. '🏠 Жильё'."""
    info = _CATEGORY_INFO.get(slug)
    if info:
        return f"{info[1]} {info[0]}"
    return slug
