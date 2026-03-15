"""Service responsible for building morning briefing and evening check-in messages."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.user_category_mapping_repository import UserCategoryMappingRepository
from app.repositories.user_repository import UserRepository
from app.telegram.formatter import TreasuryFormatter

logger = logging.getLogger("finance_bot.reminders")
formatter = TreasuryFormatter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SMART_SILENCE_THRESHOLD = 3  # skip evening reminder if user logged >= N transactions today
MAX_IGNORED_BEFORE_THROTTLE = 3  # after N ignored evenings, send only every 3rd day

CATEGORY_EMOJI = {
    "food": "\U0001f354",       # 🍔
    "transport": "\U0001f695",  # 🚕
    "housing": "\U0001f3e0",    # 🏠
    "health": "\U0001f48a",     # 💊
    "beauty": "\U0001f484",     # 💄
    "entertainment": "\U0001f3ad",  # 🎭
    "subscriptions": "\U0001f4f1",  # 📱
    "shopping": "\U0001f6cd\ufe0f",  # 🛍️
    "home": "\U0001f3e1",       # 🏡
    "telecom": "\U0001f4de",    # 📞
    "work": "\U0001f4bb",       # 💻
    "education": "\U0001f4da",  # 📚
    "gifts": "\U0001f381",      # 🎁
    "fees": "\U0001f4b3",       # 💳
    "salary": "\U0001f4b0",     # 💰
    "freelance": "\U0001f4bc",  # 💼
    "other": "\U0001f4cc",      # 📌
}


class ReminderService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.tx_repo = TransactionRepository(db)
        self.mapping_repo = UserCategoryMappingRepository(db)

    # ------------------------------------------------------------------
    # Morning briefing
    # ------------------------------------------------------------------
    def build_morning_briefing(self, user: User) -> str | None:
        """Build the morning briefing message. Returns None if nothing to send."""
        try:
            tz = ZoneInfo(user.timezone)
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        today_str = now_local.date().isoformat()

        # Update streak
        self.user_repo.update_streak(user, today_str)

        summary = self.tx_repo.get_summary(user.telegram_user_id, period="month")
        expense_total = Decimal(summary["expense_total"])
        income_total = Decimal(summary["income_total"])

        lines: list[str] = ["\U0001f305 Доброе утро!"]  # 🌅

        # Daily budget calculation
        if user.budget_amount:
            budget = Decimal(str(user.budget_amount))
            remaining_budget = budget - expense_total
            days_left = self._days_left_in_budget_period(now_local.date(), user.budget_start_day)
            daily_budget = remaining_budget / days_left if days_left > 0 else remaining_budget

            if daily_budget > 0:
                lines.append(f"\U0001f4b0 На сегодня: {daily_budget:,.0f} \u20bd")
            else:
                lines.append(f"\u26a0\ufe0f Бюджет исчерпан! Перерасход: {abs(remaining_budget):,.0f} \u20bd")

            # Budget vs time progress
            total_days = self._total_days_in_budget_period(now_local.date(), user.budget_start_day)
            days_passed = total_days - days_left
            budget_pct = (float(expense_total) / float(budget) * 100) if budget > 0 else 0
            time_pct = (days_passed / total_days * 100) if total_days > 0 else 0

            if budget_pct <= time_pct:
                status = "\u2014 в плане! \u2705"
            elif budget_pct <= time_pct + 10:
                status = "\u2014 почти в плане \U0001f7e1"
            else:
                status = "\u2014 перерасход! \U0001f534"

            lines.append(
                f"\U0001f4ca Месяц: потрачено {budget_pct:.0f}% бюджета, "
                f"прошло {time_pct:.0f}% времени {status}"
            )
        else:
            # No budget set — show simple balance
            balance = income_total - expense_total
            sign = "+" if balance >= 0 else ""
            lines.append(f"\U0001f4ca Баланс за месяц: {sign}{balance:,.0f} \u20bd")

        # Streak
        if user.streak_days > 1:
            lines.append(f"\U0001f525 Серия: {user.streak_days} дней подряд!")
        elif user.streak_days == 1:
            lines.append("\U0001f525 Начало серии! Записывай расходы каждый день")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Evening check-in
    # ------------------------------------------------------------------
    def build_evening_checkin(self, user: User) -> tuple[str | None, list[str]]:
        """
        Build evening check-in message.
        Returns (message, top_category_slugs) or (None, []) if should be silent.
        top_category_slugs are used to build quick-reply buttons.
        """
        try:
            tz = ZoneInfo(user.timezone)
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        today_str = now_local.date().isoformat()

        # Smart silence: skip if user already logged enough today
        if user.transactions_today_date == today_str and user.transactions_today >= SMART_SILENCE_THRESHOLD:
            return None, []

        # Throttle: if user ignores too many evenings, reduce frequency
        if user.ignored_evening_reminders >= MAX_IGNORED_BEFORE_THROTTLE:
            # Only send every 3rd day
            day_of_year = now_local.timetuple().tm_yday
            if day_of_year % 3 != 0:
                return None, []

        # Build message
        tx_count = user.transactions_today if user.transactions_today_date == today_str else 0

        lines: list[str] = ["\U0001f319 Вечерний чек-ин"]  # 🌙

        if tx_count > 0:
            # User logged some transactions today
            today_summary = self.tx_repo.get_summary(user.telegram_user_id, period="today")
            today_expense = Decimal(today_summary["expense_total"])
            lines.append(f"\nСегодня записано: {tx_count} расход(ов) на {today_expense:,.0f} \u20bd")
            lines.append("Забыли что-то записать?")
        else:
            lines.append("\nСегодня пока ничего не записано.")
            lines.append("Забыли что-то записать?")

        # Get personalized top categories for quick buttons
        top_categories = self._get_user_top_categories(user.telegram_user_id)

        return "\n".join(lines), top_categories

    def should_send_evening(self, user: User) -> bool:
        """Check if evening reminder should be sent based on smart silence rules."""
        msg, _ = self.build_evening_checkin(user)
        return msg is not None

    # ------------------------------------------------------------------
    # Streak loss notification
    # ------------------------------------------------------------------
    def build_streak_loss_message(self, user: User, previous_streak: int) -> str | None:
        """Build a message when user loses their streak."""
        if previous_streak < 3:
            return None  # Don't notify for very short streaks
        return (
            f"\U0001f614 Серия прервалась (было {previous_streak} дней).\n"
            f"Начнём новую? Запиши любой расход!"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_user_top_categories(self, telegram_user_id: int) -> list[str]:
        """Get top 3 expense categories for the user based on recent transactions."""
        # First try user's learned mappings
        top_from_mappings = self.mapping_repo.get_top_categories(telegram_user_id, limit=3)
        if len(top_from_mappings) >= 3:
            return top_from_mappings[:3]

        # Fall back to actual transaction categories from this month
        summary = self.tx_repo.get_summary(telegram_user_id, period="month")
        top_from_tx = [item["category"] for item in summary["top_expense_categories"]]

        # Merge: mappings first, then fill from transactions
        seen = set(top_from_mappings)
        result = list(top_from_mappings)
        for cat in top_from_tx:
            if cat not in seen and len(result) < 3:
                result.append(cat)
                seen.add(cat)

        # If still not enough, use defaults
        defaults = ["food", "transport", "entertainment"]
        for cat in defaults:
            if cat not in seen and len(result) < 3:
                result.append(cat)
                seen.add(cat)

        return result[:3]

    @staticmethod
    def _days_left_in_budget_period(today: date, start_day: int) -> int:
        """Calculate days remaining in the current budget period."""
        start_day = min(start_day, 28)  # Clamp to avoid month-end issues

        if today.day >= start_day:
            # Current period started this month
            next_month = today.month + 1 if today.month < 12 else 1
            next_year = today.year if today.month < 12 else today.year + 1
            period_end = date(next_year, next_month, start_day)
        else:
            # Current period started last month
            period_end = date(today.year, today.month, start_day)

        return max((period_end - today).days, 1)

    @staticmethod
    def _total_days_in_budget_period(today: date, start_day: int) -> int:
        """Calculate total days in the current budget period."""
        start_day = min(start_day, 28)

        if today.day >= start_day:
            period_start = date(today.year, today.month, start_day)
            next_month = today.month + 1 if today.month < 12 else 1
            next_year = today.year if today.month < 12 else today.year + 1
            period_end = date(next_year, next_month, start_day)
        else:
            prev_month = today.month - 1 if today.month > 1 else 12
            prev_year = today.year if today.month > 1 else today.year - 1
            period_start = date(prev_year, prev_month, start_day)
            period_end = date(today.year, today.month, start_day)

        return max((period_end - period_start).days, 1)

    @staticmethod
    def category_emoji(slug: str) -> str:
        return CATEGORY_EMOJI.get(slug, "\U0001f4cc")
