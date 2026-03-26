"""Navigation service — builds section content for the inline menu system."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session
from telegram import InlineKeyboardMarkup

from app.models.user import User
from app.services.analytics_service import AnalyticsService
from app.services.planned_expense_service import PlannedExpenseService
from app.services.recurring_service import RecurringService
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.user_category_mapping_repository import UserCategoryMappingRepository
from app.repositories.user_repository import UserRepository
from app.telegram.formatter import TreasuryFormatter
from app.services.category_service import CategoryService
from app.telegram.keyboards import (
    budgets_inline_keyboard,
    help_inline_keyboard,
    operations_delete_keyboard,
    operations_inline_keyboard,
    planned_inline_keyboard,
    recurring_inline_keyboard,
    settings_nav_inline_keyboard,
    stats_inline_keyboard,
)

logger = logging.getLogger("finance_bot.nav")
formatter = TreasuryFormatter()


@dataclass
class NavScreen:
    text: str
    keyboard: InlineKeyboardMarkup
    parse_mode: str = "Markdown"


class NavService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.tx_repo = TransactionRepository(db)
        self.user_repo = UserRepository(db)
        self.mapping_repo = UserCategoryMappingRepository(db)
        self.planned_service = PlannedExpenseService(db)
        self.recurring_service = RecurringService(db)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------
    def stats_screen(self, telegram_user_id: int, period: str = "month") -> NavScreen:
        summary = self.tx_repo.get_summary(telegram_user_id, period)
        text = formatter.format_stats_screen(
            income_total=f"{float(summary['income_total']):,.0f}",
            expense_total=f"{float(summary['expense_total']):,.0f}",
            balance=f"{float(summary['balance']):,.0f}",
            top_items=[
                {"category": i["category"], "amount": f"{float(i['amount']):,.0f}"}
                for i in summary["top_expense_categories"]
            ],
            period=period,
        )
        return NavScreen(text=text, keyboard=stats_inline_keyboard(period))

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------
    def operations_screen(self, telegram_user_id: int, period: str = "month") -> NavScreen:
        items = self.tx_repo.list_for_user(telegram_user_id, limit=10, offset=0, period=period)
        items_dicts = [
            {
                "id": str(tx.id),
                "type": tx.type.value,
                "amount": f"{float(tx.amount):,.0f}",
                "category": tx.category,
                "created_at": tx.created_at.isoformat() if tx.created_at else "",
            }
            for tx in items
        ]
        text = formatter.format_operations_screen(items_dicts, period)
        return NavScreen(text=text, keyboard=operations_inline_keyboard(period))

    def operations_delete_screen(self, telegram_user_id: int, period: str = "month") -> NavScreen:
        items = self.tx_repo.list_for_user(telegram_user_id, limit=5, offset=0, period=period)
        items_dicts = [
            {
                "id": str(tx.id),
                "type": tx.type.value,
                "amount": f"{float(tx.amount):,.0f}",
                "category": tx.category,
            }
            for tx in items
        ]
        if not items_dicts:
            return self.operations_screen(telegram_user_id, period)
        text = "🗑 Выбери запись для удаления:"
        return NavScreen(text=text, keyboard=operations_delete_keyboard(items_dicts, period))

    # ------------------------------------------------------------------
    # Planned / Recurring / Budgets
    # ------------------------------------------------------------------
    def planned_screen(self, telegram_user_id: int) -> NavScreen:
        from datetime import date

        items = self.planned_service.list_all(telegram_user_id, today=date.today())
        text = formatter.format_planned_list([
            {
                "title": item.title,
                "amount": item.amount,
                "category": item.category,
                "planned_date": item.planned_date,
                "is_overdue": item.planned_date < date.today().isoformat(),
            }
            for item in items
        ])
        return NavScreen(text=text, keyboard=planned_inline_keyboard(), parse_mode="HTML")

    def recurring_screen(self, telegram_user_id: int) -> NavScreen:
        items = self.recurring_service.list_active(telegram_user_id)
        text = self.recurring_service.format_list(items)
        return NavScreen(text=text, keyboard=recurring_inline_keyboard())

    def budgets_screen(self, telegram_user_id: int) -> NavScreen:
        user = self.user_repo.get_by_telegram_id(telegram_user_id)
        if user is None:
            return NavScreen(text="💰 Бюджеты\n\nПользователь не найден.", keyboard=budgets_inline_keyboard())
        text = AnalyticsService(self.db).build_budget_report(user)
        return NavScreen(text=text, keyboard=budgets_inline_keyboard())

    def categories_screen(self, telegram_user_id: int) -> NavScreen:
        """Type selector: choose expense or income."""
        CategoryService(self.db).ensure_seeded(telegram_user_id)
        from app.telegram.keyboards import categories_type_keyboard
        return NavScreen(text="🗂 *Категории*\n\nВыбери раздел:", keyboard=categories_type_keyboard())

    def categories_list_screen(
        self, telegram_user_id: int, cat_type: str, page: int
    ) -> NavScreen:
        """Paginated category list for expense or income."""
        from app.telegram.keyboards import categories_list_keyboard, CATEGORIES_PAGE_SIZE
        svc = CategoryService(self.db)
        svc.ensure_seeded(telegram_user_id)
        groups = svc.list_categories(telegram_user_id)

        # 'both' categories appear in both sections
        cats = groups.get(cat_type, []) + groups.get("both", [])
        total = len(cats)
        start = page * CATEGORIES_PAGE_SIZE
        page_cats = cats[start: start + CATEGORIES_PAGE_SIZE]

        type_label = "💸 Расходы" if cat_type == "expense" else "💰 Доходы"
        total_pages = max(1, (total + CATEGORIES_PAGE_SIZE - 1) // CATEGORIES_PAGE_SIZE)
        text = f"{type_label} _(стр. {page + 1}/{total_pages})_"

        return NavScreen(
            text=text,
            keyboard=categories_list_keyboard(page_cats, cat_type, page, total),
        )

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def settings_screen(self, telegram_user_id: int) -> NavScreen:
        user = self.user_repo.get_by_telegram_id(telegram_user_id)
        if user is None:
            return NavScreen(text="⚙️ Настройки", keyboard=settings_nav_inline_keyboard())
        text = formatter.format_settings_screen(user)
        return NavScreen(text=text, keyboard=settings_nav_inline_keyboard())

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------
    def help_screen(self) -> NavScreen:
        return NavScreen(text=formatter.format_help_screen(), keyboard=help_inline_keyboard())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_top_cats_for_type(self, telegram_user_id: int, tx_type: str) -> list[str]:
        from datetime import datetime, timezone
        from sqlalchemy import func, select
        from app.models.transaction import Transaction, TransactionType

        now = datetime.now(timezone.utc)
        from datetime import timedelta
        three_months_ago = now - timedelta(days=90)

        tx_type_enum = TransactionType.INCOME if tx_type == "income" else TransactionType.EXPENSE

        stmt = (
            select(Transaction.category)
            .where(
                Transaction.telegram_user_id == telegram_user_id,
                Transaction.type == tx_type_enum,
                Transaction.created_at >= three_months_ago,
            )
            .group_by(Transaction.category)
            .order_by(func.sum(Transaction.amount).desc())
            .limit(8)
        )
        return list(self.db.scalars(stmt).all())
