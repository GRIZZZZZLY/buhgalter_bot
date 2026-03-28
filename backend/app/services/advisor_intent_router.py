from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AdvisorIntent(StrEnum):
    GENERAL = "general"
    BUDGET_CHECK = "budget_check"
    CATEGORY_SPEND = "category_spend"
    TREND_ANALYSIS = "trend_analysis"
    UPCOMING = "upcoming"
    RECENT = "recent"
    ADVICE = "advice"


@dataclass(frozen=True)
class AdvisorRoute:
    intent: AdvisorIntent
    normalized_question: str


class AdvisorIntentRouter:
    _QUESTION_PREFIXES = (
        "сколько",
        "почему",
        "когда",
        "как ",
        "можно ",
        "стоит ",
        "могу ",
        "могла ",
        "хватит ",
        "достаточно ",
        "покажи ",
        "расскажи ",
    )

    def route(self, question: str) -> AdvisorRoute:
        normalized = self._normalize(question)
        lowered = normalized.lower()

        if self._matches_any(lowered, ("бюджет", "лимит", "вылез", "перерасход", "укладыва")):
            return AdvisorRoute(AdvisorIntent.BUDGET_CHECK, normalized)

        if self._matches_any(lowered, ("скоро", "платеж", "платёж", "подписк", "регуляр", "планов", "предстоит", "должен")):
            return AdvisorRoute(AdvisorIntent.UPCOMING, normalized)

        if self._matches_any(lowered, ("3 месяца", "три месяца", "динамик", "тенденц", "тренд", "сравни", "сравнение", "прошл", "месяц")):
            return AdvisorRoute(AdvisorIntent.TREND_ANALYSIS, normalized)

        if self._matches_any(lowered, ("последн", "недавн", "неделю", "сегодня", "вчера", "недавние", "операц")):
            return AdvisorRoute(AdvisorIntent.RECENT, normalized)

        if self._matches_any(lowered, ("еда", "кафе", "такси", "транспорт", "категор", "на что", "по категории")):
            return AdvisorRoute(AdvisorIntent.CATEGORY_SPEND, normalized)

        if self._matches_any(lowered, ("сократ", "эконом", "совет", "что делать", "оптимиз", "улучш", "риск")):
            return AdvisorRoute(AdvisorIntent.ADVICE, normalized)

        return AdvisorRoute(AdvisorIntent.GENERAL, normalized)

    def looks_like_advisor_question(self, text: str) -> bool:
        normalized = self._normalize(text).lower()
        if not normalized:
            return False
        if normalized.endswith("?"):
            return True
        return any(normalized.startswith(prefix) for prefix in self._QUESTION_PREFIXES)

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join((text or "").split()).strip()

    @staticmethod
    def _matches_any(text: str, needles: tuple[str, ...]) -> bool:
        return any(needle in text for needle in needles)
