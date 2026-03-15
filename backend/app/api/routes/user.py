from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_telegram_user_id
from app.services.transaction_service import TransactionService

router = APIRouter()


@router.delete("/user/data", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_data(
    telegram_user_id: Annotated[int, Depends(get_telegram_user_id)] = 0,
    db: Annotated[Session, Depends(get_db)] = None,
) -> Response:
    service = TransactionService(db)
    service.delete_all_for_user(telegram_user_id=telegram_user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
