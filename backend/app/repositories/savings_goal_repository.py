import difflib
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.savings_goal import SavingsGoal


class SavingsGoalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        user_id: int,
        title: str,
        target_amount: Decimal,
        deadline=None,
        auto_percent: int | None = None,
    ) -> SavingsGoal:
        goal = SavingsGoal(
            user_id=user_id,
            title=title,
            target_amount=target_amount,
            deadline=deadline,
            auto_percent=auto_percent,
        )
        self.db.add(goal)
        self.db.commit()
        self.db.refresh(goal)
        return goal

    def list_active(self, user_id: int) -> list[SavingsGoal]:
        stmt = (
            select(SavingsGoal)
            .where(SavingsGoal.user_id == user_id, SavingsGoal.is_active == True)  # noqa: E712
            .order_by(SavingsGoal.created_at)
        )
        return list(self.db.execute(stmt).scalars())

    def get(self, user_id: int, goal_id: str) -> SavingsGoal | None:
        stmt = select(SavingsGoal).where(
            SavingsGoal.id == goal_id, SavingsGoal.user_id == user_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def update_amount(self, goal: SavingsGoal, new_amount: Decimal) -> SavingsGoal:
        goal.current_amount = new_amount
        self.db.commit()
        return goal

    def update_auto_percent(self, goal: SavingsGoal, percent: int) -> SavingsGoal:
        goal.auto_percent = max(0, min(100, percent))
        self.db.commit()
        return goal

    def complete(self, goal: SavingsGoal) -> SavingsGoal:
        goal.is_active = False
        self.db.commit()
        return goal

    def fuzzy_match(self, user_id: int, query: str) -> tuple[SavingsGoal | None, float]:
        """Find best matching active goal by title. Returns (goal, confidence 0-1)."""
        goals = self.list_active(user_id)
        if not goals:
            return None, 0.0
        query_lower = query.lower()
        best_goal: SavingsGoal | None = None
        best_score = 0.0
        for goal in goals:
            title_lower = goal.title.lower()
            score = difflib.SequenceMatcher(None, query_lower, title_lower).ratio()
            if query_lower in title_lower:
                score = max(score, 0.85)
            if score > best_score:
                best_score = score
                best_goal = goal
        return best_goal, best_score
