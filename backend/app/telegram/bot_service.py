from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.telegram import TelegramVoicePayload
from app.services.planned_expense_service import PlannedExpenseService
from app.services.recurring_service import RecurringService
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
        self.planned_expense_service = PlannedExpenseService(db)
        self.recurring_service = RecurringService(db)
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

    def process_plan_command(
        self,
        telegram_user_id: int,
        title: str,
        amount: float,
        category: str,
        planned_date: str,
    ) -> dict[str, str]:
        from datetime import date

        item = self.planned_expense_service.create_manual(
            telegram_user_id=telegram_user_id,
            title=title,
            amount=amount,
            category=category,
            planned_date=date.fromisoformat(planned_date),
        )
        return {
            "action": "planned_created",
            "message": self.formatter.format_planned_created(
                item.title, item.amount, item.category, item.planned_date
            ),
        }

    def process_planned_command(self, telegram_user_id: int) -> dict[str, str]:
        from datetime import date

        today = date.today()
        items = self.planned_expense_service.list_all(telegram_user_id, today=today)
        return {
            "action": "planned_list",
            "message": self.formatter.format_planned_list(
                [
                    {
                        "title": item.title,
                        "amount": item.amount,
                        "category": item.category,
                        "planned_date": item.planned_date,
                        "is_overdue": item.planned_date < today.isoformat(),
                    }
                    for item in items
                ]
            ),
        }

    def confirm_planned_expense(
        self,
        telegram_user_id: int,
        planned_expense_id: int,
        actual_amount: float | None = None,
    ) -> dict[str, str]:
        result = self.planned_expense_service.confirm_expense(
            telegram_user_id=telegram_user_id,
            planned_expense_id=planned_expense_id,
            actual_amount=actual_amount,
        )
        if result is None:
            return {
                "action": "planned_missing",
                "message": "Этот расход уже обработан или не найден.",
            }
        return {
            "action": "planned_confirmed",
            "message": self.formatter.format_planned_confirmed(
                result.planned.title,
                result.transaction.amount,
                result.planned.category,
            ),
        }

    def cancel_planned_expense(self, telegram_user_id: int, planned_expense_id: int) -> dict[str, str]:
        result = self.planned_expense_service.cancel_expense(
            telegram_user_id=telegram_user_id,
            planned_expense_id=planned_expense_id,
        )
        if result is None:
            return {
                "action": "planned_missing",
                "message": "Этот расход уже обработан или не найден.",
            }
        return {
            "action": "planned_cancelled",
            "message": self.formatter.format_planned_cancelled(result.title),
        }

    def update_planned_date(
        self,
        telegram_user_id: int,
        planned_expense_id: int,
        planned_date: str,
    ) -> dict[str, str]:
        from datetime import date

        result = self.planned_expense_service.update_planned_date(
            telegram_user_id=telegram_user_id,
            planned_expense_id=planned_expense_id,
            planned_date=date.fromisoformat(planned_date),
        )
        if result is None:
            return {
                "action": "planned_missing",
                "message": "Этот расход уже обработан или не найден.",
            }
        return {
            "action": "planned_updated",
            "message": self.formatter.format_planned_updated(result.title, result.planned_date),
        }

    def update_recurring_amount(self, telegram_user_id: int, recurring_id: int, amount: float) -> dict[str, str]:
        rt = self.recurring_service.update_amount(telegram_user_id, recurring_id, amount)
        if rt is None:
            return {"action": "recurring_missing", "message": "Правило не найдено."}
        return {
            "action": "recurring_updated",
            "message": self.formatter.format_recurring_updated(rt.title, f"{float(rt.amount):.0f}"),
        }

    def deactivate_recurring(self, telegram_user_id: int, recurring_id: int) -> dict[str, str]:
        rt = self.recurring_service.rt_repo.get(telegram_user_id, recurring_id)
        if rt is None:
            return {"action": "recurring_missing", "message": "Правило не найдено."}
        ok = self.recurring_service.deactivate(telegram_user_id, recurring_id)
        if not ok:
            return {"action": "recurring_missing", "message": "Правило не найдено."}
        return {
            "action": "recurring_deleted",
            "message": self.formatter.format_recurring_deleted(rt.title),
        }

    def update_recurring_category(self, telegram_user_id: int, recurring_id: int, category: str) -> dict[str, str]:
        rt = self.recurring_service.update_category(telegram_user_id, recurring_id, category)
        if rt is None:
            return {"action": "recurring_missing", "message": "Правило не найдено."}
        return {
            "action": "recurring_updated",
            "message": f"✅ Обновил правило «{rt.title}»: категория {self.formatter.category_label(rt.category)}",
        }

    def update_recurring_schedule(
        self,
        telegram_user_id: int,
        recurring_id: int,
        frequency: str,
        day_value: int,
    ) -> dict[str, str]:
        rt = self.recurring_service.update_schedule(telegram_user_id, recurring_id, frequency, day_value)
        if rt is None:
            return {"action": "recurring_missing", "message": "Правило не найдено."}
        return {
            "action": "recurring_updated",
            "message": f"✅ Обновил правило «{rt.title}»: {self.recurring_service._format_schedule(rt)}",
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
