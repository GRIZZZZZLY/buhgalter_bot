from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_telegram_user_id
from app.repositories.category_budget_repository import CategoryBudgetRepository
from app.repositories.user_repository import UserRepository
from app.schemas.budget import BudgetItem, BudgetResponse, BudgetUpsertRequest
from app.services.analytics_service import AnalyticsService

router = APIRouter()


@router.get("/budgets", response_model=BudgetResponse)
def get_budgets(
    telegram_user_id: Annotated[int, Depends(get_telegram_user_id)] = 0,
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
) -> BudgetResponse:
    budget_repo = CategoryBudgetRepository(db)
    user_repo = UserRepository(db)
    analytics = AnalyticsService(db)

    budgets = budget_repo.get_all_for_user(telegram_user_id)
    category_spending = analytics._get_category_spending_this_month(telegram_user_id)

    items: list[BudgetItem] = []
    for b in budgets:
        spent = float(category_spending.get(b.category, 0))
        limit = float(b.amount)
        pct = (spent / limit * 100) if limit > 0 else 0
        items.append(BudgetItem(category=b.category, limit=limit, spent=spent, pct=round(pct, 1)))

    user = user_repo.get_by_telegram_id(telegram_user_id)
    total_budget = float(user.budget_amount) if user and user.budget_amount else None
    total_spent = sum(float(category_spending.get(b.category, 0)) for b in budgets)
    total_pct = (total_spent / total_budget * 100) if total_budget else None

    return BudgetResponse(
        items=items,
        total_budget=total_budget,
        total_spent=round(total_spent, 2),
        total_pct=round(total_pct, 1) if total_pct is not None else None,
    )


@router.put("/budgets", response_model=BudgetItem)
def upsert_budget(
    payload: BudgetUpsertRequest,
    telegram_user_id: Annotated[int, Depends(get_telegram_user_id)] = 0,
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
) -> BudgetItem:
    if payload.amount < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Amount must be >= 0")

    budget_repo = CategoryBudgetRepository(db)
    analytics = AnalyticsService(db)

    if payload.amount == 0:
        budget_repo.remove(telegram_user_id, payload.category)
        db.commit()
        return BudgetItem(category=payload.category, limit=0, spent=0, pct=0)

    budget_repo.upsert(telegram_user_id, payload.category, payload.amount)
    db.commit()

    category_spending = analytics._get_category_spending_this_month(telegram_user_id)
    spent = float(category_spending.get(payload.category, 0))
    pct = (spent / payload.amount * 100) if payload.amount > 0 else 0
    return BudgetItem(category=payload.category, limit=payload.amount, spent=spent, pct=round(pct, 1))
