"""Conversational Financial Intelligence — answers user questions using real data."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from openai import APIError, OpenAI
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.repositories.category_budget_repository import CategoryBudgetRepository
from app.repositories.planned_expense_repository import PlannedExpenseRepository
from app.repositories.recurring_transaction_repository import RecurringTransactionRepository
from app.repositories.transaction_repository import TransactionRepository

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

    def answer(self, question: str, telegram_user_id: int, history: list[dict] | None = None) -> str:
        """Answer a financial question using the user's real transaction data."""
        context = self._build_context(telegram_user_id)
        system = self._build_system_prompt(context)
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": question})
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            raw = response.choices[0].message.content or ""
            data = json.loads(raw)
            return (data.get("answer") or "").strip() or _FALLBACK
        except APIError as exc:
            logger.error("FinancialQA LLM error: %s", exc)
            return _FALLBACK
        except Exception as exc:
            logger.error("FinancialQA unexpected error: %s", exc)
            return _FALLBACK

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_context(self, telegram_user_id: int) -> str:
        repo = TransactionRepository(self.db)
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        summary = repo.get_summary(telegram_user_id, period="month")
        income = summary.get("income_total", 0)
        expenses = summary.get("expense_total", 0)
        balance = summary.get("balance", 0)

        by_category: dict = repo.sum_expenses_by_category(telegram_user_id, start=month_start, end=now)
        cat_lines = "\n".join(
            f"  {cat}: {total:.2f}₽"
            for cat, total in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)[:10]
        ) or "  нет расходов"

        recent = repo.list_for_user(telegram_user_id, limit=20, offset=0, period="month")
        recent_lines = "\n".join(
            f"  {tx.created_at.strftime('%d.%m')} {tx.type.value} {tx.amount}₽ [{tx.category}]"
            + (f" — {tx.description}" if tx.description else "")
            for tx in recent
        ) or "  нет транзакций"

        sections = [
            f"Сегодня: {today}",
            f"Баланс этого месяца: {balance:.2f}₽ "
            f"(доходы {income:.2f}₽, расходы {expenses:.2f}₽)",
            f"\nРасходы по категориям:\n{cat_lines}",
            f"\nПоследние транзакции:\n{recent_lines}",
        ]

        # Monthly stats (3 months)
        monthly = repo.monthly_summary(telegram_user_id, months=3)
        if monthly:
            monthly_lines = []
            for m in monthly:
                cat_str = ", ".join(
                    f"{cat}: {amt:.0f}₽"
                    for cat, amt in m["by_category"].items()
                )
                monthly_lines.append(
                    f"  {m['year_month']}: доходы {m['income']:.0f}₽, расходы {m['expenses']:.0f}₽"
                    + (f"\n    {cat_str}" if cat_str else "")
                )
            sections.append("\nПОМЕСЯЧНАЯ СТАТИСТИКА:\n" + "\n".join(monthly_lines))

        # Budgets
        budget_repo = CategoryBudgetRepository(self.db)
        budgets = budget_repo.get_all_for_user(telegram_user_id)
        if budgets:
            budget_lines = []
            for b in budgets:
                spent = float(by_category.get(b.category, 0))
                limit_val = float(b.amount)
                pct = int(spent / limit_val * 100) if limit_val > 0 else 0
                warn = " ⚠️" if pct >= 90 else ""
                budget_lines.append(f"  {b.category}: {limit_val:.0f}₽/мес, потрачено {spent:.0f}₽ ({pct}%){warn}")
            sections.append("\nБЮДЖЕТЫ:\n" + "\n".join(budget_lines))

        # Planned expenses
        planned_repo = PlannedExpenseRepository(self.db)
        planned = planned_repo.list_future_for_user(telegram_user_id)
        if planned:
            planned_lines = [
                f"  {p.title}: {float(p.amount):.0f}₽, {p.planned_date}"
                for p in planned[:10]
            ]
            sections.append("\nПЛАНОВЫЕ РАСХОДЫ:\n" + "\n".join(planned_lines))

        # Recurring payments
        recurring_repo = RecurringTransactionRepository(self.db)
        recurring = recurring_repo.list_active(telegram_user_id)
        if recurring:
            recurring_lines = [
                f"  {r.title}: {float(r.amount):.0f}₽/{r.frequency} ({r.transaction_type})"
                for r in recurring
            ]
            sections.append("\nРЕГУЛЯРНЫЕ ПЛАТЕЖИ:\n" + "\n".join(recurring_lines))

        return "\n".join(sections)

    @staticmethod
    def _build_system_prompt(context: str) -> str:
        return (
            "Ты персональный финансовый ассистент. "
            "Отвечай кратко и по делу на русском языке.\n\n"
            f"ФИНАНСОВЫЕ ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:\n{context}\n\n"
            'Верни JSON: {"answer": "ответ на русском"}\n'
            "Опирайся только на предоставленные данные. "
            "Если данных недостаточно для ответа — скажи об этом."
        )
