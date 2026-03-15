from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.voice_log import VoiceLog, VoiceLogStatus


class VoiceLogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_pending(
        self,
        telegram_user_id: int,
        telegram_message_id: int | None,
        file_id: str | None,
        original_text: str,
        transcript_text: str | None,
        parser_confidence: float | None,
        parser_status: str | None,
        status: VoiceLogStatus,
        failure_reason: str | None = None,
    ) -> VoiceLog:
        item = VoiceLog(
            telegram_user_id=telegram_user_id,
            telegram_message_id=telegram_message_id,
            file_id=file_id,
            original_text=original_text,
            transcript_text=transcript_text,
            parser_confidence=parser_confidence,
            parser_status=parser_status,
            status=status,
            failure_reason=failure_reason,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def get(self, voice_log_id: UUID) -> VoiceLog | None:
        stmt = select(VoiceLog).where(VoiceLog.id == voice_log_id)
        return self.db.scalar(stmt)

    def get_edit_pending_for_user(self, telegram_user_id: int) -> VoiceLog | None:
        stmt = (
            select(VoiceLog)
            .where(
                VoiceLog.telegram_user_id == telegram_user_id,
                VoiceLog.status == VoiceLogStatus.PENDING,
                VoiceLog.parser_status == "edit_pending",
            )
            .order_by(VoiceLog.updated_at.desc())
        )
        return self.db.scalar(stmt)

    def update_status(self, voice_log_id: UUID, status: VoiceLogStatus) -> VoiceLog | None:
        item = self.get(voice_log_id)
        if item is None:
            return None
        item.status = status
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def mark_edit_pending(self, voice_log_id: UUID) -> VoiceLog | None:
        item = self.get(voice_log_id)
        if item is None:
            return None
        item.parser_status = "edit_pending"
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_transcript(self, voice_log_id: UUID, transcript_text: str, parser_status: str = "edited") -> VoiceLog | None:
        item = self.get(voice_log_id)
        if item is None:
            return None
        item.transcript_text = transcript_text
        item.parser_status = parser_status
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item
