from fastapi import APIRouter

from app.api.routes import budget, chart, summary, transactions, user

api_router = APIRouter(prefix="/api")
api_router.include_router(summary.router, tags=["summary"])
api_router.include_router(transactions.router, tags=["transactions"])
api_router.include_router(budget.router, tags=["budget"])
api_router.include_router(chart.router, tags=["chart"])
api_router.include_router(user.router, tags=["user"])
