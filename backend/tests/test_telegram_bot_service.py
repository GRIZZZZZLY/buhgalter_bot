from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.schemas.parser import ParseResult
from app.schemas.telegram import TelegramVoicePayload
from app.services.recurring_service import RecurringService
from app.services.llm_service import LLMAdvisorResult, LLMParsedItem, LLMService, LLMTransactionResult
from app.telegram.bot_service import TelegramBotService


class FakeAudioService:
    def __init__(self, wav_path: str, fail: bool = False) -> None:
        self.wav_path = wav_path
        self.fail = fail

    def temp_copy(self, source_path: str, extension: str) -> str:
        assert source_path
        assert extension == ".ogg"
        return source_path

    def prepare_wav_from_ogg(self, source_path: str, suffix: str | None = None) -> str:
        assert source_path
        _ = suffix
        if self.fail:
            raise RuntimeError("conversion exploded")
        return self.wav_path

    @staticmethod
    def cleanup_audio_files(*paths: str) -> None:
        pass  # no-op in tests


def test_bot_service_processes_text_message(db_session) -> None:
    fake_parsed = ParseResult(
        matched=True,
        confidence=0.95,
        confidence_label="high",
        transaction_type="expense",
        amount=Decimal("250"),
        category="food",
        description=None,
        pattern="llm",
        raw_input="расход 250 еда",
    )
    fake_llm_result = LLMTransactionResult(
        intent="transaction",
        items=[LLMParsedItem(parsed=fake_parsed, override_date=None)],
    )

    service = TelegramBotService(db_session)
    with patch.object(service.flow.llm_service, "process", return_value=fake_llm_result):
        response = service.process_text_message(telegram_user_id=555, text="расход 250 еда")

    assert response["action"] == "saved"
    assert "250.00" in response["message"]
    assert "Еда" in response["message"]


def test_bot_service_processes_voice_message(db_session, tmp_path: Path) -> None:
    wav_path = tmp_path / "voice.wav"
    wav_path.write_bytes(b"wav")
    wav_path.with_suffix(".txt").write_text("расход 300 транспорт", encoding="utf-8")
    ogg_path = tmp_path / "voice.ogg"
    ogg_path.write_bytes(b"ogg")

    fake_parsed = ParseResult(
        matched=True,
        confidence=0.95,
        confidence_label="high",
        transaction_type="expense",
        amount=Decimal("300"),
        category="transport",
        description=None,
        pattern="llm",
        raw_input="расход 300 транспорт",
    )
    fake_llm_result = LLMTransactionResult(
        intent="transaction",
        items=[LLMParsedItem(parsed=fake_parsed, override_date=None)],
    )

    service = TelegramBotService(db_session, audio_service=FakeAudioService(str(wav_path)))
    with patch.object(service.flow.voice_flow_service.llm_service, "process", return_value=fake_llm_result):
        response, debug = service.process_voice_message(
            TelegramVoicePayload(
                telegram_user_id=555,
                telegram_message_id=101,
                file_id="file-voice",
                original_file_path=str(ogg_path),
            )
        )

    assert response["action"] == "confirm_voice"
    assert debug.converted is True
    assert debug.wav_path == str(wav_path)


def test_bot_service_handles_voice_conversion_failure(db_session, tmp_path: Path) -> None:
    ogg_path = tmp_path / "voice.ogg"
    ogg_path.write_bytes(b"ogg")

    service = TelegramBotService(db_session, audio_service=FakeAudioService(str(tmp_path / "missing.wav"), fail=True))
    response, debug = service.process_voice_message(
        TelegramVoicePayload(
            telegram_user_id=555,
            telegram_message_id=101,
            file_id="file-voice",
            original_file_path=str(ogg_path),
        )
    )

    assert response["action"] == "voice_fallback"
    assert "conversion exploded" in response["message"]
    assert debug.converted is False


def test_financial_question_uses_qa_service(db_session) -> None:
    """Вопрос пользователя ('сколько?') должен возвращать action='advisor' с ответом от FinancialQAService."""
    from app.services.financial_qa_service import FinancialQAService
    service = TelegramBotService(db_session)
    with patch.object(FinancialQAService, "answer", return_value="За месяц потратил 5000₽.") as mock_qa:
        response = service.process_text_message(telegram_user_id=555, text="сколько я потратил за месяц?")
    mock_qa.assert_called_once()
    assert response["action"] == "advisor"
    assert "5000" in response["message"]


def test_llm_prompt_excludes_transaction_history(db_session) -> None:
    """Промпт LLM не должен содержать историю транзакций — экономия ~400 токенов."""
    service = LLMService(db_session)
    prompt = service._build_system_prompt()
    assert "ИСТОРИЯ" not in prompt
    assert "транзакций за месяц" not in prompt.lower()


def test_llm_prompt_limits_synonyms_to_three(db_session) -> None:
    """Промпт категорий — не более 3 синонимов на категорию для сокращения токенов."""
    service = LLMService(db_session)
    prompt = service._build_system_prompt()
    # Проверяем через food как представителя: у "food" есть много синонимов,
    # в промпте не должно быть больше 3 через запятую для одной строки.
    food_line = next((l for l in prompt.splitlines() if l.strip().startswith("- food:")), None)
    assert food_line is not None
    synonyms = food_line.split(":", 1)[1].split(",")
    assert len(synonyms) <= 3


def test_bot_service_creates_planned_expense(db_session) -> None:
    service = TelegramBotService(db_session)

    response = service.process_plan_command(
        telegram_user_id=555,
        title="маникюр",
        amount=2100,
        category="beauty",
        planned_date="2030-04-15",
    )

    assert response["action"] == "planned_created"
    assert "маникюр" in response["message"].lower()
    assert "2100" in response["message"]


