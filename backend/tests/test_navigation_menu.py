from datetime import date, timedelta

from app.services.nav_service import NavService
from app.services.planned_expense_service import PlannedExpenseService
from app.services.recurring_service import RecurringService
from app.telegram.keyboards import main_menu_inline_keyboard


def test_main_menu_has_product_sections() -> None:
    kb = main_menu_inline_keyboard()
    labels = [button.text for row in kb.inline_keyboard for button in row]

    assert "📊 Сводка" in labels
    assert "📋 Запланированные" in labels
    assert "🔄 Регулярные" in labels
    assert "💰 Бюджеты" in labels
    assert "⚙️ Настройки" in labels
    assert "ℹ️ Помощь" in labels


def test_nav_service_planned_screen_shows_items(db_session) -> None:
    PlannedExpenseService(db_session).create_manual(
        telegram_user_id=555,
        title="Маникюр",
        amount=2100,
        category="beauty",
        planned_date=date.today() + timedelta(days=2),
    )

    screen = NavService(db_session).planned_screen(555)

    assert "Маникюр" in screen.text
    assert "Запланирован" in screen.text or "Запланированное" in screen.text


def test_nav_service_recurring_screen_shows_rules(db_session) -> None:
    RecurringService(db_session).create(555, "Аренда", 45000, "expense", "housing", "monthly", 1)

    screen = NavService(db_session).recurring_screen(555)

    assert "Аренда" in screen.text
    assert "Регулярное" in screen.text or "Повторяющ" in screen.text


def test_nav_service_budgets_screen_works_without_budgets(db_session) -> None:
    from app.repositories.user_repository import UserRepository

    UserRepository(db_session).get_or_create(555, "User")
    db_session.commit()

    screen = NavService(db_session).budgets_screen(555)

    assert "бюджет" in screen.text.lower()
