"""Conversational Financial Intelligence — answers user questions using real data."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from openai import APIError, OpenAI
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.services.advisor_intent_router import AdvisorIntent, AdvisorIntentRouter
from app.services.financial_analytics_service import FinancialAnalyticsService, FinancialAnalyticsSnapshot
from app.services.financial_snapshot_service import FinancialSnapshot, FinancialSnapshotService
from app.services.recommendation_service import RecommendationService, RecommendationSnapshot

logger = logging.getLogger(__name__)
_FALLBACK = "Не смог получить ответ — попробуй чуть позже."


@dataclass(frozen=True)
class AdvisorAnswerPayload:
    answer: str
    basis: list[str]
    warnings: list[str]
    confidence: str
    recommendations: list[str] = field(default_factory=list)
    snapshot: FinancialSnapshot | None = None
    analytics: FinancialAnalyticsSnapshot | None = None
    recommendation_snapshot: RecommendationSnapshot | None = None


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
        self._analytics_service = FinancialAnalyticsService()
        self._recommendation_service = RecommendationService()

    def answer(self, question: str, telegram_user_id: int, history: list[dict] | None = None) -> str:
        return self.answer_payload(question, telegram_user_id, history=history).answer

    def answer_payload(
        self,
        question: str,
        telegram_user_id: int,
        history: list[dict] | None = None,
    ) -> AdvisorAnswerPayload:
        route = self._intent_router.route(question)
        snapshot = self._snapshot_service.build(telegram_user_id)
        analytics = self._analytics_service.build(snapshot)
        recommendations = self._recommendation_service.build(snapshot, analytics)
        context = self._render_context(snapshot, analytics, route.intent)
        system = self._build_system_prompt(context, recommendations)
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
            payload = self._payload_from_llm_data(data)
            if not payload.answer:
                return self._fallback_payload(snapshot, analytics, recommendations, route.intent)
            return self._with_computed_state(payload, snapshot, analytics, recommendations)
        except APIError as exc:
            logger.error("FinancialQA LLM error: %s", exc)
            return self._fallback_payload(snapshot, analytics, recommendations, route.intent)
        except Exception as exc:
            logger.error("FinancialQA unexpected error: %s", exc)
            return self._fallback_payload(snapshot, analytics, recommendations, route.intent)

    def _with_computed_state(
        self,
        payload: AdvisorAnswerPayload,
        snapshot: FinancialSnapshot,
        analytics: FinancialAnalyticsSnapshot,
        recommendations: RecommendationSnapshot,
    ) -> AdvisorAnswerPayload:
        computed_basis = list(payload.basis)
        if recommendations.primary and recommendations.primary.detail not in computed_basis:
            computed_basis.append(recommendations.primary.detail)
        computed_warnings = list(payload.warnings)
        return AdvisorAnswerPayload(
            answer=payload.answer,
            basis=computed_basis[:3],
            warnings=computed_warnings[:3],
            confidence=payload.confidence,
            recommendations=self._render_recommendations(recommendations),
            snapshot=snapshot,
            analytics=analytics,
            recommendation_snapshot=recommendations,
        )

    def _payload_from_llm_data(self, data: dict) -> AdvisorAnswerPayload:
        answer = str(data.get("answer") or "").strip()
        basis = self._normalize_string_list(data.get("basis"))
        warnings = self._normalize_string_list(data.get("warnings"))
        confidence = str(data.get("confidence") or "medium").strip().lower() or "medium"
        if confidence not in {"low", "medium", "high"}:
            confidence = "medium"
        return AdvisorAnswerPayload(
            answer=answer,
            basis=basis[:3],
            warnings=warnings[:3],
            confidence=confidence,
        )

    @staticmethod
    def _normalize_string_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result

    def _build_context(self, telegram_user_id: int, question: str | None = None) -> str:
        route = self._intent_router.route(question or "")
        snapshot = self._snapshot_service.build(telegram_user_id)
        analytics = self._analytics_service.build(snapshot)
        return self._render_context(snapshot, analytics, route.intent)

    def _build_system_prompt(self, context: str, recommendations: RecommendationSnapshot) -> str:
        quality_note = {
            "full": "Данные достаточно полные. Можно давать конкретный вывод.",
            "partial": "Данные частичные. Будь осторожен с категоричностью.",
            "minimal": "Данных очень мало. Не делай сильных выводов.",
        }[recommendations.data_quality]
        recs_text = self._render_recommendations(recommendations) or ["Пока сильный next step не вычислен."]
        return (
            "Ты персональный финансовый ассистент конкретного пользователя. "
            "Твоя единственная задача — помогать с личными финансами: анализировать траты, "
            "давать советы по бюджету, объяснять финансовые паттерны на основе реальных данных.\n\n"
            "СТРОГОЕ ПРАВИЛО: если вопрос НЕ связан с личными финансами, бюджетом или тратами "
            "пользователя — откажи. Не пиши код, рецепты, стихи, советы по здоровью или что-либо "
            "кроме финансов. Вежливо напомни что ты финансовый помощник и предложи задать "
            "финансовый вопрос.\n\n"
            f"{quality_note}\n\n"
            "Уже вычисленные рекомендации и риски:\n"
            + "\n".join(f"- {item}" for item in recs_text[:3])
            + f"\n\nФИНАНСОВЫЕ ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:\n{context}\n\n"
            + "Верни JSON такого вида:\n"
            + '{"answer":"краткий ответ на русском","basis":["1-3 факта из данных"],"warnings":["0-3 риска или ограничения"],"confidence":"low|medium|high"}\n'
            + "Опирайся только на предоставленные данные и уже вычисленные риски. "
            + "Дай максимум один главный next step. Если данных недостаточно для ответа — скажи об этом."
        )

    def _render_context(
        self,
        snapshot: FinancialSnapshot,
        analytics: FinancialAnalyticsSnapshot,
        intent: AdvisorIntent,
    ) -> str:
        summary = snapshot.summary
        sections: list[str] = [
            f"Сегодня: {snapshot.today}",
            (
                f"Баланс этого месяца: {summary.balance:.2f}₽ "
                f"(доходы {summary.income:.2f}₽, расходы {summary.expenses:.2f}₽)"
            ),
            self._render_analytics(analytics),
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

    def _fallback_payload(
        self,
        snapshot: FinancialSnapshot,
        analytics: FinancialAnalyticsSnapshot,
        recommendations: RecommendationSnapshot,
        intent: AdvisorIntent,
    ) -> AdvisorAnswerPayload:
        if not snapshot.has_any_activity:
            return AdvisorAnswerPayload(
                answer="Пока у тебя мало финансовых данных. Сначала добавь несколько операций, и я смогу подсказать точнее.",
                basis=[],
                warnings=["Недостаточно данных для уверенного вывода."],
                confidence="low",
                recommendations=[],
                snapshot=snapshot,
                analytics=analytics,
                recommendation_snapshot=recommendations,
            )

        summary = snapshot.summary
        risk = analytics.primary_risk
        forecast = analytics.forecast
        budget_health = analytics.budget_health
        recommendation_lines = self._render_recommendations(recommendations)
        primary = recommendations.primary

        if intent == AdvisorIntent.BUDGET_CHECK and snapshot.budgets:
            risky = [item for item in snapshot.budgets if item.warning]
            if risky:
                parts = [
                    f"{item.category} — {item.percent_used}% ({item.spent_amount:.0f}/{item.limit_amount:.0f}₽)"
                    for item in risky[:3]
                ]
                warnings = ["Категории выше 90% бюджета уже близки к перерасходу."]
                if budget_health.score < 100:
                    warnings.append(f"Индекс бюджетной дисциплины сейчас {budget_health.score}/100.")
                return AdvisorAnswerPayload(
                    answer="По бюджетам уже виден риск перерасхода. Лучше сначала разобрать эти категории.",
                    basis=parts,
                    warnings=warnings[:3],
                    confidence="high",
                    recommendations=recommendation_lines,
                    snapshot=snapshot,
                    analytics=analytics,
                    recommendation_snapshot=recommendations,
                )
            return AdvisorAnswerPayload(
                answer="Пока бюджеты выглядят спокойно: критичных превышений не видно.",
                basis=[
                    f"Всего активных бюджетов: {len(snapshot.budgets)}",
                    f"Индекс бюджетной дисциплины: {budget_health.score}/100",
                ],
                warnings=[],
                confidence="medium",
                recommendations=recommendation_lines,
                snapshot=snapshot,
                analytics=analytics,
                recommendation_snapshot=recommendations,
            )

        if intent == AdvisorIntent.UPCOMING:
            basis: list[str] = []
            if snapshot.planned_expenses:
                item = snapshot.planned_expenses[0]
                basis.append(f"Ближайший плановый расход: {item.title} на {item.amount:.0f}₽ ({item.planned_date})")
            if snapshot.recurring_payments:
                item = snapshot.recurring_payments[0]
                basis.append(f"Регулярный платёж: {item.title} на {item.amount:.0f}₽/{item.frequency}")
            if basis:
                lead = basis[0].rstrip('.')
                warnings = [risk.detail] if risk and risk.title == 'upcoming_payment' else []
                return AdvisorAnswerPayload(
                    answer=f"Сейчас в фокусе ближайшие обязательные траты: {lead.lower()}.",
                    basis=basis,
                    warnings=warnings,
                    confidence="medium",
                    recommendations=recommendation_lines,
                    snapshot=snapshot,
                    analytics=analytics,
                    recommendation_snapshot=recommendations,
                )
            return AdvisorAnswerPayload(
                answer="Сейчас у меня нет данных о ближайших плановых или регулярных платежах.",
                basis=[],
                warnings=["Проверь, добавлены ли плановые и регулярные платежи."],
                confidence="low",
                recommendations=recommendation_lines,
                snapshot=snapshot,
                analytics=analytics,
                recommendation_snapshot=recommendations,
            )

        if intent == AdvisorIntent.TREND_ANALYSIS and snapshot.monthly_stats:
            current = snapshot.monthly_stats[0]
            previous = snapshot.monthly_stats[1] if len(snapshot.monthly_stats) > 1 else None
            if previous:
                delta = current.expenses - previous.expenses
                trend = "выросли" if delta > 0 else "снизились"
                warnings = [risk.detail] if risk and risk.title == "month_forecast_over_budget" else []
                return AdvisorAnswerPayload(
                    answer=(
                        f"В {current.year_month} расходы {trend} относительно предыдущего месяца. "
                        f"Если темп сохранится, месяц может закрыться около {forecast.projected_expenses:.0f}₽ расходов."
                    ),
                    basis=[
                        f"{current.year_month}: {current.expenses:.0f}₽",
                        f"{previous.year_month}: {previous.expenses:.0f}₽",
                        f"Прогноз на конец месяца: {forecast.projected_expenses:.0f}₽",
                    ],
                    warnings=warnings,
                    confidence="medium",
                    recommendations=recommendation_lines,
                    snapshot=snapshot,
                    analytics=analytics,
                    recommendation_snapshot=recommendations,
                )
            return AdvisorAnswerPayload(
                answer=f"За последний доступный месяц у тебя расходы {current.expenses:.0f}₽ и доходы {current.income:.0f}₽.",
                basis=[f"Период: {current.year_month}"],
                warnings=["Для тренда лучше иметь хотя бы два полных месяца данных."],
                confidence="low",
                recommendations=recommendation_lines,
                snapshot=snapshot,
                analytics=analytics,
                recommendation_snapshot=recommendations,
            )

        if intent == AdvisorIntent.CATEGORY_SPEND and snapshot.top_categories:
            top = snapshot.top_categories[0]
            warnings = [risk.detail] if risk and risk.title == "top_category_pressure" else []
            return AdvisorAnswerPayload(
                answer=f"Сейчас крупнейшая категория расходов — {top.category}.",
                basis=[f"За месяц: {top.amount:.0f}₽"],
                warnings=warnings,
                confidence="high",
                recommendations=recommendation_lines,
                snapshot=snapshot,
                analytics=analytics,
                recommendation_snapshot=recommendations,
            )

        if intent == AdvisorIntent.RECENT and snapshot.recent_transactions:
            recent = snapshot.recent_transactions[0]
            type_label = "доход" if recent.transaction_type == "income" else "расход"
            basis = [f"{recent.date_label}: {type_label} {recent.amount:.0f}₽, {recent.category}"]
            if recent.description:
                basis.append(f"Комментарий: {recent.description}")
            return AdvisorAnswerPayload(
                answer="Вот самая свежая операция из истории.",
                basis=basis,
                warnings=[],
                confidence="high",
                recommendations=recommendation_lines,
                snapshot=snapshot,
                analytics=analytics,
                recommendation_snapshot=recommendations,
            )

        if intent == AdvisorIntent.ADVICE:
            basis = [
                f"Прогноз расходов к концу месяца: {forecast.projected_expenses:.0f}₽",
                f"Индекс бюджетной дисциплины: {budget_health.score}/100",
            ]
            if snapshot.top_categories:
                top = snapshot.top_categories[0]
                basis.append(f"Самая тяжёлая категория сейчас — {top.category} ({top.amount:.0f}₽)")
            warnings = [risk.detail] if risk else []
            answer = "Сейчас лучший ход — смотреть на прогноз месяца и самый сильный текущий риск, а не просто на общий баланс."
            if primary:
                answer += f" Главный следующий шаг: {primary.title.lower()}."
            return AdvisorAnswerPayload(
                answer=answer,
                basis=basis[:3],
                warnings=warnings[:3],
                confidence="medium",
                recommendations=recommendation_lines,
                snapshot=snapshot,
                analytics=analytics,
                recommendation_snapshot=recommendations,
            )

        basis = [
            f"Доходы: {summary.income:.0f}₽",
            f"Расходы: {summary.expenses:.0f}₽",
            f"Прогноз расходов к концу месяца: {forecast.projected_expenses:.0f}₽",
        ]
        warnings = [risk.detail] if risk else []
        answer = (
            f"Сейчас за месяц у тебя доходы {summary.income:.0f}₽, расходы {summary.expenses:.0f}₽, баланс {summary.balance:.0f}₽. "
            f"Если темп сохранится, месяц может закрыться около {forecast.projected_expenses:.0f}₽ расходов."
        )
        if primary:
            answer += f" Главный следующий шаг: {primary.title.lower()}."
        return AdvisorAnswerPayload(
            answer=answer,
            basis=basis,
            warnings=warnings[:3],
            confidence="medium",
            recommendations=recommendation_lines,
            snapshot=snapshot,
            analytics=analytics,
            recommendation_snapshot=recommendations,
        )

    @staticmethod
    def _render_analytics(analytics: FinancialAnalyticsSnapshot) -> str:
        lines = [
            "АНАЛИТИКА:",
            (
                f"  Прогноз на конец месяца: расходы {analytics.forecast.projected_expenses:.0f}₽, "
                f"доходы {analytics.forecast.projected_income:.0f}₽"
            ),
            f"  Индекс бюджетной дисциплины: {analytics.budget_health.score}/100",
        ]
        if analytics.primary_risk:
            lines.append(f"  Главный риск: {analytics.primary_risk.detail}")
        return "\n".join(lines)

    @staticmethod
    def _render_recommendations(recommendations: RecommendationSnapshot) -> list[str]:
        lines: list[str] = []
        if recommendations.primary:
            lines.append(f"Главный шаг: {recommendations.primary.title}. {recommendations.primary.detail}")
        for item in recommendations.secondary:
            lines.append(f"Дальше: {item.title}. {item.detail}")
        return lines[:3]

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
