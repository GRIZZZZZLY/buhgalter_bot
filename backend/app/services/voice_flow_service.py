from uuid import UUID

from sqlalchemy.orm import Session

from app.models.voice_log import VoiceLogStatus
from app.repositories.voice_log_repository import VoiceLogRepository
from app.schemas.voice import VoiceConfirmationResult
from app.services.parser_service import ParserService
from app.services.transaction_service import TransactionService
from app.services.stt_service import STTService
from app.services.transcript_postprocessor import TranscriptPostprocessor
from app.telegram.formatter import TreasuryFormatter


class VoiceFlowService:
    def __init__(self, db: Session, parser_service: ParserService | None = None, stt_service: STTService | None = None) -> None:
        self.db = db
        self.parser_service = parser_service or ParserService()
        self.stt_service = stt_service or STTService()
        self.voice_logs = VoiceLogRepository(db)
        self.transactions = TransactionService(db)
        self.postprocessor = TranscriptPostprocessor()
        self.formatter = TreasuryFormatter()

    def process_voice(
        self,
        telegram_user_id: int,
        telegram_message_id: int | None,
        file_id: str | None,
        original_text: str,
        wav_path: str,
    ) -> VoiceConfirmationResult:
        stt_result = self.stt_service.transcribe(wav_path)
        if stt_result.needs_fallback or not stt_result.text:
            log = self.voice_logs.create_pending(
                telegram_user_id=telegram_user_id,
                telegram_message_id=telegram_message_id,
                file_id=file_id,
                original_text=original_text,
                transcript_text=stt_result.text,
                parser_confidence=None,
                parser_status=None,
                status=VoiceLogStatus.FAILED,
                failure_reason=stt_result.failure_reason or "stt failed",
            )
            return VoiceConfirmationResult(
                action="voice_fallback",
                voice_log_id=log.id,
                transcript=stt_result.text,
                message="Не удалось распознать голосовое. Попробуй текстом.",
            )

        normalized_transcript = self.postprocessor.normalize(stt_result.text)
        multi = self.parser_service.parse_many(normalized_transcript)
        if not multi.has_items:
            log = self.voice_logs.create_pending(
                telegram_user_id=telegram_user_id,
                telegram_message_id=telegram_message_id,
                file_id=file_id,
                original_text=original_text,
                transcript_text=normalized_transcript,
                parser_confidence=0.0,
                parser_status="fallback",
                status=VoiceLogStatus.FAILED,
                failure_reason="parser fallback",
            )
            return VoiceConfirmationResult(
                action="voice_fallback",
                voice_log_id=log.id,
                transcript=normalized_transcript,
                message="Не удалось распознать. Попробуй текстом.",
            )

        log = self.voice_logs.create_pending(
            telegram_user_id=telegram_user_id,
            telegram_message_id=telegram_message_id,
            file_id=file_id,
            original_text=original_text,
            transcript_text=normalized_transcript,
            parser_confidence=max(item.confidence for item in multi.items),
            parser_status="multi" if len(multi.items) > 1 else multi.items[0].confidence_label,
            status=VoiceLogStatus.PENDING,
        )
        if len(multi.items) == 1 and multi.items[0].confidence_label == 'medium':
            parsed = multi.items[0]
            raw_category = self.parser_service.normalize_category_candidate((parsed.description or '').strip())
            suggestions = self.parser_service.suggest_categories(raw_category)
            return VoiceConfirmationResult(
                action='clarify_category_choice',
                voice_log_id=log.id,
                transcript=normalized_transcript,
                message=self.formatter.format_category_resolution_prompt(raw_category, suggestions, self.parser_service.detect_merchant_label(raw_category)),
                parsed_items=[self._item_preview(parsed)],
                raw_category=raw_category,
                suggestions=suggestions,
                parsed_result=parsed,
            )

        parsed_items = [self._item_preview(item) for item in multi.items]
        message = (
            self.formatter.format_voice_confirm_many(parsed_items)
            if len(parsed_items) > 1
            else self.formatter.format_voice_confirm(normalized_transcript)
        )
        return VoiceConfirmationResult(
            action="confirm_voice",
            voice_log_id=log.id,
            transcript=normalized_transcript,
            message=message,
            parsed_items=parsed_items,
        )

    def start_edit_voice(self, voice_log_id: UUID) -> VoiceConfirmationResult:
        log = self.voice_logs.mark_edit_pending(voice_log_id)
        if log is None or not log.transcript_text:
            return VoiceConfirmationResult(action="voice_fallback", message="Не нашёл голосовую сессию для правки.")
        return VoiceConfirmationResult(
            action="voice_edit_required",
            voice_log_id=voice_log_id,
            transcript=log.transcript_text,
            message=self.formatter.format_voice_edit_prompt(log.transcript_text),
        )

    def apply_voice_edit(self, telegram_user_id: int, edited_text: str) -> VoiceConfirmationResult | None:
        log = self.voice_logs.get_edit_pending_for_user(telegram_user_id)
        if log is None:
            return None

        normalized = self.postprocessor.normalize(edited_text)
        multi = self.parser_service.parse_many(normalized)
        if not multi.has_items:
            self.voice_logs.update_transcript(log.id, normalized, parser_status="edited_failed")
            return VoiceConfirmationResult(
                action="voice_edit_required",
                voice_log_id=log.id,
                transcript=normalized,
                message=f"Не смог разобрать исправленный текст: {normalized}. Попробуй ещё раз.",
            )

        self.voice_logs.update_transcript(log.id, normalized, parser_status="edited")
        parsed_items = [self._item_preview(item) for item in multi.items]
        message = (
            self.formatter.format_voice_confirm_many(parsed_items)
            if len(parsed_items) > 1
            else self.formatter.format_voice_confirm(normalized)
        )
        return VoiceConfirmationResult(
            action="confirm_voice",
            voice_log_id=log.id,
            transcript=normalized,
            message=message,
            parsed_items=parsed_items,
        )

    def confirm_voice(self, voice_log_id: UUID) -> VoiceConfirmationResult:
        log = self.voice_logs.get(voice_log_id)
        if log is None or not log.transcript_text:
            return VoiceConfirmationResult(action="voice_fallback", message="Не нашёл голосовую сессию. Отправь голос ещё раз.")

        multi = self.parser_service.parse_many(log.transcript_text)
        if not multi.has_items:
            self.voice_logs.update_status(voice_log_id, VoiceLogStatus.FAILED)
            return VoiceConfirmationResult(
                action="voice_edit_required",
                voice_log_id=voice_log_id,
                transcript=log.transcript_text,
                message=f"Не смог уверенно выделить записи из: {log.transcript_text}. Пришли текстом, и я запишу.",
            )

        saved_items: list[dict[str, str]] = []
        for parsed in multi.items:
            if parsed.amount is None:
                continue
            if parsed.transaction_type is None:
                parsed.transaction_type = "expense"
            if parsed.category is None:
                parsed.category = "other"
            self.transactions.create_from_parse(telegram_user_id=log.telegram_user_id, source="voice", parsed=parsed)
            saved_items.append(self._item_preview(parsed))

        if not saved_items:
            self.voice_logs.update_status(voice_log_id, VoiceLogStatus.FAILED)
            return VoiceConfirmationResult(
                action="voice_edit_required",
                voice_log_id=voice_log_id,
                transcript=log.transcript_text,
                message=f"Не смог уверенно выделить записи из: {log.transcript_text}. Пришли текстом, и я запишу.",
            )

        self.voice_logs.update_status(voice_log_id, VoiceLogStatus.CONFIRMED)
        summary = self.transactions.get_summary(telegram_user_id=log.telegram_user_id, period="month")
        balance = summary.balance if summary.balance.startswith("-") else f"+{summary.balance}"

        if len(saved_items) == 1:
            item = saved_items[0]
            transcript_suffix = log.transcript_text if (item["category"] == "other") else None
            return VoiceConfirmationResult(
                action="voice_confirmed",
                voice_log_id=voice_log_id,
                transcript=log.transcript_text,
                message=self.formatter.format_voice_saved(item["type"], item["amount"], item["category"], balance, transcript_suffix),
                parsed_items=saved_items,
            )

        return VoiceConfirmationResult(
            action="voice_confirmed",
            voice_log_id=voice_log_id,
            transcript=log.transcript_text,
            message=self.formatter.format_saved_many(saved_items, balance),
            parsed_items=saved_items,
        )

    def cancel_voice(self, voice_log_id: UUID) -> VoiceConfirmationResult:
        updated = self.voice_logs.update_status(voice_log_id, VoiceLogStatus.CANCELLED)
        if updated is None:
            return VoiceConfirmationResult(action="voice_fallback", message="Не нашёл голосовую сессию. Нечего отменять.")
        return VoiceConfirmationResult(action="voice_cancelled", voice_log_id=voice_log_id, message="Окей, не записываю.")

    @staticmethod
    def _item_preview(parsed) -> dict[str, str]:
        tx_type = parsed.transaction_type or "expense"
        category = parsed.category or "other"
        amount = f"{parsed.amount:.2f}" if parsed.amount is not None else "0.00"
        return {
            "type": "доход" if tx_type == "income" else "расход",
            "amount": amount,
            "category": category,
        }
