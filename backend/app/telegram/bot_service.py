from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.telegram import TelegramVoicePayload
from app.services.audio_file_service import AudioFileService
from app.services.transaction_service import TransactionService
from app.services.yaml_learner_service import YamlLearnerService
from app.telegram.formatter import TreasuryFormatter
from app.telegram.handlers import TelegramTextFlow

_KEYWORD_STOPLIST = {
    "оплата", "перевод", "платёж", "платеж", "покупка",
    "списание", "зачисление", "банк", "карта", "счёт", "счет",
    "услуг", "услуга", "услуги", "сумма", "итого", "руб", "рублей",
}


def _extract_keyword(description: str) -> str | None:
    for token in description.lower().split():
        token = token.strip(".,!?;:()")
        if len(token) >= 3 and token not in _KEYWORD_STOPLIST:
            return token
    return None


@dataclass(slots=True)
class VoiceProcessingDebug:
    ogg_path: str
    wav_path: str | None
    converted: bool


class TelegramBotService:
    def __init__(self, db: Session, flow: TelegramTextFlow | None = None, audio_service: AudioFileService | None = None) -> None:
        self.db = db
        self.flow = flow or TelegramTextFlow(db)
        self.audio_service = audio_service or AudioFileService()
        self.transaction_service = TransactionService(db)
        self.formatter = TreasuryFormatter()

    def process_text_message(self, telegram_user_id: int, text: str) -> dict[str, str]:
        return self.flow.handle_text(telegram_user_id=telegram_user_id, text=text)

    def process_summary_command(self, telegram_user_id: int, period: str = "month") -> dict[str, str]:
        return self.flow.handle_summary(telegram_user_id=telegram_user_id, period=period)

    def process_delete_command(self, telegram_user_id: int) -> dict:
        items = self.transaction_service.list_recent_for_delete(telegram_user_id=telegram_user_id, limit=5)
        if not items:
            return {"action": "delete_empty", "message": self.formatter.format_delete_empty()}
        return {"action": "delete_select", "message": self.formatter.format_delete_prompt(), "items": items}

    def delete_transaction(self, telegram_user_id: int, transaction_id: str) -> dict[str, str]:
        deleted = self.transaction_service.delete_transaction(telegram_user_id=telegram_user_id, transaction_id=UUID(transaction_id))
        if not deleted:
            return {"action": "delete_missing", "message": self.formatter.format_delete_missing()}
        return {"action": "delete_done", "message": self.formatter.format_delete_done()}

    def process_delete_all_command(self, telegram_user_id: int) -> dict[str, str]:
        return {
            "action": "deleteall_confirm",
            "message": self.formatter.format_deleteall_confirm(),
        }

    def delete_all_transactions(self, telegram_user_id: int) -> dict[str, str]:
        deleted_count = self.transaction_service.delete_all_for_user(telegram_user_id=telegram_user_id)
        return {
            "action": "deleteall_done",
            "message": self.formatter.format_deleteall_done(deleted_count),
        }

    def process_voice_message(self, payload: TelegramVoicePayload) -> tuple[dict, VoiceProcessingDebug]:
        ogg_path = self.audio_service.temp_copy(payload.original_file_path, ".ogg")
        wav_path = None
        converted = False
        try:
            wav_path = self.audio_service.prepare_wav_from_ogg(ogg_path, suffix=Path(ogg_path).stem)
            converted = True
            response = self.flow.handle_voice(
                telegram_user_id=payload.telegram_user_id,
                telegram_message_id=payload.telegram_message_id,
                file_id=payload.file_id,
                original_text=payload.original_text,
                wav_path=wav_path,
            )
            return response, VoiceProcessingDebug(ogg_path=ogg_path, wav_path=wav_path, converted=converted)
        except Exception as exc:
            return {
                "action": "voice_fallback",
                "message": f"Не смог обработать голосовое локально: {exc}",
            }, VoiceProcessingDebug(ogg_path=ogg_path, wav_path=wav_path, converted=converted)
        finally:
            # Always clean up temporary audio files regardless of success or failure
            self.audio_service.cleanup_audio_files(ogg_path, wav_path or "")

    def start_voice_edit(self, voice_log_id: str) -> dict[str, str]:
        return self.flow.start_voice_edit(voice_log_id)

    def confirm_voice(self, voice_log_id: str) -> dict[str, str]:
        return self.flow.confirm_voice(voice_log_id)

    def cancel_voice(self, voice_log_id: str) -> dict[str, str]:
        return self.flow.cancel_voice(voice_log_id)

    def handle_category_correction(
        self, telegram_user_id: int, transaction_id: str, new_category: str
    ) -> dict:
        tx = self.transaction_service.update_category(
            telegram_user_id, transaction_id, new_category
        )
        if tx is None:
            return {"message": "Транзакция не найдена."}
        if tx.description:
            keyword = _extract_keyword(tx.description)
            if keyword:
                YamlLearnerService().add_synonym(new_category, keyword)
        return {"message": f"✅ Категория изменена на <b>{new_category}</b>"}

    def improve_categories(self, telegram_user_id: int) -> list[dict]:
        import uuid
        from app.services.category_suggestion_service import CategorySuggestionService, AddSynonymSuggestion

        service = CategorySuggestionService(self.db)
        suggestions = service.get_suggestions(telegram_user_id)

        results = []
        for sugg in suggestions:
            key = f"sugg:{uuid.uuid4().hex[:8]}"
            if isinstance(sugg, AddSynonymSuggestion):
                text = f"Добавить <b>'{sugg.synonym}'</b> как синоним категории <i>{sugg.category_slug}</i>?"
            else:
                syns = ", ".join(sugg.synonyms)
                text = f"Создать новую категорию <b>'{sugg.slug}'</b> ({syns})?"
            results.append({"text": text, "key": key, "suggestion": sugg})
        return results

    def apply_suggestion(self, suggestion) -> bool:
        from app.services.category_suggestion_service import AddSynonymSuggestion
        svc = YamlLearnerService()
        if isinstance(suggestion, AddSynonymSuggestion):
            return svc.add_synonym(suggestion.category_slug, suggestion.synonym)
        else:
            return svc.add_category(suggestion.slug, suggestion.tx_type, suggestion.synonyms)
