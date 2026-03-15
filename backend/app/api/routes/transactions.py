from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_telegram_user_id
from app.schemas.transaction import TransactionItem, TransactionListResponse, TransactionUpdateRequest
from app.services.transaction_service import TransactionService

router = APIRouter()


@router.get("/transactions", response_model=TransactionListResponse)
def list_transactions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    period: str = Query(default="month", pattern="^(today|week|month|all)$"),
    telegram_user_id: Annotated[int, Depends(get_telegram_user_id)] = 0,
    db: Annotated[Session, Depends(get_db)] = None,
) -> TransactionListResponse:
    service = TransactionService(db)
    items = service.list_transactions(telegram_user_id=telegram_user_id, limit=limit, offset=offset, period=period)
    return TransactionListResponse(items=items, limit=limit, offset=offset, period=period)


@router.put("/transactions/{transaction_id}", response_model=TransactionItem)
def update_transaction(
    transaction_id: UUID,
    payload: TransactionUpdateRequest,
    telegram_user_id: Annotated[int, Depends(get_telegram_user_id)] = 0,
    db: Annotated[Session, Depends(get_db)] = None,
) -> TransactionItem:
    service = TransactionService(db)
    updated = service.update_transaction(telegram_user_id=telegram_user_id, transaction_id=transaction_id, payload=payload)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return updated


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: UUID,
    telegram_user_id: Annotated[int, Depends(get_telegram_user_id)] = 0,
    db: Annotated[Session, Depends(get_db)] = None,
) -> Response:
    service = TransactionService(db)
    deleted = service.delete_transaction(telegram_user_id=telegram_user_id, transaction_id=transaction_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
