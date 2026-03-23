# LLM Integration via OpenRouter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the YAML regex parser with LLM (MiniMax M1 via OpenRouter) and add a conversational financial advisor, so the bot understands any natural-language phrasing.

**Architecture:** One new service `LLMService` wraps the OpenRouter API using the sync `openai` SDK client. `TelegramTextFlow.handle_text()` and `VoiceFlowService` call `LLMService.process()` instead of `ParserService`. On error, the bot replies "Сервис временно недоступен".

**Tech Stack:** Python 3.12+, `openai>=1.30.0` (sync client, OpenRouter-compatible), pytest + unittest.mock

---

## File Map

| Action | File | What changes |
|---|---|---|
| Modify | `backend/pyproject.toml` | Add `openai>=1.30.0` dependency |
| Modify | `backend/app/core/settings.py` | Add `openrouter_api_key`, `llm_model` fields |
| Modify | `backend/.env.example` | Add `OPENROUTER_API_KEY`, `LLM_MODEL` |
| **Create** | `backend/app/services/llm_service.py` | New service: LLMService, result types, error |
| **Create** | `backend/tests/test_llm_service.py` | Unit tests for LLMService (all mocked) |
| Modify | `backend/app/telegram/handlers.py` | Replace parser call with llm_service.process() |
| Modify | `backend/app/services/voice_flow_service.py` | Replace 3 parse_many() call sites |

---

## Task 1: Add dependency and settings

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/settings.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Add openai to pyproject.toml**

In `backend/pyproject.toml`, inside `[project]` `dependencies` list, add after `apscheduler>=3.10.4,`:

```toml
  "openai>=1.30.0",
```

- [ ] **Step 2: Add settings fields**

In `backend/app/core/settings.py`, add two fields after `openai_api_key: str = ""`:

```python
    openrouter_api_key: str = ""
    llm_model: str = "minimax/minimax-m1:free"
```

- [ ] **Step 3: Update .env.example**

Append to `backend/.env.example`:

```env
# LLM (OpenRouter)
OPENROUTER_API_KEY=
LLM_MODEL=minimax/minimax-m1:free
```

- [ ] **Step 4: Install the new dependency**

```bash
cd backend && pip install -e .[dev]
```

Expected: successful install, `openai` package present.

- [ ] **Step 5: Verify import works**

