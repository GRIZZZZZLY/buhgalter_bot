from pydantic import BaseModel


class CategoryTotal(BaseModel):
    category: str
    amount: str


class SummaryResponse(BaseModel):
    period: str
    balance: str
    income_total: str
    expense_total: str
    top_expense_categories: list[CategoryTotal]


class SummaryMetrics(BaseModel):
    balance: str
    income_total: str
    expense_total: str
    top_expense_categories: list[CategoryTotal]
