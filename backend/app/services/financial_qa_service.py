"""Conversational Financial Intelligence — answers user questions using real data."""
from __future__ import annotations

import json
import logging
from decimal import Decimal

from openai import APIError, OpenAI
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.services.advisor_intent_router import AdvisorIntent, AdvisorIntentRouter
from app.services.financial_snapshot_service import FinancialSnapshot, FinancialSnapshotService

logger = logging.getLogger(__name__)

_FALLBACK = "Не смог получить ответ — попробуй чуть позже."


class FinancialQAService:
    def __init__(self, db: Session) -> None:
        self.db = db
        settings = get_settings()
        self._client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.groq_api_key,
            timeout=60.0,
        )
        self._model = settings.llm_model
        self._intent_router = AdvisorIntentRouter()
        self._snapshot_service = FinancialSnapshotService(db)

    def answer(self, question: str, telegram_user_id: int, history: list[dict] | None = None) -> str:
        """Answer a financial question using the user's real transaction data."""
        route = self._intent_router.route(question)
        snapshot = self._snapshot_service.build(telegram_user_id)
        context = self._build_context(telegram_user_id, route.normalized_question)
        system = self._build_system_prompt(context)
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": route.normalized_question})
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            raw = response.choices[0].message.content or ""
            data = json.loads(raw)
            answer = (data.get("answer") or "").strip()
            return answer or self._fallback_answer(snapshot, route.intent)
        except APIError as exc:
            logger.error("FinancialQA LLM error: %s", exc)
            return self._fallback_answer(snapshot, route.intent)
        except Exception as exc:
            logger.error("FinancialQA unexpected error: %s", exc)
            return self._fallback_answer(snapshot, route.intent)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_context(self, telegram_user_id: int, question: str | None = None) -> str:
        route = self._intent_router.route(question or "")
        snapshot = self._snapshot_service.build(telegram_user_id)
        return self._render_context(snapshot, route.intent)

    def _render_context(self, snapshot: FinancialSnapshot, intent: AdvisorIntent) -> str:
        summary = snapshot.summary
        sections: list[str] = [
            f"Сегодня: {snapshot.today}",
            (
                f"Баланс этого месяца: {summary.balance:.2f}₽ "
                f"(доходы {summary.income:.2f}₽, расходы {summary.expenses:.2f}₽)"
            ),
        ]

        always_recent = intent in {AdvisorIntent.RECENT, AdvisorIntent.ADVICE, AdvisorIntent.GENERAL}
        always_categories = intent in {
            AdvisorIntent.CATEGORY_SPEND,
            AdvisorIntent.BUDGET_CHECK,
            AdvisorIntent.ADVICE,
            AdvisorIntent.GENERAL,
        }

        if always_categories or snapshot.top_categories:
            sections.append("\nРасходы по категориям:\n" + self._render_categories(snapshot))

        if always_recent or snapshot.recent_transactions:
            sections.append("\nПоследние транзакции:\n" + self._render_recent(snapshot))

        if intent in {AdvisorIntent.TREND_ANALYSIS, AdvisorIntent.ADVICE, AdvisorIntent.GENERAL} and snapshot.monthly_stats:
            sections.append("\nПОМЕСЯЧНАЯ СТАТИСТИКА:\n" + self._render_monthly(snapshot))

        if intent in {AdvisorIntent.BUDGET_CHECK, AdvisorIntent.ADVICE, AdvisorIntent.GENERAL} and snapshot.budgets:
            sections.append("\nБЮДЖЕТЫ:\n" + self._render_budgets(snapshot))

        if intent in {AdvisorIntent.UPCOMING, AdvisorIntent.ADVICE, AdvisorIntent.GENERAL} and snapshot.planned_expenses:
            sections.append("\nПЛАНОВЫЕ РАСХОДЫ:\n" + self._render_planned(snapshot))

        if intent in {AdvisorIntent.UPCOMING, AdvisorIntent.ADVICE, AdvisorIntent.GENERAL} and snapshot.recurring_payments:
            sections.append("\nРЕГУЛЯРНЫЕ ПЛАТЕЖИ:\n" + self._render_recurring(snapshot))

        return "\n".join(sections)

    @staticmethod
    def _build_system_prompt(context: str) -> str:
        return (
            "Ты персональный финансовый ассистент конкретного пользователя. "
            "Твоя единственная задача — помогать с личными финансами: анализировать траты, "
            "давать советы по бюджету, объяснять финансовые паттерны на основе реальных данных.\n\n"
            "СТРОГОЕ ПРАВИЛО: если вопрос НЕ связан с личными финансами, бюджетом или тратами "
            "пользователя — откажи. Не пиши код, рецепты, стихи, советы по здоровью или что-либо "
            "кроме финансов. Вежливо напомни что ты финансовый помощник и предложи задать "
            "финансовый вопрос.\n\n"
            f"ФИНАНСОВЫЕ ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:\n{context}\n\n"
            'Верни JSON: {"answer": "ответ на русском"}\n'
            "Опирайся только на предоставленные данные. "
            "Если данных недостаточно для ответа — скажи об этом."
        )

    def _fallback_answer(self, snapshot: FinancialSnapshot, intent: AdvisorIntent) -> str:
        if not snapshot.has_any_activity:
            return "Пока у тебя мало финансовых данных. Сначала добавь несколько операций, и я смогу подсказать точнее."

        summary = snapshot.summary

        if intent == AdvisorIntent.BUDGET_CHECK and snapshot.budgets:
            risky = [item for item in snapshot.budgets if item.warning]
            if risky:
                parts = ", ".join(
                    f"{item.category} — {item.percent_used}% ({item.spent_amount:.0f}/{item.limit_amount:.0f}₽)"
                    for item in risky[:3]
                )
                return f"По бюджетам уже есть риск перерасхода: {parts}. Если хочешь, могу отдельно разобрать, где урезать траты."
            return "Пока бюджеты выглядят спокойно: критичных превышений не видно."

        if intent == AdvisorIntent.UPCOMING:
            upcoming_parts: list[str] = []
            if snapshot.planned_expenses:
                item = snapshot.planned_expenses[0]
                upcoming_parts.append(f"ближайший плановый расход — {item.title} на {item.amount:.0f}₽ ({item.planned_date})")
            if snapshot.recurring_payments:
                item = snapshot.recurring_payments[0]
                upcoming_parts.append(f"из регулярных платежей активен {item.title} на {item.amount:.0f}₽/{item.frequency}")
            if upcoming_parts:
                return "Сейчас по ближайшим обязательствам вижу: " + "; ".join(upcoming_parts) + "."
            return "Сейчас у меня нет данных о ближайших плановых или регулярных платежах."

        if intent == AdvisorIntent.TREND_ANALYSIS and snapshot.monthly_stats:
            current = snapshot.monthly_stats[0]
            previous = snapshot.monthly_stats[1] if len(snapshot.monthly_stats) > 1 else None
            if previous:
                delta = current.expenses - previous.expenses
                trend = "выросли" if delta > 0 else "снизились"
                return (
                    f"В {current.year_month} расходы {trend}: {current.expenses:.0f}₽ против {previous.expenses:.0f}₽ "
                    f"в {previous.year_month}."
                )
            return f"За последний доступный месяц у тебя расходы {current.expenses:.0f}₽ и доходы {current.income:.0f}₽."

        if intent == AdvisorIntent.CATEGORY_SPEND and snapshot.top_categories:
            top = snapshot.top_categories[0]
            return f"Сейчас крупнейшая категория расходов — {top.category}: {top.amount:.0f}₽ за месяц."

        if intent == AdvisorIntent.RECENT and snapshot.recent_transactions:
            recent = snapshot.recent_transactions[0]
            type_label = "доход" if recent.transaction_type == "income" else "расход"
            answer = f"Последняя операция: {recent.date_label}, {type_label} {recent.amount:.0f}₽ в категории {recent.category}."
            if recent.description:
                answer += f" Комментарий: {recent.description}."
            return answer

        if intent == AdvisorIntent.ADVICE:
            advice_bits: list[str] = []
            if snapshot.top_categories:
                top = snapshot.top_categories[0]
                advice_bits.append(f"самая тяжёлая категория сейчас — {top.category} ({top.amount:.0f}₽)")
            risky = [item for item in snapshot.budgets if item.warning]
            if risky:
                advice_bits.append(f"по бюджету уже горит {risky[0].category} ({risky[0].percent_used}%)")
            if advice_bits:
                return "Сейчас главный сигнал такой: " + "; ".join(advice_bits) + ". С этого и стоит начинать оптимизацию."

        return (
            f"Сейчас за месяц у тебя доходы {summary.income:.0f}₽, расходы {summary.expenses:.0f}₽, "
            f"баланс {summary.balance:.0f}₽. Если хочешь, могу отдельно разобрать бюджеты, категории или ближайшие платежи."
        )

    @staticmethod
    def _render_categories(snapshot: FinancialSnapshot) -> str:
        return "\n".join(
            f"  {item.category}: {item.amount:.2f}₽" for item in snapshot.top_categories
        ) or "  нет расходов"

    @staticmethod
    def _render_recent(snapshot: FinancialSnapshot) -> str:
        return "\n".join(
            (
                f"  {item.date_label} {item.transaction_type} {item.amount}₽ [{item.category}]"
                + (f" — {item.description}" if item.description else "")
            )
            for item in snapshot.recent_transactions
        ) or "  нет транзакций"

    @staticmethod
    def _render_monthly(snapshot: FinancialSnapshot) -> str:
        lines: list[str] = []
        for item in snapshot.monthly_stats:
            cat_str = ", ".join(
                f"{category}: {amount:.0f}₽" for category, amount in item.by_category.items()
            )
            lines.append(
                f"  {item.year_month}: доходы {item.income:.0f}₽, расходы {item.expenses:.0f}₽"
                + (f"\n    {cat_str}" if cat_str else "")
            )
        return "\n".join(lines)

    @staticmethod
    def _render_budgets(snapshot: FinancialSnapshot) -> str:
        return "\n".join(
            (
                f"  {item.category}: {item.limit_amount:.0f}₽/мес, потрачено {item.spent_amount:.0f}₽ "
                f"({item.percent_used}%)" + (" ⚠️" if item.warning else "")
            )
            for item in snapshot.budgets
        )

    @staticmethod
    def _render_planned(snapshot: FinancialSnapshot) -> str:
        return "\n".join(
            f"  {item.title}: {item.amount:.0f}₽, {item.planned_date}" for item in snapshot.planned_expenses
        )

    @staticmethod
    def _render_recurring(snapshot: FinancialSnapshot) -> str:
        return "\n".join(
            f"  {item.title}: {item.amount:.0f}₽/{item.frequency} ({item.transaction_type})"
            for item in snapshot.recurring_payments
        )