```bash
cd backend && python -c "from openai import OpenAI; print('ok')"
```

Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/app/core/settings.py backend/.env.example
git commit -m "feat: add openai dependency and openrouter settings fields"
```

---

## Task 2: Create LLMService (TDD)

**Files:**
- Create: `backend/tests/test_llm_service.py`
- Create: `backend/app/services/llm_service.py`

### Step 2a: Write all failing tests first

- [ ] **Step 1: Create test file**

Create `backend/tests/test_llm_service.py`:

```python
"""Tests for LLMService — all OpenRouter calls are mocked."""
from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services.llm_service import (
    LLMAdvisorResult,
    LLMService,
    LLMTransactionResult,
    LLMUnavailableError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(db=None, mock_response_content: str = "{}"):
    """Return an LLMService with a mocked OpenAI client."""
    if db is None:
        db = MagicMock()
        db.scalars.return_value.all.return_value = []

    mock_message = MagicMock()
    mock_message.content = mock_response_content
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    with patch("app.services.llm_service.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_openai_cls.return_value = mock_client
        service = LLMService(db)
        service._client = mock_client  # keep reference for assertion
    return service


def _tx_response(*items: dict) -> str:
    return json.dumps({"intent": "transaction", "items": list(items)})


def _advisor_response(answer: str) -> str:
    return json.dumps({"intent": "advisor", "answer": answer})


# ---------------------------------------------------------------------------
# Transaction parsing tests
# ---------------------------------------------------------------------------

def test_parse_simple_expense(db_session):
    content = _tx_response({"type": "expense", "amount": 200, "category": "food", "description": "кофе", "date": None})
    svc = _make_service(db_session, content)
    result = svc.process("купил кофе 200", telegram_user_id=1)

    assert isinstance(result, LLMTransactionResult)
    assert len(result.items) == 1
    item = result.items[0]
    assert item.parsed.transaction_type == "expense"
    assert item.parsed.amount == Decimal("200")
    assert item.parsed.category == "food"
    assert item.override_date is None


def test_parse_freeform(db_session):
    content = _tx_response({"type": "expense", "amount": 500, "category": "transport", "description": "такси", "date": None})
    svc = _make_service(db_session, content)
    result = svc.process("ну там рублей 500 на такси потратил примерно", telegram_user_id=1)

    assert isinstance(result, LLMTransactionResult)
    item = result.items[0]
    assert item.parsed.transaction_type == "expense"
    assert item.parsed.amount == Decimal("500")
    assert item.parsed.category == "transport"


def test_parse_multi_transaction(db_session):
    content = _tx_response(
        {"type": "expense", "amount": 80, "category": "food", "description": "хлеб", "date": None},
        {"type": "expense", "amount": 120, "category": "food", "description": "молоко", "date": None},
    )
    svc = _make_service(db_session, content)
    result = svc.process("хлеб 80 и молоко 120", telegram_user_id=1)

    assert isinstance(result, LLMTransactionResult)
    assert len(result.items) == 2
    assert result.items[0].parsed.amount == Decimal("80")
    assert result.items[1].parsed.amount == Decimal("120")


def test_parse_income(db_session):
    content = _tx_response({"type": "income", "amount": 50000, "category": "salary", "description": None, "date": None})
    svc = _make_service(db_session, content)
    result = svc.process("получил зарплату 50000", telegram_user_id=1)

    assert isinstance(result, LLMTransactionResult)
    assert result.items[0].parsed.transaction_type == "income"
    assert result.items[0].parsed.amount == Decimal("50000")


def test_parse_result_fields(db_session):
    """ParseResult mapping: matched=True, confidence=0.95, pattern='llm'."""
    content = _tx_response({"type": "expense", "amount": 300, "category": "food", "description": None, "date": None})
    svc = _make_service(db_session, content)
    result = svc.process("обед 300", telegram_user_id=1)

    p = result.items[0].parsed
    assert p.matched is True
    assert p.confidence == 0.95
    assert p.confidence_label == "high"
    assert p.pattern == "llm"
    assert p.raw_input == "обед 300"


def test_date_extraction(db_session):
    """LLM-returned date is surfaced as override_date, not stored in ParseResult."""
    content = _tx_response({"type": "expense", "amount": 300, "category": "food", "description": None, "date": "2026-03-22"})
    svc = _make_service(db_session, content)
    result = svc.process("вчера потратил 300 на еду", telegram_user_id=1)

    item = result.items[0]
    assert item.override_date is not None
    assert str(item.override_date) == "2026-03-22"


def test_unknown_category_falls_back_to_other(db_session):
    """If LLM returns a category not in categories.yaml, use 'other'."""
    content = _tx_response({"type": "expense", "amount": 100, "category": "nonexistent_slug", "description": None, "date": None})
    svc = _make_service(db_session, content)
    result = svc.process("что-то купил за 100", telegram_user_id=1)

    assert result.items[0].parsed.category == "other"


# ---------------------------------------------------------------------------
# Advisor tests
# ---------------------------------------------------------------------------

def test_advisor_question(db_session):
    content = _advisor_response("В этом месяце ты потратил 3 200 ₽ на еду.")
    svc = _make_service(db_session, content)
    result = svc.process("сколько я потратил на еду?", telegram_user_id=1)

    assert isinstance(result, LLMAdvisorResult)
    assert result.intent == "advisor"
    assert len(result.answer) > 0


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

def test_invalid_json_raises(db_session):
    svc = _make_service(db_session, "this is not json at all")
    with pytest.raises(LLMUnavailableError):
        svc.process("купил что-то", telegram_user_id=1)


def test_unknown_intent_raises(db_session):
    svc = _make_service(db_session, json.dumps({"intent": "unknown"}))
    with pytest.raises(LLMUnavailableError):
        svc.process("...", telegram_user_id=1)


def test_empty_items_raises(db_session):
    svc = _make_service(db_session, json.dumps({"intent": "transaction", "items": []}))
    with pytest.raises(LLMUnavailableError):
        svc.process("купил что-то", telegram_user_id=1)


def test_http_error_raises(db_session):
    from openai import APIError

    db = MagicMock()
    db.scalars.return_value.all.return_value = []

    with patch("app.services.llm_service.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = APIError(
            message="500 Internal Server Error", request=MagicMock(), body=None
        )
        mock_openai_cls.return_value = mock_client
        svc = LLMService(db)
        svc._client = mock_client

    with pytest.raises(LLMUnavailableError):
        svc.process("купил что-то", telegram_user_id=1)
```

- [ ] **Step 2: Run tests — verify they ALL fail (module not found)**

```bash
cd backend && pytest tests/test_llm_service.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'app.services.llm_service'`

### Step 2b: Implement LLMService

- [ ] **Step 3: Create `backend/app/services/llm_service.py`**

```python
"""LLM-powered transaction parser and financial advisor via OpenRouter."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Literal

from openai import APIError, OpenAI
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.parser import ParseResult
from app.services.config_loader import load_yaml

if TYPE_CHECKING:
    from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------


class LLMUnavailableError(Exception):
    """Raised when OpenRouter is unreachable or returns unusable output."""


@dataclass
class LLMParsedItem:
    parsed: ParseResult
    override_date: date | None  # None = today


@dataclass
class LLMTransactionResult:
    intent: Literal["transaction"]
    items: list[LLMParsedItem]


@dataclass
class LLMAdvisorResult:
    intent: Literal["advisor"]
    answer: str


LLMResult = LLMTransactionResult | LLMAdvisorResult


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class LLMService:
    def __init__(self, db: Session) -> None:
        self.db = db
        settings = get_settings()
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
        )
        self._model = settings.llm_model
        self._categories_config = load_yaml("categories.yaml")
        self._valid_slugs: set[str] = {
            cat["slug"] for cat in self._categories_config["ru"]["categories"]
        }

    def process(self, text: str, telegram_user_id: int) -> LLMResult:
        """Parse a user message into a transaction or an advisor answer."""
        transactions = TransactionRepository(self.db).list_for_user(
            telegram_user_id, limit=50, offset=0, period="month"
        )
        system_prompt = self._build_system_prompt(transactions)

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
        except APIError as exc:
            logger.error("OpenRouter API error: %s", exc)
            raise LLMUnavailableError(str(exc)) from exc

        raw = response.choices[0].message.content or ""
        return self._parse_response(raw, text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_response(self, raw: str, original_text: str) -> LLMResult:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("LLM returned invalid JSON: %r", raw)
            raise LLMUnavailableError("invalid JSON from LLM") from exc

        intent = data.get("intent")

        if intent == "advisor":
            answer = (data.get("answer") or "").strip()
            if not answer:
                raise LLMUnavailableError("empty advisor answer")
            return LLMAdvisorResult(intent="advisor", answer=answer)

        if intent == "transaction":
            raw_items = data.get("items") or []
            if not raw_items:
                raise LLMUnavailableError("empty transaction items list")
            items = [self._parse_item(item, original_text) for item in raw_items]
            return LLMTransactionResult(intent="transaction", items=items)

        raise LLMUnavailableError(f"unknown intent: {intent!r}")

    def _parse_item(self, item: dict, original_text: str) -> LLMParsedItem:
        try:
            amount = Decimal(str(item["amount"]))
        except (KeyError, InvalidOperation) as exc:
            raise LLMUnavailableError(f"invalid amount: {item.get('amount')!r}") from exc

        tx_type = item.get("type", "expense")
        if tx_type not in ("income", "expense"):
            tx_type = "expense"

        category = item.get("category") or "other"
        if category not in self._valid_slugs:
            category = "other"

        override_date: date | None = None
        raw_date = item.get("date")
        if raw_date:
            try:
                override_date = date.fromisoformat(raw_date)
            except ValueError:
                override_date = None

        parsed = ParseResult(
            matched=True,
            confidence=0.95,
            confidence_label="high",
            transaction_type=tx_type,
            amount=amount,
            category=category,
            description=item.get("description"),
            pattern="llm",
            raw_input=original_text,
        )
        return LLMParsedItem(parsed=parsed, override_date=override_date)

    def _build_system_prompt(self, transactions: list[Transaction]) -> str:
        categories = self._categories_config["ru"]["categories"]
        category_lines = "\n".join(
            f"- {cat['slug']}: {', '.join(str(s) for s in cat['synonyms'][:5])}"
            for cat in categories
        )
        tx_lines = "\n".join(
            f"{tx.created_at.strftime('%d.%m')}: {tx.type.value} {tx.amount} {tx.category}"
            for tx in transactions
        ) or "нет транзакций"
        today = datetime.now().strftime("%Y-%m-%d")

        return (
            f"Ты финансовый ассистент для личного бюджета. Сегодня {today}.\n\n"
            f"КАТЕГОРИИ (используй только эти slug):\n{category_lines}\n\n"
            f"ИСТОРИЯ ТРАНЗАКЦИЙ ЗА МЕСЯЦ:\n{tx_lines}\n\n"
            "Верни JSON строго одного из двух форматов:\n"
            '1. Транзакция: {"intent":"transaction","items":[{"type":"expense"|"income",'
            '"amount":число,"category":"slug из списка","description":"строка или null","date":"YYYY-MM-DD или null"}]}\n'
            '2. Вопрос: {"intent":"advisor","answer":"ответ на русском языке"}\n\n'
            "Правила: только валидный JSON без markdown-обёртки; "
            "category ТОЛЬКО из списка выше; date=null если речь идёт о сегодня; "
            "если сумма не указана — это advisor, не transaction."
        )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd backend && pytest tests/test_llm_service.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm_service.py backend/tests/test_llm_service.py
git commit -m "feat: add LLMService with OpenRouter integration and tests"
```

---

## Task 3: Wire LLMService into TelegramTextFlow

**Files:**
- Modify: `backend/app/telegram/handlers.py`

The new `handle_text()` is significantly simpler: no confidence levels, no date extraction, no category clarification for new messages. The pending-resolution and voice-edit early returns stay unchanged.

- [ ] **Step 1: Add LLMService import at top of handlers.py**

Find the imports block in `backend/app/telegram/handlers.py`. After the existing imports add:

```python
from app.services.llm_service import LLMService, LLMUnavailableError
```

- [ ] **Step 2: Update TelegramTextFlow.__init__ to create LLMService**

Find:
```python
    def __init__(self, db: Session, parser_service: ParserService | None = None) -> None:
        self.db = db
        self.parser_service = parser_service or ParserService()
        self.transaction_service = TransactionService(db)
        self.voice_flow_service = VoiceFlowService(db, parser_service=self.parser_service)
        self.mapping_repo = UserCategoryMappingRepository(db)
```

Replace with:
```python
    def __init__(self, db: Session, parser_service: ParserService | None = None) -> None:
        self.db = db
        self.parser_service = parser_service or ParserService()
        self.transaction_service = TransactionService(db)
        self.voice_flow_service = VoiceFlowService(db, parser_service=self.parser_service)
        self.mapping_repo = UserCategoryMappingRepository(db)
        self.llm_service = LLMService(db)
```

- [ ] **Step 3: Replace handle_text() body**

Find the entire `handle_text` method body (from `normalized_text = ...` to the final `return {"action": "fallback", ...}`) and replace it with:

```python
    def handle_text(self, telegram_user_id: int, text: str) -> dict[str, object]:
        normalized_text = self._normalize_incoming_text(text)

        # Preserve in-flight category resolution sessions unchanged
        pending_resolution = _store_get(telegram_user_id)
        if pending_resolution is not None:
            resolved = self._handle_pending_category_resolution(telegram_user_id, normalized_text, pending_resolution)
            if resolved is not None:
                return resolved

        # Preserve voice edit flow unchanged
        voice_edit = self.voice_flow_service.apply_voice_edit(telegram_user_id, normalized_text)
        if voice_edit is not None:
            payload: dict[str, object] = {"action": voice_edit.action, "message": voice_edit.message}
            if voice_edit.voice_log_id is not None:
                payload["voice_log_id"] = str(voice_edit.voice_log_id)
            return payload

        # LLM processing
        try:
            llm_result = self.llm_service.process(normalized_text, telegram_user_id)
        except LLMUnavailableError:
            return {"action": "fallback", "message": "Сервис временно недоступен, попробуй позже."}

        if llm_result.intent == "advisor":
            return {"action": "advisor", "message": llm_result.answer}

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
```

- [ ] **Step 4: Remove now-unused imports from handlers.py**

Remove these imports (they are no longer used in handle_text):
- `from app.services.date_extractor import extract_date`

Leave everything else — `_pending_store`, `_handle_pending_category_resolution`, `UserCategoryMappingRepository` are still used by the pending-resolution branch.

- [ ] **Step 5: Run existing handler tests**

```bash
cd backend && pytest tests/test_telegram_bot_service.py tests/test_voice_flow.py tests/test_voice_edit_flow.py -v
```

Expected: all pass (these tests mock the parser/LLM at a higher level).

- [ ] **Step 6: Commit**

```bash
git add backend/app/telegram/handlers.py
git commit -m "feat: wire LLMService into TelegramTextFlow.handle_text"
```

---

## Task 4: Wire LLMService into VoiceFlowService

**Files:**
- Modify: `backend/app/services/voice_flow_service.py`

Three call sites use `self.parser_service.parse_many()`. Each must be replaced with `self.llm_service.process()`. The rest of each method (voice log creation, confirmation messages, etc.) stays unchanged.

- [ ] **Step 1: Add import and update constructor**

At the top of `backend/app/services/voice_flow_service.py`, add after existing imports:

```python
from app.services.llm_service import LLMService, LLMParsedItem, LLMTransactionResult, LLMUnavailableError
```

Find `VoiceFlowService.__init__`:
```python
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
```

Add `self.llm_service = LLMService(db)` at the end:

```python
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
```

- [ ] **Step 2: Add helper method `_llm_to_multi`**

Add this private method to `VoiceFlowService` (before `_item_preview`). It converts `LLMTransactionResult` into the list of `ParseResult` objects the rest of the methods already work with:

```python
    def _llm_parse(self, text: str, telegram_user_id: int) -> list[LLMParsedItem] | None:
        """Call LLM and return items, or None on failure."""
        try:
            result = self.llm_service.process(text, telegram_user_id)
        except LLMUnavailableError:
            return None
        if not isinstance(result, LLMTransactionResult):
            return None
        return result.items
```

- [ ] **Step 3: Replace call site 1 — `process_voice()`**

Find in `process_voice()`:
```python
        normalized_transcript = self.postprocessor.normalize(stt_result.text)
        multi = self.parser_service.parse_many(normalized_transcript)
        if not multi.has_items:
```

Replace with:
```python
        normalized_transcript = self.postprocessor.normalize(stt_result.text)
        llm_items = self._llm_parse(normalized_transcript, telegram_user_id)
        if not llm_items:
```

Then find the block that uses `multi.items` and `multi.has_items` in `process_voice` and update references:
- `multi.has_items` → `llm_items` (truthy check)
- `multi.items` → `[item.parsed for item in llm_items]`
- `max(item.confidence for item in multi.items)` → `0.95`
- `multi.items[0].confidence_label` → `"high"`

The medium-confidence category clarification block (`if len(multi.items) == 1 and multi.items[0].confidence_label == "medium":`) is **removed** — LLM always returns high confidence.

Full replacement for the body after `normalized_transcript = ...`:

```python
        llm_items = self._llm_parse(normalized_transcript, telegram_user_id)
        if not llm_items:
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

        parsed_results = [item.parsed for item in llm_items]

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
```

- [ ] **Step 4: Replace call site 2 — `apply_voice_edit()`**

Find:
```python
        normalized = self.postprocessor.normalize(edited_text)
        multi = self.parser_service.parse_many(normalized)
        if not multi.has_items:
            self.voice_logs.update_transcript(log.id, normalized, parser_status="edited_failed")
            return VoiceConfirmationResult(
                action="voice_edit_required",
                voice_log_id=log.id,
                transcript=normalized,
                message=f"Не смог разобрать: {normalized}. Попробуй ещё раз.",
            )

        self.voice_logs.update_transcript(log.id, normalized, parser_status="edited")
        parsed_items = [self._item_preview(item) for item in multi.items]
```

Replace with:
```python
        normalized = self.postprocessor.normalize(edited_text)
        llm_items = self._llm_parse(normalized, log.telegram_user_id)
        if not llm_items:
            self.voice_logs.update_transcript(log.id, normalized, parser_status="edited_failed")
            return VoiceConfirmationResult(
                action="voice_edit_required",
                voice_log_id=log.id,
                transcript=normalized,
                message=f"Не смог разобрать: {normalized}. Попробуй ещё раз.",
            )

        self.voice_logs.update_transcript(log.id, normalized, parser_status="edited")
        parsed_items = [self._item_preview(item.parsed) for item in llm_items]
```

- [ ] **Step 5: Replace call site 3 — `confirm_voice()`**

Find:
```python
        multi = self.parser_service.parse_many(log.transcript_text)
        if not multi.has_items:
            self.voice_logs.update_status(voice_log_id, VoiceLogStatus.FAILED)
            return VoiceConfirmationResult(
                action="voice_edit_required",
                voice_log_id=voice_log_id,
                transcript=log.transcript_text,
                message=f"Не смог выделить записи из: {log.transcript_text}. Пришли текстом.",
            )

        saved_items: list[dict[str, str]] = []
        saved_tx_ids: list[str] = []
        for parsed in multi.items:
```

Replace with:
```python
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
```

Also update `create_from_parse` call inside the loop to pass `override_date`:
```python
            tx = self.transactions.create_from_parse(
                telegram_user_id=log.telegram_user_id,
                source="voice",
                parsed=parsed,
                override_date=llm_item.override_date,
            )
```

- [ ] **Step 6: Run voice tests**

```bash
cd backend && pytest tests/test_voice_flow.py tests/test_voice_edit_flow.py tests/test_voice_multi_parse.py -v
```

Expected: all pass.

- [ ] **Step 7: Run full test suite**

```bash
cd backend && pytest -v
```

Expected: all tests pass (or only pre-existing failures, none new).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/voice_flow_service.py
git commit -m "feat: wire LLMService into VoiceFlowService (3 call sites)"
```

---

## Task 5: Final verification and cleanup

**Files:**
- Modify: `backend/app/telegram/handlers.py` (remove dead import if missed)

- [ ] **Step 1: Check for remaining unused imports in handlers.py**

Run ruff to catch any unused imports:

```bash
cd backend && python -m ruff check app/telegram/handlers.py --select F401
```

Fix any reported unused imports.

- [ ] **Step 2: Run the full test suite one final time**

```bash
cd backend && pytest -v
```

Expected: all pass.

- [ ] **Step 3: Manual smoke-test checklist**

Start the backend and bot:
```bash
npm run dev:all:bot
```

Verify these scenarios work end-to-end in Telegram:

| Input | Expected |
|---|---|
| `купил кофе 200` | Сохранено как расход food 200 |
| `ну там рублей 500 на такси примерно` | Сохранено как расход transport 500 |
| `получил зарплату 80000` | Сохранено как доход |
| `хлеб 80 и молоко 120` | 2 транзакции сохранены |
| `сколько я потратил на еду?` | Текстовый ответ-анализ |
| `я укладываюсь в бюджет?` | Текстовый ответ-анализ |
| *(отключи интернет)* | "Сервис временно недоступен" |

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete LLM integration via OpenRouter (MiniMax M1)"
```

---

## Environment Setup Reminder

Before running the bot, set in `backend/.env`:

```env
OPENROUTER_API_KEY=sk-or-...
LLM_MODEL=minimax/minimax-m1:free
```

Get your key at [openrouter.ai/keys](https://openrouter.ai/keys).