def test_bot_service_lists_planned_expenses(db_session) -> None:
    service = TelegramBotService(db_session)
    service.process_plan_command(
        telegram_user_id=555,
        title="маникюр",
        amount=2100,
        category="beauty",
        planned_date="2030-04-15",
    )

    response = service.process_planned_command(telegram_user_id=555)

    assert response["action"] == "planned_list"
    assert "маникюр" in response["message"].lower()
    assert "2100" in response["message"]


def test_bot_service_lists_overdue_planned_expenses_separately(db_session) -> None:
    service = TelegramBotService(db_session)
    from datetime import date, timedelta

    service.planned_expense_service.create_manual(555, "просроченный маникюр", 2100, "beauty", date.today() - timedelta(days=1))
    service.planned_expense_service.create_manual(555, "будущий зал", 3000, "health", date.today() + timedelta(days=2))

    response = service.process_planned_command(telegram_user_id=555)

    assert response["action"] == "planned_list"
    assert "Просроченные" in response["message"]
    assert "просроченный маникюр" in response["message"].lower()
    assert "будущий зал" in response["message"].lower()


def test_bot_service_confirms_planned_expense(db_session) -> None:
    service = TelegramBotService(db_session)
    created = service.process_plan_command(
        telegram_user_id=555,
        title="маникюр",
        amount=2100,
        category="beauty",
        planned_date="2030-04-15",
    )

    planned_id = service.planned_expense_service.list_future(555)[0].id
    response = service.confirm_planned_expense(telegram_user_id=555, planned_expense_id=planned_id)

    assert response["action"] == "planned_confirmed"
    assert "2100" in response["message"]
    assert "Красота" in response["message"]


def test_bot_service_confirms_planned_expense_with_new_amount(db_session) -> None:
    service = TelegramBotService(db_session)
    service.process_plan_command(
        telegram_user_id=555,
        title="маникюр",
        amount=2100,
        category="beauty",
        planned_date="2030-04-15",
    )

    planned_id = service.planned_expense_service.list_future(555)[0].id
    response = service.confirm_planned_expense(
        telegram_user_id=555,
        planned_expense_id=planned_id,
        actual_amount=2500,
    )

    assert response["action"] == "planned_confirmed"
    assert "2500" in response["message"]


def test_bot_service_cancels_planned_expense(db_session) -> None:
    service = TelegramBotService(db_session)
    service.process_plan_command(
        telegram_user_id=555,
        title="маникюр",
        amount=2100,
        category="beauty",
        planned_date="2030-04-15",
    )

    planned_id = service.planned_expense_service.list_future(555)[0].id
    response = service.cancel_planned_expense(telegram_user_id=555, planned_expense_id=planned_id)

    assert response["action"] == "planned_cancelled"
    assert "отмен" in response["message"].lower()


def test_bot_service_updates_planned_date(db_session) -> None:
    service = TelegramBotService(db_session)
    service.process_plan_command(
        telegram_user_id=555,
        title="маникюр",
        amount=2100,
        category="beauty",
        planned_date="2030-04-15",
    )

    planned_id = service.planned_expense_service.list_future(555)[0].id
    response = service.update_planned_date(telegram_user_id=555, planned_expense_id=planned_id, planned_date="2030-04-20")

    assert response["action"] == "planned_updated"
    assert "20" in response["message"]


def test_bot_service_updates_recurring_amount(db_session) -> None:
    service = TelegramBotService(db_session)
    rt = RecurringService(db_session).create(555, "маникюр", 2100, "expense", "beauty", "interval_days", 30)

    response = service.update_recurring_amount(telegram_user_id=555, recurring_id=rt.id, amount=2500)

    assert response["action"] == "recurring_updated"
    assert "2500" in response["message"]


def test_high_confidence_text_skips_llm(db_session) -> None:
    """При high confidence от ParserService LLM не должен вызываться."""
    service = TelegramBotService(db_session)
    with patch.object(service.flow.llm_service, "process") as mock_llm:
        response = service.process_text_message(telegram_user_id=555, text="500 еда")
    mock_llm.assert_not_called()
    assert response["action"] == "saved"


def test_low_confidence_text_calls_llm(db_session) -> None:
    """При low/medium confidence от ParserService LLM должен вызываться."""
    fake_parsed = ParseResult(
        matched=False,
        confidence=0.3,
        confidence_label="low",
        transaction_type=None,
        amount=None,
        category=None,
        description=None,
        pattern=None,
        raw_input="что-то непонятное",
    )
    fake_llm_result = LLMAdvisorResult(
        intent="advisor",
        answer="Не понял что это.",
    )
    service = TelegramBotService(db_session)
    with patch.object(service.flow._input_guard, "check", return_value=None), \
         patch.object(service.flow.llm_service, "process", return_value=fake_llm_result) as mock_llm:
        response = service.process_text_message(telegram_user_id=555, text="что-то непонятное")
    mock_llm.assert_called_once()
    assert response["action"] == "advisor"


def test_bot_service_deactivates_recurring_rule(db_session) -> None:
    service = TelegramBotService(db_session)
    rt = RecurringService(db_session).create(555, "маникюр", 2100, "expense", "beauty", "interval_days", 30)

    response = service.deactivate_recurring(telegram_user_id=555, recurring_id=rt.id)

    assert response["action"] == "recurring_deleted"
    assert "отключ" in response["message"].lower()
