# Input Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `InputGuard` service that blocks off-topic messages at the start of `handle_text` before any parser or LLM call, saving API costs.

**Architecture:** New `InputGuard` class in `backend/app/services/input_guard.py` with combo whitelist+blacklist logic. Blacklist runs first (explicit off-topic wins), then whitelist passes financial signals, default rejects everything else. Integrated into `TelegramTextFlow.__init__` and called at top of `handle_text` when no pending category resolution.

**Tech Stack:** Python 3.11+, re (stdlib), pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/services/input_guard.py` | Create | InputGuard class with check() logic |
| `backend/tests/test_input_guard.py` | Create | Unit tests — no DB, no mocks |
| `backend/app/telegram/handlers.py` | Modify | Init guard + call at top of handle_text |

---

## Task 1: Create InputGuard service with tests (TDD)

**Files:**
- Create: `backend/app/services/input_guard.py`
- Create: `backend/tests/test_input_guard.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_input_guard.py`:

```python
import pytest
from app.services.input_guard import InputGuard

guard = InputGuard()

REJECTION_MSG = "Я работаю только с финансами — расходами, доходами и бюджетом."


# --- Blacklist: explicit off-topic → rejected ---

@pytest.mark.parametrize("text", [
    "расскажи анекдот",
    "Расскажи Анекдот",                  # case-insensitive
    "напиши стих про осень",
    "привет как дела",
    "здравствуй",
    "добрый день",
    "какая погода завтра",
    "новости спорта",
    "дай рецепт борща",
    "помоги с домашним заданием",
    "расскажи анекдот про 100 рублей",   # blacklist wins over digit
    "как дела с бюджетом?",              # blacklist "как дела" wins over whitelist "бюджет"
])
def test_blacklist_rejected(text):
    assert guard.check(text) == REJECTION_MSG


# --- Whitelist: financial signals → passed ---

@pytest.mark.parametrize("text", [
    "потратил 500 на еду",
    "купил кофе за 150",
    "заплатил 3000 за интернет",
    "получил зарплату 80000",
    "перевел 1000 маме",
    "списали 299₽ за подписку",
    "налог 13%",
    "кредит закрыт",
    "расход на такси",                   # financial keyword, no digit
    "бюджет на месяц",
    "напиши расход на такси",            # "напиши" NOT in blacklist; whitelist "расход" saves it
    "расскажи сколько я потратил",       # NOT blacklisted; whitelist "потратил" saves it
])
def test_whitelist_passed(text):
    assert guard.check(text) is None


@pytest.mark.parametrize("text", [
    "потратил на еду",        # financial keyword без цифры
    "доход вырос",
    "долг перед банком",
    "депозит открыл",
    "выплата по кредиту",
])
def test_whitelist_keywords_no_digit(text):
    assert guard.check(text) is None


# --- Default reject: no signals on either side ---

@pytest.mark.parametrize("text", [
    "ок",
    "хорошо",
    "понял",
    "да",
    "нет",
    "",
    "   ",
    "lorem ipsum",
    "расскажи",          # "расскажи" alone — not blacklisted, no financial signal → default reject
    "напиши",            # same
])
def test_default_rejected(text):
    assert guard.check(text) == REJECTION_MSG
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_input_guard.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError` или `ImportError` — `input_guard` не существует.

- [ ] **Step 3: Implement InputGuard**

Create `backend/app/services/input_guard.py`:

```python
"""InputGuard — rejects off-topic messages before parser/LLM."""
from __future__ import annotations

import re

_REJECTION = "Я работаю только с финансами — расходами, доходами и бюджетом."

# Patterns that indicate explicitly off-topic requests.
# Checked BEFORE financial whitelist — blacklist always wins.
# NOTE: "расскажи" and "напиши" are intentionally NOT here — they may appear
# in valid financial messages ("напиши расход на такси"). They are caught by
# the default-reject path when no financial signals are present.
_BLACKLIST: tuple[str, ...] = (
    "анекдот", "шутк", "стих", "поэм", "песн",
    "привет", "здравствуй", "добрый день", "добрый вечер",
    "как дела", "как ты",
    "погода", "новост", "политик", "спорт", "рецепт",
    "помоги с",
)

# Substrings that indicate a financial message. Any match → pass through.
_FINANCIAL_KEYWORDS: tuple[str, ...] = (
    "потратил", "купил", "заплатил", "получил",
    "доход", "расход", "зарплата", "зарплат",
    "перевёл", "перевел",
    "стоит", "рублей", "копейк",
    "бюджет", "трат", "плат", "выплат",
    "списал", "снял", "внёс", "вернул",
    "задолж", "долг", "кредит", "депозит", "налог",
)

_CURRENCY_RE = re.compile(r"[₽$€£]|\d")


