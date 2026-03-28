import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.user_category_mapping_repository import UserCategoryMappingRepository
from app.schemas.parser import ParseResult
from app.services.advisor_intent_router import AdvisorIntentRouter
from app.services.financial_qa_service import FinancialQAService
from app.services.input_guard import InputGuard
from app.services.llm_service import LLMService, LLMUnavailableError, LLMPlannedResult, LLMRecurringResult, LLMTransactionResult
from app.services.parser_service import ParserService
from app.services.transaction_service import TransactionService
from app.services.voice_flow_service import VoiceFlowService
from app.telegram.formatter import TreasuryFormatter

logger = logging.getLogger(__name__)
formatter = TreasuryFormatter()
START_MESSAGE = formatter.format_start()

# How long (seconds) a pending category resolution is kept before being discarded.
_PENDING_TTL_SECONDS = 600  # 10 minutes


@dataclass(slots=True)
class PendingCategoryResolution:
    parsed: ParseResult
    raw_category: str
    suggestions: list[str]
    source: str = "text"
    override_date: "date | None" = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Module-level shared store: user_id → PendingCategoryResolution
# This is intentionally a module-level dict (not a class variable) so that
# all TelegramTextFlow instances share the same state — matching the single
# python-telegram-bot process model — while remaining easy to clear in tests.
# ---------------------------------------------------------------------------
_pending_store: dict[int, PendingCategoryResolution] = {}


def _store_get(user_id: int) -> "PendingCategoryResolution | None":
    """Return pending resolution for user, or None if absent / expired."""
    entry = _pending_store.get(user_id)
    if entry is None:
        return None
    age = (datetime.now(timezone.utc) - entry.created_at).total_seconds()
    if age > _PENDING_TTL_SECONDS:
        logger.debug("pending category resolution expired for user_id=%s (age=%.0fs)", user_id, age)
        _pending_store.pop(user_id, None)
        return None
    return entry


def _store_set(user_id: int, entry: "PendingCategoryResolution") -> None:
    _pending_store[user_id] = entry


def _store_pop(user_id: int) -> None:
    _pending_store.pop(user_id, None)


# ---------------------------------------------------------------------------
# Module-level store for /improve_categories suggestions
# ---------------------------------------------------------------------------
_pending_suggestions: dict = {}


def _sugg_set(key: str, suggestion) -> None:
    _pending_suggestions[key] = suggestion


def _sugg_pop(key: str):
    return _pending_suggestions.pop(key, None)


