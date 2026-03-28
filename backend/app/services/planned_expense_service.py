from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.planned_expense_repository import PlannedExpenseRepository
from app.repositories.transaction_repository import TransactionRepository
from app.services.transaction_service import TransactionService


@dataclass(slots=True)
class PlannedExpenseItem:
    id: int
    title: str
    amount: str
    category: str
    planned_date: str
    source: str
    status: str


@dataclass(slots=True)
class PlannedExpenseConfirmationResult:
    planned: PlannedExpenseItem
    transaction: object | None


class PlannedExpenseService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = PlannedExpenseRepository(db)
        self.tx_repo = TransactionRepository(db)
        self.tx_service = TransactionService(db)

    def create_manual(
        self,
        telegram_user_id: int,
        title: str,
        amount: float,
        category: str,
        planned_date: date,
        reminder_time: str | None = None,
    ) -> PlannedExpenseItem:
        item = self.repo.create(
            telegram_user_id=telegram_user_id,
            title=title,
            amount=amount,
            category=category,
            planned_date=planned_date,
            source="manual",
            reminder_time=reminder_time,
        )
        self.db.commit()
        return self._to_item(item)

    def list_future(self, telegram_user_id: int) -> list[PlannedExpenseItem]:
        return [self._to_item(x) for x in self.repo.list_future_for_user(telegram_user_id)]

    def list_due_today(self, today: date, telegram_user_id: int | None = None) -> list[PlannedExpenseItem]:
        return [self._to_item(x) for x in self.repo.list_due_today(today, telegram_user_id)]

    def list_for_week(self, telegram_user_id: int, start: date, end: date) -> list[PlannedExpenseItem]:
        return [self._to_item(x) for x in self.repo.list_for_week(telegram_user_id, start, end)]

    def list_all(self, telegram_user_id: int, today: date | None = None) -> list[PlannedExpenseItem]:
        today = today or date.today()
        items = [self._to_item(x) for x in self.repo.list_all_for_user(telegram_user_id)]
        overdue = [x for x in items if date.fromisoformat(x.planned_date) < today]
        future = [x for x in items if date.fromisoformat(x.planned_date) >= today]
        return overdue + future

    def confirm_expense(
        self,
        telegram_user_id: int,
        planned_expense_id: int,
        actual_amount: float | None = None,
    ) -> PlannedExpenseConfirmationResult | None:
        item = self.repo.get(telegram_user_id, planned_expense_id)
        if item is None or item.status.value != "pending":
            return None

        tx_amount = Decimal(str(actual_amount if actual_amount is not None else item.amount))
        transaction = self.tx_repo.create(
            {
                "telegram_user_id": telegram_user_id,
                "type": "expense",
                "amount": tx_amount,
                "category": item.category,
                "description": item.title,
                "source": "text",
                "raw_input": f"[planned] {item.title}",
                "confidence": 1.0,
            }
        )
        confirmed = self.repo.mark_confirmed(item)
        self.db.commit()
        return PlannedExpenseConfirmationResult(
            planned=self._to_item(confirmed),
            transaction=self.tx_service._to_item(transaction),
        )

    def cancel_expense(self, telegram_user_id: int, planned_expense_id: int) -> PlannedExpenseItem | None:
        item = self.repo.get(telegram_user_id, planned_expense_id)
        if item is None or item.status.value != "pending":
            return None
        cancelled = self.repo.mark_cancelled(item)
        self.db.commit()
        return self._to_item(cancelled)

    def delete_planned(self, telegram_user_id: int, planned_expense_id: int) -> PlannedExpenseItem | None:
        return self.cancel_expense(telegram_user_id, planned_expense_id)

    def update_planned_date(
        self,
        telegram_user_id: int,
        planned_expense_id: int,
        planned_date: date,
    ) -> PlannedExpenseItem | None:
        item = self.repo.get(telegram_user_id, planned_expense_id)
        if item is None or item.status.value != "pending":
            return None
        updated = self.repo.update_planned_date(item, planned_date)
        self.db.commit()
        return self._to_item(updated)

    @staticmethod
    def _to_item(item) -> PlannedExpenseItem:
        return PlannedExpenseItem(
            id=item.id,
            title=item.title,
            amount=f"{Decimal(item.amount):.2f}",
            category=item.category,
            planned_date=item.planned_date.isoformat(),
            source=item.source.value,
            status=item.status.value,
        )


