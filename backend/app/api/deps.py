from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db


def get_telegram_user_id(x_telegram_user_id: int | None = Header(default=None)) -> int:
    if x_telegram_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Telegram-User-Id header",
        )
    return x_telegram_user_id


DBSession = Session
DBDependency = get_db
