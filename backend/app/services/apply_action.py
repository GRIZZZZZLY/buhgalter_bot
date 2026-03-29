from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class ApplyActionType(Enum):
    SET_BUDGET               = "set_budget"
    SET_TOTAL_BUDGET         = "set_total_budget"
    ADD_PLANNED_EXPENSE      = "add_planned_expense"
    SET_REMINDER             = "set_reminder"
    UPDATE_PLANNED_EXPENSE   = "update_planned_expense"
    DELETE_PLANNED_EXPENSE   = "delete_planned_expense"
    DELETE_REMINDER          = "delete_reminder"


REQUIRED_PAYLOAD_FIELDS: dict[str, list[str]] = {
    "set_budget":               ["category", "suggested_limit"],
    "set_total_budget":         ["amount"],
    "add_planned_expense":      ["title", "amount", "planned_date"],
    "set_reminder":             ["description", "amount", "payment_date"],
    "update_planned_expense":   ["planned_id", "amount"],
    "delete_planned_expense":   ["planned_id"],
    "delete_reminder":          ["reminder_id"],
}


@dataclass(frozen=True)
class ApplyAction:
    action_type: ApplyActionType
    label: str            # человекочитаемое: "Поставить бюджет еда 12 000 ₽"
    payload: dict         # параметры действия
    preview_text: str     # что покажем в confirm-экране
    is_reversible: bool   # можно ли отменить

    def __post_init__(self) -> None:
        required = REQUIRED_PAYLOAD_FIELDS.get(self.action_type.value, [])
        missing = [f for f in required if f not in self.payload]
        if missing:
            raise ValueError(
                f"ApplyAction({self.action_type.value}): "
                f"missing payload fields: {missing}"
            )

    def to_callback_data(self) -> str:
        """Сериализация для Telegram callback_data (max 64 bytes)."""
        key = hashlib.md5(
            json.dumps(self.payload, sort_keys=True).encode()
        ).hexdigest()[:8]
        return f"apply:{self.action_type.value}:{key}"