class InputGuard:
    """Rejects non-financial messages before any parser or LLM call.

    check() returns the rejection message string when the text is off-topic,
    or None when the text should be processed normally.

    Logic (in order):
    1. Blacklist — explicit off-topic patterns → reject (blacklist wins over all)
    2. Whitelist — financial signals present → pass
    3. Default — no signals → reject
    """

    def check(self, text: str) -> str | None:
        t = text.lower().strip()
        if not t:
            return _REJECTION

        # 1. Blacklist: explicit off-topic wins regardless of financial signals
        if any(pattern in t for pattern in _BLACKLIST):
            return _REJECTION

        # 2. Whitelist: digits, currency symbols, or financial keywords
        if _CURRENCY_RE.search(t):
            return None
        if any(kw in t for kw in _FINANCIAL_KEYWORDS):
            return None

        # 3. Default: no financial signals found
        return _REJECTION
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_input_guard.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/input_guard.py backend/tests/test_input_guard.py
git commit -m "feat(input-guard): add InputGuard service with whitelist+blacklist logic"
```

---

## Task 2: Integrate InputGuard into TelegramTextFlow

**Files:**
- Modify: `backend/app/telegram/handlers.py` — `__init__` and `handle_text`

- [ ] **Step 1: Write failing test for integration**

Add to `backend/tests/test_input_guard.py` (append at end of file).

Note: `PendingCategoryResolution`, `_store_set`, and `_pending_store` are confirmed to exist
in `handlers.py` (verified from source). `ParseResult` fields: matched, confidence,
confidence_label, transaction_type, amount, category, description, pattern, raw_input.

```python
# --- Integration: TelegramTextFlow returns offtopic action ---

from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from app.telegram.handlers import TelegramTextFlow, _pending_store


def _make_flow():
    db = MagicMock(spec=Session)
    return TelegramTextFlow(db)


def test_handle_text_offtopic_returns_action():
    flow = _make_flow()
    result = flow.handle_text(telegram_user_id=999, text="расскажи анекдот")
    assert result["action"] == "offtopic"
    assert "финанс" in result["message"].lower()


def test_handle_text_offtopic_skipped_when_pending():
    """Guard must NOT fire when user has a pending category resolution."""
    from app.schemas.parser import ParseResult
    from app.telegram.handlers import PendingCategoryResolution, _store_set

    # _store_set, _pending_store, PendingCategoryResolution all confirmed in handlers.py
    parsed = ParseResult(
        matched=True, confidence=0.9, confidence_label="high",
        transaction_type="expense", amount=None,
        category="other", description=None, pattern=None, raw_input="test",
    )
    _store_set(999, PendingCategoryResolution(
        parsed=parsed, raw_category="тест", suggestions=[]
    ))
    try:
        flow = _make_flow()
        # With pending active, guard is bypassed. "еда" has no financial signals
        # but goes to _handle_pending_category_resolution instead.
        result = flow.handle_text(telegram_user_id=999, text="еда")
        assert result.get("action") != "offtopic"
    finally:
        _pending_store.pop(999, None)
```

- [ ] **Step 2: Run to verify tests fail**

```bash
cd backend && pytest tests/test_input_guard.py::test_handle_text_offtopic_returns_action tests/test_input_guard.py::test_handle_text_offtopic_skipped_when_pending -v
```

Expected: FAIL — guard not yet integrated (ImportError or AttributeError).

- [ ] **Step 3: Modify handlers.py — add import and init**

In `backend/app/telegram/handlers.py`, add import at top with other service imports:

```python
from app.services.input_guard import InputGuard
```

In `TelegramTextFlow.__init__`, add after `self.llm_service = LLMService(db)`:

```python
self._input_guard = InputGuard()
```

- [ ] **Step 4: Modify handlers.py — add guard call in handle_text**

In `handle_text`, after `normalized_text = self._normalize_incoming_text(text)` and before `pending_resolution = _store_get(telegram_user_id)`:

```python
        # Guard: only run when user is NOT in a pending category resolution flow.
        # _store_get returns None when there is no active pending state.
        if _store_get(telegram_user_id) is None:
            rejection = self._input_guard.check(normalized_text)
            if rejection:
                return {"action": "offtopic", "message": rejection}
```

- [ ] **Step 5: Run integration tests**

```bash
cd backend && pytest tests/test_input_guard.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
cd backend && pytest --tb=short -q
```

Expected: no new failures.

- [ ] **Step 7: Commit**

```bash
git add backend/app/telegram/handlers.py
git commit -m "feat(input-guard): integrate InputGuard into TelegramTextFlow.handle_text"
```

---

## Verification Checklist

After both tasks complete:

- [ ] `pytest backend/tests/test_input_guard.py -v` — все тесты зелёные
- [ ] `pytest backend/ --tb=short -q` — нет регрессий
- [ ] Вручную в боте: отправить "расскажи анекдот" → получить отбивку
- [ ] Вручную в боте: отправить "потратил 500 на кофе" → транзакция сохранена
- [ ] Вручную в боте: начать категорию (pending flow) → отправить "расскажи анекдот" → guard не срабатывает
