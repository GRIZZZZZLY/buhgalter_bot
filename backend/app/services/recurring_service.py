"""Service for managing and firing recurring transactions."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.planned_expense_repository import PlannedExpenseRepository
from app.models.recurring_transaction import RecurringTransaction
from app.repositories.recurring_transaction_repository import RecurringTransactionRepository
from app.repositories.transaction_repository import TransactionRepository
from app.telegram.formatter import TreasuryFormatter

logger = logging.getLogger("finance_bot.recurring")
formatter = TreasuryFormatter()

FREQUENCY_LABELS = {
    "daily": "каждый день",
    "weekly": "каждую неделю",
    "monthly": "каждый месяц",
    "interval_days": "каждые N дней",
}

WEEKDAY_LABELS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


class RecurringService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.rt_repo = RecurringTransactionRepository(db)
        self.tx_repo = TransactionRepository(db)
        self.planned_repo = PlannedExpenseRepository(db)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        telegram_user_id: int,
        title: str,
        amount: float,
        transaction_type: str,
        category: str,
        frequency: str,
        day_value: int,
    ) -> RecurringTransaction:
        rt = self.rt_repo.create(
            telegram_user_id=telegram_user_id,
            title=title,
            amount=amount,
            transaction_type=transaction_type,
            category=category,
            frequency=frequency,
            day_value=day_value,
        )
        self.db.commit()
        return rt

    def list_active(self, telegram_user_id: int) -> list[RecurringTransaction]:
        return self.rt_repo.list_active(telegram_user_id)

    def deactivate(self, telegram_user_id: int, rt_id: int) -> bool:
        ok = self.rt_repo.deactivate(telegram_user_id, rt_id)
        if ok:
            self.db.commit()
        return ok

    def update_amount(self, telegram_user_id: int, rt_id: int, amount: float) -> RecurringTransaction | None:
        rt = self.rt_repo.get(telegram_user_id, rt_id)
        if rt is None:
            return None
        self.rt_repo.update(rt, amount=amount)
        self.db.commit()
        return rt

    def update_category(self, telegram_user_id: int, rt_id: int, category: str) -> RecurringTransaction | None:
        rt = self.rt_repo.get(telegram_user_id, rt_id)
        if rt is None:
            return None
        self.rt_repo.update(rt, category=category)
        self.db.commit()
        return rt

    def update_schedule(
        self,
        telegram_user_id: int,
        rt_id: int,
        frequency: str,
        day_value: int,
    ) -> RecurringTransaction | None:
        rt = self.rt_repo.get(telegram_user_id, rt_id)
        if rt is None:
            return None
        self.rt_repo.update(rt, frequency=frequency, day_value=day_value)
        # Recalculate next_run_date from today for simplicity
        rt.next_run_date = self.rt_repo._calc_next_run(frequency, day_value, date.today()).isoformat()
        self.db.commit()
        return rt

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_list(self, items: list[RecurringTransaction]) -> str:
        if not items:
            return (
                "📋 Повторяющихся транзакций нет.\n\n"
                "Добавить:\n"
                "/recurring аренда 45000 расход жильё ежемесячно 1\n"
                "/recurring зарплата 120000 доход зарплата ежемесячно 10\n"
                "/recurring netflix 799 расход подписки ежемесячно 15\n"
                "/recurring маникюр 2100 расход красота каждые 30"
            )

        lines = ["📋 Повторяющиеся транзакции:\n"]
        for rt in items:
            sign = "+" if rt.transaction_type == "income" else "−"
            cat_label = formatter.category_label(rt.category)
            freq_label = self._format_schedule(rt)
            lines.append(
                f"#{rt.id} {rt.title}: {sign}{float(rt.amount):,.0f} ₽ "
                f"({cat_label}) — {freq_label}\n"
                f"   Следующая: {rt.next_run_date}"
            )

        lines.append("\nУдалить: /recurring_del <номер>")
        return "\n".join(lines)

    def format_created(self, rt: RecurringTransaction) -> str:
        sign = "+" if rt.transaction_type == "income" else "−"
        cat_label = formatter.category_label(rt.category)
        freq_label = self._format_schedule(rt)
        return (
            f"✅ Добавлено: {rt.title} {sign}{float(rt.amount):,.0f} ₽ "
            f"({cat_label})\n"
            f"📅 {freq_label.capitalize()}, следующая: {rt.next_run_date}\n"
            "В дату события будет создан запланированный расход с подтверждением."
        )

    def format_reminder(self, rt: RecurringTransaction) -> str:
        sign = "+" if rt.transaction_type == "income" else "−"
        return (
            f"⏰ Завтра: {rt.title} {sign}{float(rt.amount):,.0f} ₽\n"
            f"Всё верно?"
        )

    def format_fired(self, rt: RecurringTransaction) -> str:
        return (
            f"📌 Создан запланированный платёж: {rt.title} — {float(rt.amount):,.0f} ₽\n"
            "В день события я попрошу подтвердить его."
        )

    # ------------------------------------------------------------------
    # Firing (called from scheduler)
    # ------------------------------------------------------------------

    def spawn_planned_expense(self, rt: RecurringTransaction) -> None:
        """Create a pending planned expense instead of auto-posting a transaction."""
        self.planned_repo.create(
            telegram_user_id=rt.telegram_user_id,
            title=rt.title,
            amount=float(rt.amount),
            category=rt.category,
            planned_date=date.fromisoformat(rt.next_run_date),
            source="recurring",
            recurring_transaction_id=rt.id,
        )
        self.rt_repo.advance(rt)
        self.db.commit()
        logger.info("recurring spawned planned expense: id=%s user=%s title=%s", rt.id, rt.telegram_user_id, rt.title)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_schedule(self, rt: RecurringTransaction) -> str:
        if rt.frequency == "daily":
            return "каждый день"
        if rt.frequency == "interval_days":
            return f"каждые {rt.day_value} дн."
        if rt.frequency == "weekly":
            day_label = WEEKDAY_LABELS[rt.day_value] if 0 <= rt.day_value <= 6 else "?"
            return f"каждую неделю ({day_label})"
        # monthly
        return f"каждый месяц, {rt.day_value}-го числа"


# ------------------------------------------------------------------
# Command parser
# ------------------------------------------------------------------

FREQUENCY_ALIASES: dict[str, str] = {
    "ежемесячно": "monthly",
    "monthly": "monthly",
    "месяц": "monthly",
    "каждый месяц": "monthly",
    "еженедельно": "weekly",
    "weekly": "weekly",
    "неделя": "weekly",
    "каждую неделю": "weekly",
    "ежедневно": "daily",
    "daily": "daily",
    "каждый день": "daily",
}

TYPE_ALIASES: dict[str, str] = {
    "расход": "expense",
    "трата": "expense",
    "expense": "expense",
    "доход": "income",
    "income": "income",
    "зарплата": "income",
}


def parse_recurring_args(args: list[str]) -> dict | str:
    """
    Parse /recurring command arguments.
    Expected: title amount type category frequency [day]
    Example:  аренда 45000 расход жильё ежемесячно 1
    Returns dict with parsed fields or error string.
    """
    if len(args) < 5:
        return (
            "Формат: /recurring название сумма тип категория частота [день]\n\n"
            "Примеры:\n"
            "  /recurring аренда 45000 расход жильё ежемесячно 1\n"
            "  /recurring зарплата 120000 доход зарплата ежемесячно 10\n"
            "  /recurring netflix 799 расход подписки ежемесячно 15\n"
            "  /recurring маникюр 2100 расход красота каждые 30\n\n"
            "Частота: ежемесячно / еженедельно / ежедневно / каждые N дней\n"
            "День: число месяца (1-28) или день недели (0=пн … 6=вс)"
        )

    title = args[0]

    try:
        amount = float(args[1].replace(",", ".").replace(" ", ""))
        if amount <= 0:
            return "❌ Сумма должна быть больше нуля."
    except ValueError:
        return f"❌ Не понял сумму: {args[1]}"

    tx_type = TYPE_ALIASES.get(args[2].lower())
    if tx_type is None:
        return f"❌ Тип должен быть 'расход' или 'доход', получил: {args[2]}"

    category = args[3].lower()

    schedule = parse_recurring_schedule_args(args[4:])
    if isinstance(schedule, str):
        return schedule
    frequency = schedule["frequency"]
    day_value = schedule["day_value"]

    if frequency == "monthly" and not (1 <= day_value <= 28):
        return "❌ День месяца должен быть от 1 до 28."
    if frequency == "weekly" and not (0 <= day_value <= 6):
        return "❌ День недели: 0=пн, 1=вт, 2=ср, 3=чт, 4=пт, 5=сб, 6=вс."

    return {
        "title": title,
        "amount": amount,
        "transaction_type": tx_type,
        "category": category,
        "frequency": frequency,
        "day_value": day_value,
    }


def parse_recurring_schedule_args(args: list[str]) -> dict | str:
    """Parse schedule update payload for recurring rule.
    Examples:
      ["ежемесячно", "10"] -> monthly day 10
      ["еженедельно", "4"] -> weekly Friday
      ["каждые", "30"] -> interval_days 30
    """
    if not args:
        return "❌ Укажи частоту: ежемесячно 10 / еженедельно 4 / каждые 30"

    # Human phrases: каждый месяц 10 числа / каждую неделю 4
    if len(args) >= 2 and args[0].lower() == "каждый" and args[1].lower() == "месяц":
        rest = args[2:]
        if rest and rest[-1].lower() == "числа":
            rest = rest[:-1]
        day_value = 1
        if rest:
            try:
                day_value = int(rest[0])
            except ValueError:
                return f"❌ День должен быть числом, получил: {rest[0]}"
        if not (1 <= day_value <= 28):
            return "❌ День месяца должен быть от 1 до 28."
        return {"frequency": "monthly", "day_value": day_value}

    if len(args) >= 2 and args[0].lower() == "каждую" and args[1].lower() == "неделю":
        rest = args[2:]
        day_value = 1
        if rest:
            try:
                day_value = int(rest[0])
            except ValueError:
                return f"❌ День должен быть числом, получил: {rest[0]}"
        if not (0 <= day_value <= 6):
            return "❌ День недели: 0=пн, 1=вт, 2=ср, 3=чт, 4=пт, 5=сб, 6=вс."
        return {"frequency": "weekly", "day_value": day_value}

    if args[0].lower() == "каждые":
        if len(args) < 2:
            return "❌ После 'каждые' укажи число дней."
        try:
            day_value = int(args[1])
        except ValueError:
            return f"❌ Интервал должен быть числом, получил: {args[1]}"
        if day_value <= 0:
            return "❌ Интервал должен быть больше 0 дней."
        return {"frequency": "interval_days", "day_value": day_value}

    frequency = FREQUENCY_ALIASES.get(args[0].lower())
    if frequency is None:
        return f"❌ Частота: ежемесячно / еженедельно / ежедневно / каждые N дней. Получил: {args[0]}"

    day_value = 1
    if len(args) >= 2:
        try:
            day_value = int(args[1])
        except ValueError:
            return f"❌ День должен быть числом, получил: {args[1]}"

    if frequency == "monthly" and not (1 <= day_value <= 28):
        return "❌ День месяца должен быть от 1 до 28."
    if frequency == "weekly" and not (0 <= day_value <= 6):
        return "❌ День недели: 0=пн, 1=вт, 2=ср, 3=чт, 4=пт, 5=сб, 6=вс."

    return {"frequency": frequency, "day_value": day_value}
