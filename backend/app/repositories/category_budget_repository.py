from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.category_budget import CategoryBudget


class CategoryBudgetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, telegram_user_id: int, category: str) -> CategoryBudget | None:
        stmt = select(CategoryBudget).where(
            CategoryBudget.telegram_user_id == telegram_user_id,
            CategoryBudget.category == category,
        )
        return self.db.scalar(stmt)

    def get_all_for_user(self, telegram_user_id: int) -> list[CategoryBudget]:
        stmt = (
            select(CategoryBudget)
            .where(CategoryBudget.telegram_user_id == telegram_user_id)
            .order_by(CategoryBudget.amount.desc())
        )
        return list(self.db.scalars(stmt).all())

    def upsert(self, telegram_user_id: int, category: str, amount: float) -> CategoryBudget:
        budget = self.get(telegram_user_id, category)
        if budget is None:
            budget = CategoryBudget(
                telegram_user_id=telegram_user_id,
                category=category,
                amount=amount,
            )
            self.db.add(budget)
        else:
            budget.amount = amount
        self.db.flush()
        return budget

    def remove(self, telegram_user_id: int, category: str) -> bool:
        stmt = delete(CategoryBudget).where(
            CategoryBudget.telegram_user_id == telegram_user_id,
            CategoryBudget.category == category,
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return result.rowcount > 0

    def check_budget_exceeded(
        self, telegram_user_id: int, category: str, current_spent: Decimal
    ) -> tuple[bool, float | None, float | None]:
        """Check if spending in a category exceeds its budget.
        Returns (exceeded, budget_amount, spent_amount) or (False, None, None) if no budget set."""
        budget = self.get(telegram_user_id, category)
        if budget is None:
            return False, None, None
        exceeded = float(current_spent) > float(budget.amount)
        return exceeded, float(budget.amount), float(current_spent)
