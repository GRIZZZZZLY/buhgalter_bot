from pydantic import BaseModel


class BudgetItem(BaseModel):
    category: str
    limit: float
    spent: float
    pct: float  # 0–100+


class BudgetUpsertRequest(BaseModel):
    category: str
    amount: float


class BudgetResponse(BaseModel):
    items: list[BudgetItem]
    total_budget: float | None
    total_spent: float
    total_pct: float | None
