from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.user_category_mapping_repository import UserCategoryMappingRepository
from app.schemas.parser import ParseResult
from app.services.parser_service import ParserService
from app.services.transaction_service import TransactionService
from app.services.voice_flow_service import VoiceFlowService
from app.telegram.formatter import TreasuryFormatter

formatter = TreasuryFormatter()
START_MESSAGE = formatter.format_start()


@dataclass(slots=True)
class PendingCategoryResolution:
    parsed: ParseResult
    raw_category: str
    suggestions: list[str]
    source: str = "text"


class TelegramTextFlow:
    _pending_category_resolutions: dict[int, PendingCategoryResolution] = {}

    def __init__(self, db: Session, parser_service: ParserService | None = None) -> None:
        self.db = db
        self.parser_service = parser_service or ParserService()
        self.transaction_service = TransactionService(db)
        self.voice_flow_service = VoiceFlowService(db, parser_service=self.parser_service)
        self.mapping_repo = UserCategoryMappingRepository(db)

    def handle_text(self, telegram_user_id: int, text: str) -> dict[str, object]:
        normalized_text = self._normalize_incoming_text(text)

        pending_resolution = self._pending_category_resolutions.get(telegram_user_id)
        if pending_resolution is not None:
            resolved = self._handle_pending_category_resolution(telegram_user_id, normalized_text, pending_resolution)
            if resolved is not None:
                return resolved

        voice_edit = self.voice_flow_service.apply_voice_edit(telegram_user_id, normalized_text)
        if voice_edit is not None:
            payload: dict[str, object] = {"action": voice_edit.action, "message": voice_edit.message}
            if voice_edit.voice_log_id is not None:
                payload["voice_log_id"] = str(voice_edit.voice_log_id)
            return payload

        parsed = self.parser_service.parse(normalized_text)
        if parsed.confidence_label == "high":
            category_fragment = self.parser_service.extract_category_fragment(normalized_text)
            suggestions = self.parser_service.suggest_categories(category_fragment)
            if suggestions and category_fragment and category_fragment not in self.parser_service.category_lookup:
                normalized_category = self.parser_service.normalize_category_candidate(category_fragment)

                # Check user's learned category mappings before asking
                learned = self._check_learned_mapping(telegram_user_id, normalized_category)
                if learned is not None:
                    parsed_with_category = ParseResult(
                        matched=True,
                        confidence=parsed.confidence,
                        confidence_label="high",
                        transaction_type=parsed.transaction_type,
                        amount=parsed.amount,
                        category=learned,
                        description=normalized_category,
                        pattern=parsed.pattern,
                        raw_input=parsed.raw_input,
                    )
                    item = self.transaction_service.create_from_parse(
                        telegram_user_id=telegram_user_id, source="text", parsed=parsed_with_category,
                    )
                    self.mapping_repo.upsert(telegram_user_id, normalized_category, learned)
                    self.db.commit()
                    summary = self.transaction_service.get_summary(telegram_user_id=telegram_user_id, period="month")
                    operation_label = "доход" if item.type == "income" else "расход"
                    return {
                        "action": "saved",
                        "message": formatter.format_saved(operation_label, item.amount, item.category, self._signed(summary.balance)),
                        "saved_category": item.category,
                    }

                return self._set_pending_category_resolution(telegram_user_id, parsed, normalized_category, suggestions, source="text")

            item = self.transaction_service.create_from_parse(
                telegram_user_id=telegram_user_id,
                source="text",
                parsed=parsed,
            )
            summary = self.transaction_service.get_summary(telegram_user_id=telegram_user_id, period="month")
            operation_label = "доход" if item.type == "income" else "расход"
            return {
                "action": "saved",
                "message": formatter.format_saved(operation_label, item.amount, item.category, self._signed(summary.balance)),
                "saved_category": item.category,
            }
        if parsed.confidence_label == "medium":
            raw_category = (parsed.description or "").strip()
            normalized_raw = self.parser_service._normalize(raw_category)
            if raw_category and normalized_raw not in self.parser_service.category_lookup:
                normalized_category = self.parser_service.normalize_category_candidate(raw_category)

                # Check user's learned category mappings before asking
                learned = self._check_learned_mapping(telegram_user_id, normalized_category)
                if learned is not None:
                    parsed_with_category = ParseResult(
                        matched=True,
                        confidence=0.9,
                        confidence_label="high",
                        transaction_type=parsed.transaction_type or "expense",
                        amount=parsed.amount,
                        category=learned,
                        description=normalized_category,
                        pattern=parsed.pattern,
                        raw_input=parsed.raw_input,
                    )
                    item = self.transaction_service.create_from_parse(
                        telegram_user_id=telegram_user_id, source="text", parsed=parsed_with_category,
                    )
                    self.mapping_repo.upsert(telegram_user_id, normalized_category, learned)
                    self.db.commit()
                    summary = self.transaction_service.get_summary(telegram_user_id=telegram_user_id, period="month")
                    operation_label = "доход" if item.type == "income" else "расход"
                    return {
                        "action": "saved",
                        "message": formatter.format_saved(operation_label, item.amount, item.category, self._signed(summary.balance)),
                        "saved_category": item.category,
                    }

                suggestions = self.parser_service.suggest_categories(normalized_category)
                return self._set_pending_category_resolution(telegram_user_id, parsed, normalized_category, suggestions, source="text")
            return {
                "action": "clarify_category",
                "message": formatter.format_clarify_category(str(parsed.amount), parsed.description),
            }
        if parsed.confidence_label == "low":
            return {
                "action": "clarify",
                "message": formatter.format_clarify(str(parsed.amount)),
            }
        return {
            "action": "fallback",
            "message": formatter.format_fallback(),
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
            self._pending_category_resolutions.pop(telegram_user_id, None)
            return {
                "action": "category_resolution_cancelled",
                "message": formatter.format_category_resolution_cancelled(),
                "remove_keyboard": True,
            }

        create_label = self.parser_service._normalize(formatter.format_create_category_option(pending.raw_category))
        if choice_normalized == create_label:
            self._pending_category_resolutions.pop(telegram_user_id, None)
            return self._save_from_pending(telegram_user_id, pending, pending.raw_category, remove_keyboard=True)

        for suggestion in pending.suggestions:
            label = self.parser_service._normalize(formatter.category_label(suggestion))
            use_label = self.parser_service._normalize(formatter.format_use_category_option(suggestion))
            if choice_normalized in {label, use_label}:
                self._pending_category_resolutions.pop(telegram_user_id, None)
                return self._save_from_pending(telegram_user_id, pending, suggestion, remove_keyboard=True)

        if choice_normalized in self.parser_service.category_lookup:
            resolved_category = self.parser_service.category_lookup[choice_normalized]
            self._pending_category_resolutions.pop(telegram_user_id, None)
            return self._save_from_pending(telegram_user_id, pending, resolved_category, remove_keyboard=True)

        normalized_choice = self.parser_service.normalize_category_candidate(choice)
        suggestions = self.parser_service.suggest_categories(normalized_choice)
        self._pending_category_resolutions[telegram_user_id] = PendingCategoryResolution(
            parsed=pending.parsed,
            raw_category=normalized_choice,
            suggestions=suggestions,
            source=pending.source,
        )
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
    ) -> dict[str, object]:
        pending = PendingCategoryResolution(
            parsed=parsed,
            raw_category=raw_category,
            suggestions=suggestions,
            source=source,
        )
        self._pending_category_resolutions[telegram_user_id] = pending
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
        )

        # Learn the merchant -> category mapping for future auto-categorization
        if pending.raw_category:
            self.mapping_repo.upsert(telegram_user_id, pending.raw_category.lower().strip(), category)
            self.db.commit()

        summary = self.transaction_service.get_summary(telegram_user_id=telegram_user_id, period="month")
        operation_label = "доход" if item.type == "income" else "расход"
        return {
            "action": "saved",
            "message": formatter.format_saved(operation_label, item.amount, item.category, self._signed(summary.balance)),
            "saved_category": item.category,
            "remove_keyboard": remove_keyboard,
        }

    def _check_learned_mapping(self, telegram_user_id: int, merchant_text: str) -> str | None:
        """Check if user has a learned category mapping for this merchant text.
        Returns the category slug if confident enough, None otherwise."""
        normalized = merchant_text.lower().strip()
        mapping = self.mapping_repo.find(telegram_user_id, normalized)
        if mapping is not None and self.mapping_repo.is_confident(mapping):
            return mapping.category
        return None

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
    def _signed(value: str) -> str:
        return value if value.startswith("-") else f"+{value}"