def parse_plan_args(args: list[str]) -> dict | str:
    """Parse /plan command.
    Supports:
      /plan маникюр 2100 15.04 красота
      /plan маникюр 2100 2030-04-15 красота
      /plan маникюр 2100 завтра красота
      /plan маникюр 2100 через 10 дней красота
      /plan маникюр 2100 в следующий вторник красота
      /plan маникюр 2100 1 мая красота
    """
    if len(args) < 4:
        return (
            "Формат: /plan название сумма дата категория\n"
            "Примеры:\n"
            "  /plan маникюр 2100 15.04 красота\n"
            "  /plan стоматолог 8000 2030-04-22 здоровье\n"
            "  /plan маникюр 2100 завтра красота\n"
            "  /plan маникюр 2100 через 10 дней красота"
        )

    # Find the first numeric token -> amount
    amount_index = next((i for i, token in enumerate(args) if _looks_like_amount_token(token)), None)
    if amount_index is None:
        return f"❌ Не понял сумму: {args[1] if len(args) > 1 else ''}"
    if amount_index == 0 or amount_index >= len(args) - 1:
        return "❌ Формат: /plan название сумма дата категория"

    title = " ".join(args[:amount_index]).strip()
    raw_amount = args[amount_index]
    category = args[-1].lower().strip()
    date_tokens = args[amount_index + 1 : -1]

    try:
        amount = float(raw_amount.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            return "❌ Сумма должна быть больше нуля."
    except ValueError:
        return f"❌ Не понял сумму: {raw_amount}"

    planned_date = _parse_future_date_phrase(date_tokens)
    if isinstance(planned_date, str):
        return planned_date

    return {
        "title": title,
        "amount": amount,
        "planned_date": planned_date,
        "category": category,
    }


def _looks_like_number(token: str) -> bool:
    token = token.replace(",", ".")
    try:
        float(token)
        return True
    except ValueError:
        return False


def _looks_like_amount_token(token: str) -> bool:
    # Exclude date-like tokens such as 15.04 or 2030-04-15
    if "-" in token:
        return False
    if token.count(".") == 1:
        left, right = token.split(".")
        if left.isdigit() and right.isdigit() and 1 <= len(left) <= 2 and 1 <= len(right) <= 2:
            return False
    return _looks_like_number(token)


_FUTURE_WEEKDAY = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
    "воскресенье": 6,
    "пн": 0,
    "вт": 1,
    "ср": 2,
    "чт": 3,
    "пт": 4,
    "сб": 5,
    "вс": 6,
}

_MONTH_NAMES = {
    "января": 1, "январь": 1, "янв": 1,
    "февраля": 2, "февраль": 2, "фев": 2,
    "марта": 3, "март": 3, "мар": 3,
    "апреля": 4, "апрель": 4, "апр": 4,
    "мая": 5, "май": 5,
    "июня": 6, "июнь": 6, "июн": 6,
    "июля": 7, "июль": 7, "июл": 7,
    "августа": 8, "август": 8, "авг": 8,
    "сентября": 9, "сентябрь": 9, "сен": 9,
    "октября": 10, "октябрь": 10, "окт": 10,
    "ноября": 11, "ноябрь": 11, "ноя": 11,
    "декабря": 12, "декабрь": 12, "дек": 12,
}


def _parse_future_date_phrase(tokens: list[str]) -> date | str:
    if not tokens:
        return "❌ Не понял дату. Формат: 15.04 / 2030-04-15 / завтра / через 10 дней"

    today = date.today()
    raw = [t.lower().strip() for t in tokens]

    # завтра
    if raw == ["завтра"]:
        return today + timedelta(days=1)

    # через 10 дней
    if len(raw) == 3 and raw[0] == "через" and raw[2] in {"день", "дня", "дней"}:
        try:
            days = int(raw[1])
        except ValueError:
            return f"❌ Не понял дату: {' '.join(tokens)}."
        if days <= 0:
            return "❌ Интервал должен быть больше 0 дней."
        return today + timedelta(days=days)

    # в следующий вторник
    if len(raw) == 3 and raw[0] == "в" and raw[1] == "следующий" and raw[2] in _FUTURE_WEEKDAY:
        target = _FUTURE_WEEKDAY[raw[2]]
        days_ahead = (target - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return today + timedelta(days=days_ahead)

    # 2030-04-15
    if len(raw) == 1 and "-" in raw[0]:
        try:
            d = date.fromisoformat(raw[0])
        except Exception:
            return f"❌ Не понял дату: {' '.join(tokens)}. Формат: 15.04 или 2030-04-15"
        if d < today:
            return "❌ Дата уже прошла. Укажи будущую дату."
        return d

    # 15.04
    if len(raw) == 1 and "." in raw[0]:
        try:
            day_num, month_num = map(int, raw[0].split("."))
            d = date(today.year, month_num, day_num)
        except Exception:
            return f"❌ Не понял дату: {' '.join(tokens)}. Формат: 15.04 или 2030-04-15"
        if d < today:
            return "❌ Дата уже прошла. Укажи будущую дату."
        return d

    # 1 мая
    if len(raw) == 2 and raw[1] in _MONTH_NAMES:
        try:
            day_num = int(raw[0])
            month_num = _MONTH_NAMES[raw[1]]
            d = date(today.year, month_num, day_num)
        except Exception:
            return f"❌ Не понял дату: {' '.join(tokens)}."
        if d < today:
            return "❌ Дата уже прошла. Укажи будущую дату."
        return d

    return f"❌ Не понял дату: {' '.join(tokens)}. Формат: 15.04 / 2030-04-15 / завтра / через 10 дней"
