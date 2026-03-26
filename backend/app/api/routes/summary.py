from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_telegram_user_id
from app.schemas.summary import SummaryResponse
from app.services.transaction_service import TransactionService

router = APIRouter()


@router.get("/summary", response_model=SummaryResponse)
def get_summary(
    period: str = Query(default="month", pattern="^(today|week|month|all)$"),
    telegram_user_id: Annotated[int, Depends(get_telegram_user_id)] = 0,
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
) -> SummaryResponse:
    service = TransactionService(db)
    summary = service.get_summary(telegram_user_id=telegram_user_id, period=period)
    return SummaryResponse(period=period, **summary.model_dump())
