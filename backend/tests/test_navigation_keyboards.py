from app.services.recommendation_service import RecommendationItem, RecommendationSnapshot
from datetime import UTC, datetime

from app.telegram.keyboards import (
    ADVISOR_QUICK_SCENARIOS,
    advisor_action_rows,
    advisor_keyboard,
    advisor_onboarding_keyboard,
    advisor_session_keyboard,
    cancel_keyboard,
    done_keyboard,
)


def test_done_keyboard_menu_only():
    kb = done_keyboard()
    buttons = kb.inline_keyboard
    assert len(buttons) == 1
    assert len(buttons[0]) == 1
    assert buttons[0][0].text == "≡ Меню"
    assert buttons[0][0].callback_data == "nav:menu"


def test_done_keyboard_with_back():
    kb = done_keyboard(back_target="nav:categories")
    buttons = kb.inline_keyboard
    assert len(buttons) == 1
    assert len(buttons[0]) == 2
    assert buttons[0][0].text == "← Назад"
    assert buttons[0][0].callback_data == "nav:categories"
    assert buttons[0][1].text == "≡ Меню"
    assert buttons[0][1].callback_data == "nav:menu"


def test_advisor_keyboard():
    kb = advisor_keyboard()
    buttons = kb.inline_keyboard
    assert len(buttons) == 2
    assert buttons[0][0].text == "🧠 Продолжить в советнике"
    assert buttons[0][0].callback_data == "nav:advisor"
    assert buttons[1][0].text == "📊 Сводка"
    assert buttons[1][1].text == "≡ Меню"


def test_advisor_onboarding_keyboard_contains_quick_scenarios():
    kb = advisor_onboarding_keyboard()
    all_callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    for slug, _label in ADVISOR_QUICK_SCENARIOS:
        assert f"advisor:scenario:{slug}" in all_callbacks
    assert "nav:menu" in all_callbacks


def test_advisor_session_keyboard_contains_quick_followups():
    kb = advisor_session_keyboard()
    all_callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "advisor:scenario:budget_risks" in all_callbacks
    assert "advisor:scenario:upcoming" in all_callbacks
    assert "advisor:scenario:export" in all_callbacks
    assert "nav:advisor" in all_callbacks
    assert "nav:menu" in all_callbacks


def test_cancel_keyboard():
    kb = cancel_keyboard("nav:settings")
    buttons = kb.inline_keyboard
    assert len(buttons) == 1
    assert len(buttons[0]) == 1
    assert buttons[0][0].text == "❌ Отмена"
    assert buttons[0][0].callback_data == "nav:settings"


def test_advisor_action_rows_map_recommendations_to_real_navigation() -> None:
    recs = RecommendationSnapshot(
        primary=RecommendationItem(
            title="Срочно охлади категорию",
            detail="Уже потрачено 112%",
            score=0.9,
            action_type="cut_costs",
            category="еда",
        ),
        secondary=[
            RecommendationItem(
                title="Подготовь платёж",
                detail="Налог скоро",
                score=0.6,
                action_type="upcoming_payment",
            ),
            RecommendationItem(
                title="Смотри сводку",
                detail="Прогноз выше бюджета",
                score=0.55,
                action_type="forecast_control",
            ),
        ],
        generated_at=datetime.now(UTC),
        data_quality="full",
    )

    rows = advisor_action_rows(recs)
    assert rows[0][0].text == "💰 Открыть бюджеты"
    assert rows[0][0].callback_data == "nav:budgets"
    assert any(button.callback_data == "nav:planned" for row in rows for button in row)
