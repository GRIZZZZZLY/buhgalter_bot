from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.repositories.category_budget_repository import CategoryBudgetRepository
from app.services.apply_action import ApplyAction, ApplyActionType
from app.services.planned_expense_service import PlannedExpenseService


@dataclass(frozen=True)
class ActionResult:
    success: bool
    message: str


class ActionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def execute(self, action: ApplyAction, telegram_user_id: int) -> ActionResult:
        if action.action_type == ApplyActionType.SET_BUDGET:
            return self._set_budget(action, telegram_user_id)
        if action.action_type == ApplyActionType.SET_REMINDER:
            return self._set_reminder(action, telegram_user_id)
        if action.action_type == ApplyActionType.ADD_PLANNED_EXPENSE:
            return self._add_planned_expense(action, telegram_user_id)
        if action.action_type == ApplyActionType.SET_TOTAL_BUDGET:
            return ActionResult(
                success=False,
                message="Установка общего бюджета пока не реализована.",
            )
        return ActionResult(success=False, message=f"Неизвестный тип действия: {action.action_type}")

    def _set_budget(self, action: ApplyAction, telegram_user_id: int) -> ActionResult:
        try:
            category: str = action.payload["category"]
            amount: float = float(action.payload["suggested_limit"])
        except (KeyError, TypeError, ValueError) as exc:
            return ActionResult(success=False, message=f"Некорректные данные действия: {exc}")

        repo = CategoryBudgetRepository(self.db)
        repo.upsert(telegram_user_id, category, amount)
        self.db.commit()

        return ActionResult(
            success=True,
            message=f"✅ Бюджет «{category}» установлен: {amount:.0f} ₽/мес",
        )

    def _set_reminder(self, action: ApplyAction, telegram_user_id: int) -> ActionResult:
        try:
            description: str = action.payload["description"]
            amount: float = float(action.payload["amount"])
            payment_date: date = date.fromisoformat(action.payload["payment_date"])
        except (KeyError, TypeError, ValueError) as exc:
            return ActionResult(success=False, message=f"Некорректные данные действия: {exc}")

        svc = PlannedExpenseService(self.db)
        svc.create_manual(
            telegram_user_id=telegram_user_id,
            title=description,
            amount=amount,
            category="other",
            planned_date=payment_date,
            reminder_time="09:00",
        )

        return ActionResult(
            success=True,
            message=f"✅ Напоминание о «{description}» добавлено на {payment_date}.",
        )

    def _add_planned_expense(self, action: ApplyAction, telegram_user_id: int) -> ActionResult:
        try:
            title: str = action.payload["title"]
            amount: float = float(action.payload["amount"])
            category: str = action.payload["category"]
            planned_date: date = date.fromisoformat(action.payload["planned_date"])
        except (KeyError, TypeError, ValueError) as exc:
            return ActionResult(success=False, message=f"Некорректные данные действия: {exc}")

        svc = PlannedExpenseService(self.db)
        svc.create_manual(
            telegram_user_id=telegram_user_id,
            title=title,
            amount=amount,
            category=category,
            planned_date=planned_date,
        )

        return ActionResult(
            success=True,
            message=f"✅ Плановая трата «{title}» добавлена на {planned_date}.",
        )
