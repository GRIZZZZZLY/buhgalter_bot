from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import ceil

from sqlalchemy.orm import Session

from app.models.savings_goal import SavingsGoal
from app.repositories.savings_goal_repository import SavingsGoalRepository


@dataclass
class GoalForecast:
    remaining: Decimal
    monthly_rate: Decimal | None      # None if no auto_percent or no income data
    months_to_goal: float | None      # None if can't calculate
    months_to_deadline: int | None    # None if no deadline
    on_track: bool | None             # None if no deadline
    suggested_percent: int | None     # only set when behind schedule


class SavingsGoalService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._repo = SavingsGoalRepository(db)

    def create(
        self,
        user_id: int,
        title: str,
        target_amount: Decimal,
        deadline: date | None = None,
        auto_percent: int | None = None,
    ) -> SavingsGoal:
        if target_amount <= 0:
            raise ValueError("target_amount must be > 0")
        if auto_percent is not None:
            auto_percent = max(0, min(100, auto_percent))
        return self._repo.create(
            user_id=user_id,
            title=title,
            target_amount=target_amount,
            deadline=deadline,
            auto_percent=auto_percent,
        )

    def deposit(
        self, user_id: int, goal_id: str, amount: Decimal
    ) -> tuple[SavingsGoal, bool]:
        """Add amount to goal. Returns (updated_goal, reached)."""
        goal = self._repo.get(user_id, goal_id)
        if goal is None or not goal.is_active:
            raise ValueError(f"Goal {goal_id} not found or inactive")
        new_amount = goal.current_amount + amount
        updated = self._repo.update_amount(goal, new_amount)
        reached = updated.current_amount >= updated.target_amount
        return updated, reached

    def list_active(self, user_id: int) -> list[SavingsGoal]:
        return self._repo.list_active(user_id)

    def complete(self, user_id: int, goal_id: str) -> SavingsGoal:
        goal = self._repo.get(user_id, goal_id)
        if goal is None:
            raise ValueError(f"Goal {goal_id} not found")
        return self._repo.complete(goal)

    def update_auto_percent(self, user_id: int, goal_id: str, percent: int) -> SavingsGoal:
        goal = self._repo.get(user_id, goal_id)
        if goal is None:
            raise ValueError(f"Goal {goal_id} not found")
        return self._repo.update_auto_percent(goal, percent)

    def fuzzy_find(self, user_id: int, query: str) -> tuple[SavingsGoal | None, float]:
        """Returns (goal, confidence). Confidence >= 0.8 is reliable."""
        return self._repo.fuzzy_match(user_id, query)

    def process_income(
        self, user_id: int, income_amount: Decimal
    ) -> list[tuple[SavingsGoal, Decimal, bool]]:
        """Auto-deduct from each active goal with auto_percent > 0.
        Returns list of (goal, deposited_amount, reached)."""
        results = []
        for goal in self._repo.list_active(user_id):
            if not goal.auto_percent:
                continue
            deposit_amount = (income_amount * goal.auto_percent / 100).quantize(Decimal("0.01"))
            if deposit_amount <= 0:
                continue
            updated, reached = self.deposit(user_id, goal.id, deposit_amount)
            results.append((updated, deposit_amount, reached))
        return results

    def calculate_forecast(self, goal: SavingsGoal, user_id: int) -> GoalForecast:
        """Deterministic forecast — no LLM."""
        remaining = max(Decimal("0"), goal.target_amount - goal.current_amount)

        from app.repositories.transaction_repository import TransactionRepository
        tx_repo = TransactionRepository(self.db)
        summary = tx_repo.get_summary(user_id, period="month")
        avg_income = Decimal(str(summary.get("income_total", 0)))

        monthly_rate: Decimal | None = None
        months_to_goal: float | None = None
        if goal.auto_percent and avg_income > 0:
            monthly_rate = (avg_income * goal.auto_percent / 100).quantize(Decimal("0.01"))
            if monthly_rate > 0:
                months_to_goal = float(remaining / monthly_rate)

        months_to_deadline: int | None = None
        on_track: bool | None = None
        suggested_percent: int | None = None

        if goal.deadline:
            today = date.today()
            delta = (goal.deadline - today).days
            months_to_deadline = max(0, ceil(delta / 30))

            if months_to_goal is not None and months_to_deadline > 0:
                on_track = months_to_goal <= months_to_deadline
                if not on_track and avg_income > 0 and months_to_deadline > 0:
                    needed_monthly = remaining / months_to_deadline
                    suggested_percent = ceil(float(needed_monthly / avg_income * 100)) + 1

        return GoalForecast(
            remaining=remaining,
            monthly_rate=monthly_rate,
            months_to_goal=months_to_goal,
            months_to_deadline=months_to_deadline,
            on_track=on_track,
            suggested_percent=suggested_percent,
        )
