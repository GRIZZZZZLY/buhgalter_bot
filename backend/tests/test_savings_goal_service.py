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
