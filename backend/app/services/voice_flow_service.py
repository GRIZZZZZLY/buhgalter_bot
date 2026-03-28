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
from app.services.llm_service import (
    LLMService, LLMParsedItem, LLMTransactionResult,
    LLMPlannedResult, LLMRecurringResult, LLMUnavailableError,
)


class VoiceFlowService:
    def __init__(
        self,
        db: Session,
        parser_service: ParserService | None = None,
        stt_service: STTService | None = None,
    ) -> None:
        self.db = db
        self.parser_service = parser_service or ParserService()
        self.stt_service = stt_service or STTService()
        self.voice_logs = VoiceLogRepository(db)
        self.transactions = TransactionService(db)
        self.postprocessor = TranscriptPostprocessor()
        self.formatter = TreasuryFormatter()
        self.llm_service = LLMService(db)

    def _llm_call(self, text: str, telegram_user_id: int):
        """Call LLM and return full result, or None on failure."""
        try:
            return self.llm_service.process(text, telegram_user_id)
        except LLMUnavailableError:
            return None

    def _llm_parse(self, text: str, telegram_user_id: int) -> list[LLMParsedItem] | None:
        """Call LLM and return transaction items only, or None on non-transaction result."""
        result = self._llm_call(text, telegram_user_id)
        if not isinstance(result, LLMTransactionResult):
            return None
        return result.items

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
        llm_result = self._llm_call(normalized_transcript, telegram_user_id)

        if llm_result is None:
            log = self.voice_logs.create_pending(
                telegram_user_id=telegram_user_id,
                telegram_message_id=telegram_message_id,
                file_id=file_id,
                original_text=original_text,
                transcript_text=normalized_transcript,
                parser_confidence=0.0,
                parser_status="fallback",
                status=VoiceLogStatus.FAILED,
                failure_reason="llm unavailable or no items",
            )
            return VoiceConfirmationResult(
                action="voice_fallback",
                voice_log_id=log.id,
                transcript=normalized_transcript,
                message="Не удалось распознать. Попробуй текстом.",
            )

        # --- planned / recurring intents ---
        if isinstance(llm_result, LLMPlannedResult):
            log = self.voice_logs.create_pending(
                telegram_user_id=telegram_user_id,
                telegram_message_id=telegram_message_id,
                file_id=file_id,
                original_text=original_text,
                transcript_text=normalized_transcript,
                parser_confidence=0.95,
                parser_status="planned",
                status=VoiceLogStatus.PENDING,
            )
            return VoiceConfirmationResult(
                action="planned_confirm",
                voice_log_id=log.id,
                transcript=normalized_transcript,
                message="",
                parsed_items=[{
                    "title": llm_result.title,
                    "amount": str(llm_result.amount),
                    "category": llm_result.category,
                    "planned_date": llm_result.planned_date.isoformat() if llm_result.planned_date else "",
                    "reminder_time": llm_result.reminder_time or "",
                }],
            )

        if isinstance(llm_result, LLMRecurringResult):
            log = self.voice_logs.create_pending(
                telegram_user_id=telegram_user_id,
                telegram_message_id=telegram_message_id,
                file_id=file_id,
                original_text=original_text,
                transcript_text=normalized_transcript,
                parser_confidence=0.95,
                parser_status="recurring",
                status=VoiceLogStatus.PENDING,
            )
            return VoiceConfirmationResult(
                action="recurring_confirm",
                voice_log_id=log.id,
                transcript=normalized_transcript,
                message="",
                parsed_items=[{
                    "title": llm_result.title,
                    "amount": str(llm_result.amount),
                    "category": llm_result.category,
                    "transaction_type": llm_result.transaction_type,
                    "frequency": llm_result.frequency,
                    "day_value": str(llm_result.day_value),
                }],
            )

        # --- transaction intent ---
        if not isinstance(llm_result, LLMTransactionResult) or not llm_result.items:
            log = self.voice_logs.create_pending(
                telegram_user_id=telegram_user_id,
                telegram_message_id=telegram_message_id,
                file_id=file_id,
                original_text=original_text,
                transcript_text=normalized_transcript,
                parser_confidence=0.0,
                parser_status="fallback",
                status=VoiceLogStatus.FAILED,
                failure_reason="no transaction items",
            )
            return VoiceConfirmationResult(
                action="voice_fallback",
                voice_log_id=log.id,
                transcript=normalized_transcript,
                message="Не удалось распознать. Попробуй текстом.",
            )

        parsed_results = [item.parsed for item in llm_result.items]

        log = self.voice_logs.create_pending(
            telegram_user_id=telegram_user_id,
            telegram_message_id=telegram_message_id,
            file_id=file_id,
            original_text=original_text,
            transcript_text=normalized_transcript,
            parser_confidence=0.95,
            parser_status="multi" if len(parsed_results) > 1 else "high",
            status=VoiceLogStatus.PENDING,
        )

        parsed_items = [self._item_preview(p) for p in parsed_results]
        if len(parsed_items) == 1:
            item = parsed_items[0]
            message = self.formatter.format_voice_confirm(
                tx_type=item["type"],
                amount=item["amount"],
                category=item["category"],
                transcript=normalized_transcript,
            )
        else:
            message = self.formatter.format_voice_confirm_many(parsed_items, transcript=normalized_transcript)

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
            return VoiceConfirmationResult(
                action="voice_fallback",
                message="Не нашёл голосовую сессию для правки.",
            )
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
        llm_result = self._llm_call(normalized, log.telegram_user_id)

        if isinstance(llm_result, LLMPlannedResult):
            self.voice_logs.update_transcript(log.id, normalized, parser_status="edited_planned")
            return VoiceConfirmationResult(
                action="planned_confirm",
                voice_log_id=log.id,
                transcript=normalized,
                message="",
                parsed_items=[{
                    "title": llm_result.title,
                    "amount": str(llm_result.amount),
                    "category": llm_result.category,
                    "planned_date": llm_result.planned_date.isoformat() if llm_result.planned_date else "",
                    "reminder_time": llm_result.reminder_time or "",
                }],
            )

        if isinstance(llm_result, LLMRecurringResult):
            self.voice_logs.update_transcript(log.id, normalized, parser_status="edited_recurring")
            return VoiceConfirmationResult(
                action="recurring_confirm",
                voice_log_id=log.id,
                transcript=normalized,
                message="",
                parsed_items=[{
                    "title": llm_result.title,
                    "amount": str(llm_result.amount),
                    "category": llm_result.category,
                    "transaction_type": llm_result.transaction_type,
                    "frequency": llm_result.frequency,
                    "day_value": str(llm_result.day_value),
                }],
            )

        if not isinstance(llm_result, LLMTransactionResult) or not llm_result.items:
            self.voice_logs.update_transcript(log.id, normalized, parser_status="edited_failed")
            return VoiceConfirmationResult(
                action="voice_edit_required",
                voice_log_id=log.id,
                transcript=normalized,
                message=f"Не смог разобрать: {normalized}. Попробуй ещё раз.",
            )

        self.voice_logs.update_transcript(log.id, normalized, parser_status="edited")
        parsed_items = [self._item_preview(item.parsed) for item in llm_result.items]
        if len(parsed_items) == 1:
            item = parsed_items[0]
            message = self.formatter.format_voice_confirm(
                tx_type=item["type"],
                amount=item["amount"],
                category=item["category"],
                transcript=normalized,
            )
        else:
            message = self.formatter.format_voice_confirm_many(parsed_items, transcript=normalized)

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
            return VoiceConfirmationResult(
                action="voice_fallback",
                message="Не нашёл голосовую сессию. Отправь голос ещё раз.",
            )

        llm_items = self._llm_parse(log.transcript_text, log.telegram_user_id)
        if not llm_items:
            self.voice_logs.update_status(voice_log_id, VoiceLogStatus.FAILED)
            return VoiceConfirmationResult(
                action="voice_edit_required",
                voice_log_id=voice_log_id,
                transcript=log.transcript_text,
                message=f"Не смог выделить записи из: {log.transcript_text}. Пришли текстом.",
            )

        saved_items: list[dict[str, str]] = []
        saved_tx_ids: list[str] = []
        for llm_item in llm_items:
            parsed = llm_item.parsed
            if parsed.amount is None:
                continue
            if parsed.transaction_type is None:
                parsed.transaction_type = "expense"
            if parsed.category is None:
                parsed.category = "other"
            tx = self.transactions.create_from_parse(
                telegram_user_id=log.telegram_user_id,
                source="voice",
                parsed=parsed,
                override_date=llm_item.override_date,
            )
            saved_tx_ids.append(str(tx.id))
            saved_items.append(self._item_preview(parsed))

        if not saved_items:
            self.voice_logs.update_status(voice_log_id, VoiceLogStatus.FAILED)
            return VoiceConfirmationResult(
                action="voice_edit_required",
                voice_log_id=voice_log_id,
                transcript=log.transcript_text,
                message=f"Не смог выделить записи из: {log.transcript_text}. Пришли текстом.",
            )

        self.voice_logs.update_status(voice_log_id, VoiceLogStatus.CONFIRMED)
        summary = self.transactions.get_summary(
            telegram_user_id=log.telegram_user_id, period="month"
        )
        balance = summary.balance if summary.balance.startswith("-") else f"+{summary.balance}"

        if len(saved_items) == 1:
            item = saved_items[0]
            return VoiceConfirmationResult(
                action="voice_confirmed",
                voice_log_id=voice_log_id,
                transcript=log.transcript_text,
                message=self.formatter.format_voice_saved(
                    item["type"], item["amount"], item["category"], balance
                ),
                parsed_items=saved_items,
                saved_transaction_ids=saved_tx_ids,
            )

        return VoiceConfirmationResult(
            action="voice_confirmed",
            voice_log_id=voice_log_id,
            transcript=log.transcript_text,
            message=self.formatter.format_saved_many(saved_items, balance),
            parsed_items=saved_items,
            saved_transaction_ids=saved_tx_ids,
        )

    def cancel_voice(self, voice_log_id: UUID) -> VoiceConfirmationResult:
        updated = self.voice_logs.update_status(voice_log_id, VoiceLogStatus.CANCELLED)
        if updated is None:
            return VoiceConfirmationResult(
                action="voice_fallback",
                message="Не нашёл голосовую сессию. Нечего отменять.",
            )
        return VoiceConfirmationResult(
            action="voice_cancelled",
            voice_log_id=voice_log_id,
            message="Запись отменена.",
        )

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