class TelegramTextFlow:
    def __init__(self, db: Session, parser_service: ParserService | None = None) -> None:
        self.db = db
        self.parser_service = parser_service or ParserService()
        self.transaction_service = TransactionService(db)
        self.voice_flow_service = VoiceFlowService(db, parser_service=self.parser_service)
        self.mapping_repo = UserCategoryMappingRepository(db)
        self.llm_service = LLMService(db)
        self._input_guard = InputGuard()

    def handle_text(self, telegram_user_id: int, text: str) -> dict[str, object]:
        normalized_text = self._normalize_incoming_text(text)

        # Guard: only run when user is NOT in a pending category resolution flow.
        # _store_get returns None when there is no active pending state.
        pending_resolution = _store_get(telegram_user_id)
        if pending_resolution is None:
            rejection = self._input_guard.check(normalized_text)
            if rejection:
                return {"action": "offtopic", "message": rejection}

        if pending_resolution is not None:
            resolved = self._handle_pending_category_resolution(telegram_user_id, normalized_text, pending_resolution)
            if resolved is not None:
                return resolved

        voice_edit = self.voice_flow_service.apply_voice_edit(telegram_user_id, normalized_text)
        if voice_edit is not None:
            payload: dict[str, object] = {"action": voice_edit.action, "message": voice_edit.message}
            if voice_edit.voice_log_id is not None:
                payload["voice_log_id"] = str(voice_edit.voice_log_id)
            if voice_edit.parsed_items:
                payload["parsed_items"] = voice_edit.parsed_items
            return payload

        # Question shortcut: route financial questions directly to QA service
        if self._looks_like_question(normalized_text):
            answer = FinancialQAService(self.db).answer(normalized_text, telegram_user_id)
            return {"action": "advisor", "message": answer}

        # Fast path: skip LLM when ParserService is confident
        parsed = self.parser_service.parse(normalized_text)
        if parsed.confidence_label == "high" and parsed.amount is not None:
            tx = self.transaction_service.create_from_parse(
                telegram_user_id=telegram_user_id,
                source="text",
                parsed=parsed,
                override_date=None,
            )
            summary = self.transaction_service.get_summary(telegram_user_id=telegram_user_id, period="month")
            operation_label = "доход" if tx.type == "income" else "расход"
            return {
                "action": "saved",
                "message": formatter.format_saved(operation_label, tx.amount, tx.category, self._signed(summary.balance), None),
                "saved_category": tx.category,
                "saved_transaction_id": str(tx.id),
            }

        # LLM processing
        try:
            llm_result = self.llm_service.process(normalized_text, telegram_user_id)
        except LLMUnavailableError:
            return {"action": "fallback", "message": "Сервис временно недоступен, попробуй позже."}

        if llm_result.intent == "advisor":
            answer = FinancialQAService(self.db).answer(normalized_text, telegram_user_id)
            return {"action": "advisor", "message": answer}

        if isinstance(llm_result, LLMPlannedResult):
            return {
                "action": "planned_confirm",
                "parsed_items": [{
                    "title": llm_result.title,
                    "amount": str(llm_result.amount),
                    "category": llm_result.category,
                    "planned_date": llm_result.planned_date.isoformat() if llm_result.planned_date else "",
                    "reminder_time": llm_result.reminder_time or "",
                }],
            }

        if isinstance(llm_result, LLMRecurringResult):
            return {
                "action": "recurring_confirm",
                "parsed_items": [{
                    "title": llm_result.title,
                    "amount": str(llm_result.amount),
                    "category": llm_result.category,
                    "transaction_type": llm_result.transaction_type,
                    "frequency": llm_result.frequency,
                    "day_value": str(llm_result.day_value),
                }],
            }

        if not isinstance(llm_result, LLMTransactionResult):
            return {"action": "fallback", "message": "Не удалось обработать сообщение."}

        # Save transaction(s)
        saved_items: list[dict[str, str]] = []
        last_tx = None
        for llm_item in llm_result.items:
            tx = self.transaction_service.create_from_parse(
                telegram_user_id=telegram_user_id,
                source="text",
                parsed=llm_item.parsed,
                override_date=llm_item.override_date,
            )
            saved_items.append({
                "type": "доход" if tx.type == "income" else "расход",
                "amount": str(tx.amount),
                "category": tx.category,
            })
            last_tx = tx

        summary = self.transaction_service.get_summary(telegram_user_id=telegram_user_id, period="month")
        balance = self._signed(summary.balance)

        if len(saved_items) == 1 and last_tx is not None:
            operation_label = saved_items[0]["type"]
            return {
                "action": "saved",
                "message": formatter.format_saved(operation_label, last_tx.amount, last_tx.category, balance, None),
                "saved_category": last_tx.category,
                "saved_transaction_id": str(last_tx.id),
            }

        return {
            "action": "saved",
            "message": formatter.format_saved_many(saved_items, balance),
        }

    def handle_summary(self, telegram_user_id: int, period: str = "month") -> dict[str, str]:
        summary = self.transaction_service.get_summary(telegram_user_id=telegram_user_id, period=period)
        top_items = [
            {"category": item.category, "amount": item.amount}
            for item in summary.top_expense_categories[:3]
        ]
        return {
            "action": "summary",
            "message": formatter.format_summary(period, self._signed(summary.balance), summary.income_total, summary.expense_total, top_items),
        }

    def handle_voice(
        self,
        telegram_user_id: int,
        telegram_message_id: int | None,
        file_id: str | None,
        original_text: str,
        wav_path: str,
    ) -> dict[str, object]:
        result = self.voice_flow_service.process_voice(
            telegram_user_id=telegram_user_id,
            telegram_message_id=telegram_message_id,
            file_id=file_id,
            original_text=original_text,
            wav_path=wav_path,
        )
        payload: dict[str, object] = {"action": result.action, "message": result.message}
        if result.voice_log_id is not None:
            payload["voice_log_id"] = str(result.voice_log_id)
        if result.transcript is not None:
            payload["transcript"] = result.transcript
        if getattr(result, 'raw_category', None) is not None:
            payload['raw_category'] = result.raw_category
        if getattr(result, 'suggestions', None):
            payload['suggestions'] = result.suggestions
        if result.action == 'clarify_category_choice' and result.parsed_result is not None and result.raw_category is not None:
            self._set_pending_category_resolution(
                telegram_user_id,
                result.parsed_result,
                result.raw_category,
                result.suggestions,
                source='voice',
            )
        return payload

    def start_voice_edit(self, voice_log_id: str) -> dict[str, str]:
        result = self.voice_flow_service.start_edit_voice(UUID(voice_log_id))
        payload = {"action": result.action, "message": result.message}
        if result.voice_log_id is not None:
            payload["voice_log_id"] = str(result.voice_log_id)
        return payload

    def confirm_voice(self, voice_log_id: str) -> dict[str, str]:
        result = self.voice_flow_service.confirm_voice(UUID(voice_log_id))
        payload = {"action": result.action, "message": result.message}
        if result.voice_log_id is not None:
            payload["voice_log_id"] = str(result.voice_log_id)
        return payload

    def cancel_voice(self, voice_log_id: str) -> dict[str, str]:
        result = self.voice_flow_service.cancel_voice(UUID(voice_log_id))
        payload = {"action": result.action, "message": result.message}
        if result.voice_log_id is not None:
            payload["voice_log_id"] = str(result.voice_log_id)
        return payload

    def _handle_pending_category_resolution(
        self,
        telegram_user_id: int,
        text: str,
        pending: PendingCategoryResolution,
    ) -> dict[str, object] | None:
        choice = text.strip()
        if not choice:
            return None
        choice_normalized = self.parser_service._normalize(choice)

        if choice_normalized == "отменить":
            _store_pop(telegram_user_id)
            return {
                "action": "category_resolution_cancelled",
                "message": formatter.format_category_resolution_cancelled(),
                "remove_keyboard": True,
            }

        create_label = self.parser_service._normalize(formatter.format_create_category_option(pending.raw_category))
        if choice_normalized == create_label:
            _store_pop(telegram_user_id)
            return self._save_from_pending(telegram_user_id, pending, pending.raw_category, remove_keyboard=True)

        for suggestion in pending.suggestions:
            label = self.parser_service._normalize(formatter.category_label(suggestion))
            use_label = self.parser_service._normalize(formatter.format_use_category_option(suggestion))
            if choice_normalized in {label, use_label}:
                _store_pop(telegram_user_id)
                return self._save_from_pending(telegram_user_id, pending, suggestion, remove_keyboard=True)

        if choice_normalized in self.parser_service.category_lookup:
            resolved_category = self.parser_service.category_lookup[choice_normalized]
            _store_pop(telegram_user_id)
            return self._save_from_pending(telegram_user_id, pending, resolved_category, remove_keyboard=True)

        normalized_choice = self.parser_service.normalize_category_candidate(choice)
        suggestions = self.parser_service.suggest_categories(normalized_choice)
        _store_set(telegram_user_id, PendingCategoryResolution(
            parsed=pending.parsed,
            raw_category=normalized_choice,
            suggestions=suggestions,
            source=pending.source,
        ))
        return {
            "action": "clarify_category_choice",
            "message": formatter.format_category_resolution_prompt(normalized_choice, suggestions, self.parser_service.detect_merchant_label(normalized_choice)),
            "raw_category": normalized_choice,
            "suggestions": suggestions,
        }

    def _set_pending_category_resolution(
        self,
        telegram_user_id: int,
        parsed: ParseResult,
        raw_category: str,
        suggestions: list[str],
        source: str,
        override_date: "date | None" = None,
    ) -> dict[str, object]:
        pending = PendingCategoryResolution(
            parsed=parsed,
            raw_category=raw_category,
            suggestions=suggestions,
            source=source,
            override_date=override_date,
        )
        _store_set(telegram_user_id, pending)
        return {
            "action": "clarify_category_choice",
            "message": formatter.format_category_resolution_prompt(pending.raw_category, suggestions, self.parser_service.detect_merchant_label(pending.raw_category)),
            "raw_category": pending.raw_category,
            "suggestions": suggestions,
        }

    def _save_from_pending(
        self,
        telegram_user_id: int,
        pending: PendingCategoryResolution,
        category: str,
        *,
        remove_keyboard: bool,
    ) -> dict[str, object]:
        resolved = ParseResult(
            matched=True,
            confidence=0.9,
            confidence_label="high",
            transaction_type=pending.parsed.transaction_type or "expense",
            amount=pending.parsed.amount,
            category=category,
            description=pending.raw_category,
            pattern=pending.parsed.pattern,
            raw_input=pending.parsed.raw_input,
        )
        item = self.transaction_service.create_from_parse(
            telegram_user_id=telegram_user_id,
            source=pending.source,
            parsed=resolved,
            override_date=pending.override_date,
        )

        # Learn the merchant -> category mapping for future auto-categorization
        if pending.raw_category:
            self.mapping_repo.upsert(telegram_user_id, pending.raw_category.lower().strip(), category)
            self.db.commit()

        summary = self.transaction_service.get_summary(telegram_user_id=telegram_user_id, period="month")
        operation_label = "доход" if item.type == "income" else "расход"
        # Show learned mapping in confirmation message
        learned_mapping = (
            f"{pending.raw_category} → {formatter.category_label(category)}"
            if pending.raw_category and pending.raw_category != category
            else None
        )
        return {
            "action": "saved",
            "message": formatter.format_saved(
                operation_label, item.amount, item.category,
                self._signed(summary.balance), pending.override_date,
                learned_mapping=learned_mapping,
            ),
            "saved_category": item.category,
            "saved_transaction_id": str(item.id),
        }

    @staticmethod
    def _normalize_incoming_text(text: str) -> str:
        normalized = text.strip()
        prefixes = [
            "переслано от",
            "forwarded from",
            "ответ пользователю",
            "replying to",
        ]
        lines: list[str] = []
        for line in normalized.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if any(lowered.startswith(prefix) for prefix in prefixes):
                continue
            lines.append(stripped)
        return " ".join(lines).strip()

    @staticmethod
    def _looks_like_question(text: str) -> bool:
        return AdvisorIntentRouter().looks_like_advisor_question(text)

    @staticmethod
    def _signed(value: str) -> str:
        return value if value.startswith("-") else f"+{value}"
