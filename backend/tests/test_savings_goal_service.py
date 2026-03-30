from decimal import Decimal

import pytest
from app.models.savings_goal import SavingsGoal
from app.repositories.savings_goal_repository import SavingsGoalRepository


def test_savings_goal_model_exists() -> None:
    goal = SavingsGoal(
        user_id=555,
        title="iPhone 14 Pro",
        target_amount=120000,
    )
    assert goal.title == "iPhone 14 Pro"
    assert goal.current_amount == 0
    assert goal.is_active is True


def test_repository_create_and_list(db_session) -> None:
    repo = SavingsGoalRepository(db_session)
    goal = repo.create(user_id=555, title="iPhone 14 Pro", target_amount=Decimal("120000"))
    goals = repo.list_active(user_id=555)
    assert len(goals) == 1
    assert goals[0].title == "iPhone 14 Pro"
    assert goals[0].current_amount == Decimal("0")


def test_repository_fuzzy_match_exact(db_session) -> None:
    repo = SavingsGoalRepository(db_session)
    repo.create(user_id=555, title="Отпуск в Турции", target_amount=Decimal("80000"))
    goal, score = repo.fuzzy_match(user_id=555, query="отпуск")
    assert goal is not None
    assert score >= 0.8


def test_repository_fuzzy_match_no_goals(db_session) -> None:
    repo = SavingsGoalRepository(db_session)
    goal, score = repo.fuzzy_match(user_id=999, query="айфон")
    assert goal is None
    assert score == 0.0


def test_repository_complete_deactivates(db_session) -> None:
    repo = SavingsGoalRepository(db_session)
    goal = repo.create(user_id=555, title="Велосипед", target_amount=Decimal("30000"))
    repo.complete(goal)
    goals = repo.list_active(user_id=555)
    assert len(goals) == 0


# --- SavingsGoalService tests ---

from app.services.savings_goal_service import SavingsGoalService


def test_service_create_goal(db_session) -> None:
    service = SavingsGoalService(db_session)
    goal = service.create(
        user_id=555,
        title="MacBook Pro",
        target_amount=Decimal("200000"),
        auto_percent=15,
    )
    assert goal.title == "MacBook Pro"
    assert goal.auto_percent == 15
    assert goal.current_amount == Decimal("0")


def test_service_create_rejects_zero_amount(db_session) -> None:
    service = SavingsGoalService(db_session)
    with pytest.raises(ValueError, match="target_amount"):
        service.create(user_id=555, title="Тест", target_amount=Decimal("0"))


def test_service_deposit_increases_amount(db_session) -> None:
    service = SavingsGoalService(db_session)
    goal = service.create(user_id=555, title="Велосипед", target_amount=Decimal("30000"))
    updated, reached = service.deposit(user_id=555, goal_id=goal.id, amount=Decimal("5000"))
    assert updated.current_amount == Decimal("5000")
    assert reached is False


def test_service_deposit_returns_reached_when_complete(db_session) -> None:
    service = SavingsGoalService(db_session)
    goal = service.create(user_id=555, title="Велосипед", target_amount=Decimal("1000"))
    _, reached = service.deposit(user_id=555, goal_id=goal.id, amount=Decimal("1000"))
    assert reached is True


def test_service_list_active_returns_only_active(db_session) -> None:
    service = SavingsGoalService(db_session)
    g1 = service.create(user_id=555, title="Цель 1", target_amount=Decimal("10000"))
    g2 = service.create(user_id=555, title="Цель 2", target_amount=Decimal("20000"))
    service.complete(user_id=555, goal_id=g1.id)
    active = service.list_active(user_id=555)
    assert len(active) == 1
    assert active[0].id == g2.id


def test_service_forecast_on_track(db_session) -> None:
    from datetime import date, timedelta
    service = SavingsGoalService(db_session)
    deadline = date.today().replace(day=1) + timedelta(days=365)
    goal = service.create(
        user_id=555, title="Тест", target_amount=Decimal("12000"),
        deadline=deadline, auto_percent=10,
    )
    forecast = service.calculate_forecast(goal, user_id=555)
    assert forecast.remaining == Decimal("12000")
    assert forecast.months_to_deadline is not None
    assert forecast.months_to_deadline > 0


def test_service_process_income_distributes(db_session) -> None:
    service = SavingsGoalService(db_session)
    service.create(user_id=555, title="Цель А", target_amount=Decimal("50000"), auto_percent=10)
    service.create(user_id=555, title="Цель Б", target_amount=Decimal("30000"), auto_percent=5)
    results = service.process_income(user_id=555, income_amount=Decimal("10000"))
    assert len(results) == 2
    deposited = {r[0].title: r[1] for r in results}
    assert deposited["Цель А"] == Decimal("1000.00")
    assert deposited["Цель Б"] == Decimal("500.00")
