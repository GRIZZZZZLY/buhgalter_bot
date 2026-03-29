from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class ApplyActionType(Enum):
    SET_BUDGET          = "set_budget"
    SET_TOTAL_BUDGET    = "set_total_budget"
    ADD_PLANNED_EXPENSE = "add_planned_expense"
    SET_REMINDER        = "set_reminder"


@dataclass(frozen=True)
class ApplyAction:
    action_type: ApplyActionType
    label: str            # человекочитаемое: "Поставить бюджет еда 12 000 ₽"
    payload: dict         # параметры действия
    preview_text: str     # что покажем в confirm-экране
    is_reversible: bool   # можно ли отменить

    def to_callback_data(self) -> str:
        """Сериализация для Telegram callback_data (max 64 bytes)."""
        key = hashlib.md5(
            json.dumps(self.payload, sort_keys=True).encode()
        ).hexdigest()[:8]
        return f"apply:{self.action_type.value}:{key}"
