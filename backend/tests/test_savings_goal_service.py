from decimal import Decimal

import pytest
from app.models.savings_goal import SavingsGoal


def test_savings_goal_model_exists() -> None:
    goal = SavingsGoal(
        user_id=555,
        title="iPhone 14 Pro",
        target_amount=120000,
    )
    assert goal.title == "iPhone 14 Pro"
    assert goal.current_amount == 0
    assert goal.is_active is True
