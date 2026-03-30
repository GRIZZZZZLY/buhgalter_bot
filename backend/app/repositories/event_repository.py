"""
event_repository.py — запись событий аналитики.

Основной публичный интерфейс — функция log_event(), которая открывает
собственную сессию и никогда не поднимает исключений наружу.
Handlers просто вызывают log_event(...) без try/except.
"""
import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.event import Event

logger = logging.getLogger("finance_bot.events")


class EventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        user_id: int,
        event_type: str,
        source: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Event:
        event = Event(
            user_id=user_id,
            event_type=event_type,
            source=source,
            meta=json.dumps(meta, ensure_ascii=False) if meta else None,
        )
        self.db.add(event)
        self.db.commit()
        return event


def log_event(
    user_id: int,
    event_type: str,
    source: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Fire-and-forget запись события. Никогда не бросает исключений."""
    try:
        with SessionLocal() as db:
            EventRepository(db).create(
                user_id=user_id,
                event_type=event_type,
                source=source,
                meta=meta,
            )
    except Exception:
        logger.debug("event log failed: user=%s type=%s", user_id, event_type, exc_info=True)
