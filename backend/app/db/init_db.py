from app.db.base import Base
from app.db.session import engine
from app.models.transaction import Transaction  # noqa: F401
from app.models.voice_log import VoiceLog  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
