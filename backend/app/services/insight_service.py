"""Proactive spending insights with LLM-generated text."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.user import User
from app.repositories.transaction_repository import TransactionRepository

logger = logging.getLogger(__name__)

_MILESTONE_DAYS = (7, 14, 30)


@dataclass
class InsightFact:
    type: str
    data: dict


class InsightService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._repo = TransactionRepository(db)
        settings = get_settings()
        self._client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.groq_api_key,
            timeout=30.0,
        )
        self._model = settings.llm_model

    def get_realtime_insight(self, user: User, transaction) -> str | None:
        """Called after transaction save. Returns insight text or None (cooldown or no fact)."""
        if self._cooldown_active(user):
            return None
        fact = self._run_detectors(user)
        if fact is None:
            return None
        return self._generate_text(user, fact)

    def get_scheduled_insight(self, user: User) -> str | None:
        """Called from morning scheduler. Applies same daily cooldown as get_realtime_insight."""
        if self._cooldown_active(user):
            return None
        fact = self._run_detectors(user)
        if fact is None:
            return None
        return self._generate_text(user, fact)

    def _cooldown_active(self, user: User) -> bool:
        if user.last_insight_at is None:
            return False
        tz = ZoneInfo(user.timezone)
        today = datetime.now(tz).date()
        last = user.last_insight_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return last.astimezone(tz).date() == today

    def _mark_sent(self, user: User) -> None:
        user.last_insight_at = datetime.now(timezone.utc)
        self.db.add(user)
        self.db.commit()

    def _run_detectors(self, user: User) -> InsightFact | None:
        for detector in (
            self._detect_category_spike,
            self._detect_budget_milestone,
            self._detect_weekly_anomaly,
            self._detect_category_record,
            self._detect_motivational_streak,
        ):
            try:
                fact = detector(user)
                if fact is not None:
                    return fact
            except Exception:
                logger.exception("detector %s failed", detector.__name__)
        return None

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def _detect_category_spike(self, user: User) -> InsightFact | None:
        """Category spending this week > 150% of last week AND delta > 500."""
        now = self._now_utc()
        this_week_start = now - timedelta(days=7)
        last_week_start = now - timedelta(days=14)

        this_week = self._repo.sum_expenses_by_category(
            user.telegram_user_id, this_week_start, now
        )
        last_week = self._repo.sum_expenses_by_category(
            user.telegram_user_id, last_week_start, this_week_start
        )

        best_category = None
        best_delta = Decimal("0")
        best_this = Decimal("0")
        best_prev = Decimal("0")

        for cat, this_amt in this_week.items():
            prev_amt = last_week.get(cat, Decimal("0"))
            if prev_amt == 0:
                continue
            if this_amt > prev_amt * Decimal("1.5") and (this_amt - prev_amt) > Decimal("500"):
                delta = this_amt - prev_amt
                if delta > best_delta:
                    best_delta = delta
                    best_category = cat
                    best_this = this_amt
                    best_prev = prev_amt

        if best_category is None:
            return None

        delta_pct = int((best_this - best_prev) / best_prev * 100)
        return InsightFact(type="category_spike", data={
            "category": best_category,
            "this_week": int(best_this),
            "last_week": int(best_prev),
            "delta_pct": delta_pct,
        })

    def _detect_budget_milestone(self, user: User) -> InsightFact | None:
        """N consecutive days within daily budget limit.
        daily_limit = budget_amount / 30 — intentional fixed divisor treating budget as monthly.
        budget_start_day is not used here (not relevant for streak detection).
        """
        if not user.budget_amount:
            return None

        daily_limit = Decimal(str(user.budget_amount)) / 30
        now = self._now_utc()
        start = now - timedelta(days=30)
        per_day = self._repo.sum_expenses_per_day(user.telegram_user_id, start, now)

        today = now.date()
        streak = 0
        for i in range(30):
            d = today - timedelta(days=i)
            if d not in per_day:
                break
            day_total = per_day[d]
            if day_total <= daily_limit:
                streak += 1
            else:
                break

        if streak in _MILESTONE_DAYS:
            return InsightFact(type="budget_milestone", data={
                "streak_days": streak,
                "daily_limit": int(daily_limit),
            })
        return None

    def _detect_weekly_anomaly(self, user: User) -> InsightFact | None:
        """This week's spend > 130% of average weekly spend over last month."""
        now = self._now_utc()
        this_week_start = now - timedelta(days=7)
        last_month_start = now - timedelta(days=30)

        this_week_cats = self._repo.sum_expenses_by_category(
            user.telegram_user_id, this_week_start, now
        )
        last_month_cats = self._repo.sum_expenses_by_category(
            user.telegram_user_id, last_month_start, this_week_start
        )

        this_week_total = sum(this_week_cats.values(), Decimal("0"))
        last_month_total = sum(last_month_cats.values(), Decimal("0"))

        if last_month_total == 0:
            return None

        avg_weekly = last_month_total / 4
        if this_week_total > avg_weekly * Decimal("1.3"):
            delta_pct = int((this_week_total - avg_weekly) / avg_weekly * 100)
            return InsightFact(type="weekly_anomaly", data={
                "this_week": int(this_week_total),
                "avg_weekly": int(avg_weekly),
                "delta_pct": delta_pct,
            })
        return None

    def _detect_category_record(self, user: User) -> InsightFact | None:
        """A category this month > 140% of same category last month."""
        now = self._now_utc()
        this_month_start = now - timedelta(days=30)
        last_month_start = now - timedelta(days=60)

        this_month = self._repo.sum_expenses_by_category(
            user.telegram_user_id, this_month_start, now
        )
        last_month = self._repo.sum_expenses_by_category(
            user.telegram_user_id, last_month_start, this_month_start
        )

        best_cat = None
        best_ratio = Decimal("1.4")
        best_this = Decimal("0")
        best_prev = Decimal("0")

        for cat, this_amt in this_month.items():
            prev_amt = last_month.get(cat, Decimal("0"))
            if prev_amt == 0:
                continue
            ratio = this_amt / prev_amt
            if ratio > best_ratio:
                best_ratio = ratio
                best_cat = cat
                best_this = this_amt
                best_prev = prev_amt

        if best_cat is None:
            return None

        return InsightFact(type="category_record", data={
            "category": best_cat,
            "this_month": int(best_this),
            "last_month": int(best_prev),
        })

    def _detect_motivational_streak(self, user: User) -> InsightFact | None:
        """3rd or more transaction today (uses cached counter)."""
        if user.transactions_today >= 3:
            return InsightFact(type="motivational_streak", data={
                "count": user.transactions_today,
            })
        return None

    def _generate_text(self, user: User, fact: InsightFact) -> str | None:
        system = (
            "Ты финансовый ассистент. Напиши 1-2 живых предложения на русском языке "
            "по данному инсайту. Тон: дружелюбный, без занудства, с уместным эмодзи."
        )
        user_msg = json.dumps({"type": fact.type, **fact.data}, ensure_ascii=False)
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.7,
                max_tokens=120,
            )
            text = (response.choices[0].message.content or "").strip()
            if text:
                self._mark_sent(user)
                return text
            return None
        except Exception as exc:
            logger.error("InsightService LLM error: %s", exc)
            return None
