from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from sqlalchemy.orm import Session

from app.repositories.category_budget_repository import CategoryBudgetRepository
from app.services.apply_action import ApplyAction, ApplyActionType
from app.services.planned_expense_service import PlannedExpenseService

_DEFAULT_REMINDER_TIME = "09:00"


class ActionStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass
class ActionResult:
    status: ActionStatus
    action_type: str
    message: str
    detail: str = ""
    is_reversible: bool = False
    undo_payload: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.status == ActionStatus.SUCCESS


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
                status=ActionStatus.FAILURE,
                action_type=ApplyActionType.SET_TOTAL_BUDGET.value,
                message="Установка общего бюджета пока не поддерживается. Настройте бюджеты по категориям.",
            )
        return ActionResult(
            status=ActionStatus.FAILURE,
            action_type=action.action_type.value,
            message=f"Неизвестный тип действия: {action.action_type.value}",
        )

    def _set_budget(self, action: ApplyAction, telegram_user_id: int) -> ActionResult:
        try:
            category: str = action.payload["category"]
            amount: float = float(action.payload["suggested_limit"])
        except (KeyError, TypeError, ValueError):
            return ActionResult(
                status=ActionStatus.FAILURE,
                action_type=ApplyActionType.SET_BUDGET.value,
                message="Недостаточно данных для установки бюджета.",
            )

        repo = CategoryBudgetRepository(self.db)
        existing = repo.get(telegram_user_id, category)
        old_amount = float(existing.amount) if existing else 0.0
        repo.upsert(telegram_user_id, category, float(amount))
        self.db.commit()

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_type=ApplyActionType.SET_BUDGET.value,
            message=f"✅ Бюджет «{category}» установлен: {float(amount):.0f} ₽/мес",
            detail="",
            is_reversible=True,
            undo_payload={
                "action_type": ApplyActionType.SET_BUDGET.value,
                "category": category,
                "old_amount": old_amount,
            },
        )

    def _set_reminder(self, action: ApplyAction, telegram_user_id: int) -> ActionResult:
        try:
            description: str = action.payload["description"]
            amount: float = float(action.payload["amount"])
            payment_date: date = date.fromisoformat(action.payload["payment_date"])
        except (KeyError, TypeError, ValueError):
            return ActionResult(
                status=ActionStatus.FAILURE,
                action_type=ApplyActionType.SET_REMINDER.value,
                message="Недостаточно данных для создания напоминания.",
            )

        svc = PlannedExpenseService(self.db)
        item = svc.create_manual(
            telegram_user_id=telegram_user_id,
            title=description,
            amount=amount,
            category="other",
            planned_date=payment_date,
            reminder_time=_DEFAULT_REMINDER_TIME,
        )
        payment_date_str = str(payment_date)

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_type=ApplyActionType.SET_REMINDER.value,
            message=f"✅ Напоминание о «{description}» добавлено на {payment_date_str}.",
            is_reversible=True,
            undo_payload={
                "action_type": ApplyActionType.SET_REMINDER.value,
                "planned_id": item.id,
                "description": description,
            },
        )

    def _add_planned_expense(self, action: ApplyAction, telegram_user_id: int) -> ActionResult:
        try:
            title: str = action.payload["title"]
            amount: float = float(action.payload["amount"])
            category: str = action.payload["category"]
            planned_date: date = date.fromisoformat(action.payload["planned_date"])
        except (KeyError, TypeError, ValueError):
            return ActionResult(
                status=ActionStatus.FAILURE,
                action_type=ApplyActionType.ADD_PLANNED_EXPENSE.value,
                message="Недостаточно данных для создания плановой траты.",
            )

        svc = PlannedExpenseService(self.db)
        item = svc.create_manual(
            telegram_user_id=telegram_user_id,
            title=title,
            amount=amount,
            category=category,
            planned_date=planned_date,
        )
        planned_date_str = str(planned_date)

        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_type=ApplyActionType.ADD_PLANNED_EXPENSE.value,
            message=f"✅ Плановая трата «{title}» добавлена на {planned_date_str}.",
            is_reversible=True,
            undo_payload={
                "action_type": ApplyActionType.ADD_PLANNED_EXPENSE.value,
                "planned_id": item.id,
                "title": title,
            },
        )

    # ------------------------------------------------------------------
    # Undo
    # ------------------------------------------------------------------

    def undo(self, undo_payload: dict, telegram_user_id: int) -> ActionResult:
        """Отменяет последнее выполненное действие."""
        action_type = undo_payload.get("action_type")

        undo_handlers = {
            ApplyActionType.SET_BUDGET.value:          self._undo_set_budget,
            ApplyActionType.SET_REMINDER.value:        self._undo_set_reminder,
            ApplyActionType.ADD_PLANNED_EXPENSE.value: self._undo_add_planned_expense,
        }

        handler = undo_handlers.get(action_type)
        if not handler:
            return ActionResult(
                status=ActionStatus.FAILURE,
                action_type=action_type or "unknown",
                message="Не удалось отменить действие.",
            )
        try:
            return handler(undo_payload, telegram_user_id)
        except Exception as exc:
            return ActionResult(
                status=ActionStatus.FAILURE,
                action_type=action_type or "unknown",
                message="Ошибка при отмене. Данные не изменены.",
                error=str(exc),
            )

    def _undo_set_budget(self, payload: dict, telegram_user_id: int) -> ActionResult:
        category = payload["category"]
        old_amount = float(payload["old_amount"])
        repo = CategoryBudgetRepository(self.db)
        if old_amount == 0.0:
            repo.remove(telegram_user_id, category)
        else:
            repo.upsert(telegram_user_id, category, old_amount)
        self.db.commit()
        action_word = "удалён" if old_amount == 0.0 else f"возвращён: {old_amount:.0f} ₽/мес"
        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_type=ApplyActionType.SET_BUDGET.value,
            message=f"↩ Бюджет «{category}» {action_word}",
        )

    def _undo_set_reminder(self, payload: dict, telegram_user_id: int) -> ActionResult:
        planned_id = payload["planned_id"]
        description = payload.get("description", "")
        svc = PlannedExpenseService(self.db)
        svc.delete_planned(telegram_user_id, planned_id)
        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_type=ApplyActionType.SET_REMINDER.value,
            message=f"↩ Напоминание «{description}» удалено",
        )

    def _undo_add_planned_expense(self, payload: dict, telegram_user_id: int) -> ActionResult:
        planned_id = payload["planned_id"]
        title = payload.get("title", "")
        svc = PlannedExpenseService(self.db)
        svc.delete_planned(telegram_user_id, planned_id)
        return ActionResult(
            status=ActionStatus.SUCCESS,
            action_type=ApplyActionType.ADD_PLANNED_EXPENSE.value,
            message=f"↩ Плановая трата «{title}» удалена",
        )
