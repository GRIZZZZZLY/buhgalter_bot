"""InputGuard — rejects off-topic messages before parser/LLM."""
from __future__ import annotations

import re

_REJECTION = "Я работаю только с финансами — расходами, доходами и бюджетом."

# Patterns that indicate explicitly off-topic requests.
# Checked BEFORE financial whitelist — blacklist always wins.
# NOTE: "расскажи" and "напиши" are intentionally NOT here — they may appear
# in valid financial messages ("напиши расход на такси"). They are caught by
# the default-reject path when no financial signals are present.
_BLACKLIST: tuple[str, ...] = (
    "анекдот", "шутк", "стих", "поэм", "песн",
    "привет", "здравствуй", "добрый день", "добрый вечер",
    "как дела", "как ты",
    "погода", "новост", "политик", "спорт", "рецепт",
    "помоги с",
)

# Substrings that indicate a financial message. Any match → pass through.
_FINANCIAL_KEYWORDS: tuple[str, ...] = (
    "потратил", "купил", "заплатил", "получил",
    "доход", "расход", "зарплата", "зарплат",
    "перевёл", "перевел",
    "стоит", "рублей", "копейк",
    "бюджет", "трат", "плат", "выплат",
    "списал", "снял", "внёс", "вернул",
    "задолж", "долг", "кредит", "депозит", "налог",
)

_CURRENCY_RE = re.compile(r"[₽$€£]|\d")


class InputGuard:
    """Rejects non-financial messages before any parser or LLM call.

    check() returns the rejection message string when the text is off-topic,
    or None when the text should be processed normally.

    Logic (in order):
    1. Blacklist — explicit off-topic patterns → reject (blacklist wins over all)
    2. Whitelist — financial signals present → pass
    3. Default — no signals → reject
    """

    def check(self, text: str) -> str | None:
        t = text.lower().strip()
        if not t:
            return _REJECTION

        # 1. Blacklist: explicit off-topic wins regardless of financial signals
        if any(pattern in t for pattern in _BLACKLIST):
            return _REJECTION

        # 2. Whitelist: digits, currency symbols, or financial keywords
        if _CURRENCY_RE.search(t):
            return None
        if any(kw in t for kw in _FINANCIAL_KEYWORDS):
            return None

        # 3. Default: no financial signals found
        return _REJECTION
