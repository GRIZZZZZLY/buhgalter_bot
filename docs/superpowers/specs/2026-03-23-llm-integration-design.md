# LLM Integration via OpenRouter — Design Spec

**Date:** 2026-03-23
**Status:** Approved
**Scope:** Replace YAML regex parser with LLM (MiniMax M1 via OpenRouter) + add conversational financial advisor

---

## Goal

Replace the rigid `ParserService` (YAML patterns + regex) with a single LLM call that:
1. Parses transactions from any natural-language phrasing
2. Answers free-form financial questions using the user's transaction history

---

## Approach

**Thin wrapper (Approach A):** One new service `LLMService`, minimal changes to existing code. `TelegramTextFlow.handle_text()` calls `LLMService.process()` instead of `ParserService.parse()`. Everything downstream (saving transactions, formatting messages) stays unchanged.

`LLMService` uses the **synchronous** `OpenAI` client (not `AsyncOpenAI`) — the entire service layer is sync, this avoids async/sync mismatch entirely. No changes to handler call signatures.

---

## New Files

### `backend/app/services/llm_service.py`

**Return types:**

```python
@dataclass
class LLMTransactionResult:
    intent: Literal["transaction"]
    items: list[ParseResult]

@dataclass
class LLMAdvisorResult:
    intent: Literal["advisor"]
    answer: str

LLMResult = LLMTransactionResult | LLMAdvisorResult
```

**Error type:**

```python
class LLMUnavailableError(Exception):
    pass
```

Raised when: HTTP error from OpenRouter, invalid/missing JSON in response, empty `items` list.

**Client setup (synchronous):**

```python
from openai import OpenAI  # sync client, not AsyncOpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.openrouter_api_key,
)
```

**Public interface (synchronous):**

```python
class LLMService:
    def __init__(self, db: Session) -> None: ...

    def process(self, text: str, telegram_user_id: int) -> LLMResult: ...
```

`db` is a sync SQLAlchemy `Session` — passed at construction time, used to fetch transaction history via `TransactionRepository(self.db).list_for_user(telegram_user_id, limit=50, period="month")`.

---

## ParseResult Mapping

LLM returns `{"type", "amount", "category", "description", "date"}`. Map to `ParseResult` as follows:

| ParseResult field | Value |
|---|---|
| `matched` | `True` |
| `confidence` | `0.95` |
| `confidence_label` | `"high"` |
| `transaction_type` | LLM `type` field (`"income"` / `"expense"`) |
| `amount` | `Decimal(str(llm_item["amount"]))` |
| `category` | LLM `category` field (validated against category slugs) |
| `description` | LLM `description` field (may be `None`) |
| `pattern` | `"llm"` |
| `raw_input` | original `text` passed to `process()` |

`date` from LLM (`null` or `"YYYY-MM-DD"`) is handled separately — passed as `override_date` to `create_from_parse()`, not stored in `ParseResult`.

---

## System Prompt

Built at call time with:
- Full category list from `categories.yaml` (slug + synonyms) — ensures LLM always returns a valid slug
- Last 50 transactions for the current month (`period="month"`) in compact format — gives advisor real data
- Current date (`datetime.now().strftime("%Y-%m-%d")`) — for relative date resolution

**Response schema — transaction:**

```json
{
  "intent": "transaction",
  "items": [
    {
      "type": "expense",
      "amount": 750,
      "category": "еда",
      "description": "Пятёрочка",
      "date": null
    }
  ]
}
```

`date: null` = today. `date: "YYYY-MM-DD"` = explicit past date (user said «вчера» / «10 марта»).

**Response schema — advisor:**

```json
{
  "intent": "advisor",
  "answer": "В этом месяце ты потратил 8 400 ₽ на еду — это 34% расходов."
}
```

---

## Settings Changes

**`backend/app/core/settings.py`** — add two fields:

```python
openrouter_api_key: str = ""
llm_model: str = "minimax/minimax-m1:free"
```

The existing `openai_api_key` field remains (not removed).

**`backend/.env.example`** — add:

```env
OPENROUTER_API_KEY=
LLM_MODEL=minimax/minimax-m1:free
```

---

## Modified Files

### `backend/app/telegram/handlers.py` — `TelegramTextFlow`

**Constructor:** add `llm_service: LLMService` (instantiated with `self.db`).

**`handle_text()` changes:**

The `pending_resolution` early-return branch at the top of `handle_text()` is **preserved unchanged** — if a user is mid-category-clarification dialog, we return early before ever calling `LLMService`.

After the pending-resolution check, replace:
```python
parsed = self.parser_service.parse(parse_text)
```

With:
```python
try:
    llm_result = self.llm_service.process(normalized_text, telegram_user_id)
except LLMUnavailableError:
    return {"action": "fallback", "message": "Сервис временно недоступен, попробуй позже."}

if llm_result.intent == "advisor":
    return {"action": "advisor", "message": llm_result.answer}

# llm_result.intent == "transaction"
# llm_result.items contains ParseResult objects — use existing save logic unchanged
```

The `extract_date` call and `past_date` / `override_date` logic is **removed** — LLM handles date extraction and returns it in the `date` field of each item.

The category clarification flow (`_set_pending_category_resolution`, `suggest_categories`) is **removed** from the main path — LLM resolves category directly. The `_handle_pending_category_resolution` method and `_pending_store` remain for any in-flight sessions, but are not triggered for new messages.

### `backend/app/services/voice_flow_service.py`

Three call sites to replace (all three call `self.parser_service.parse_many()`):

1. **`process_voice()`** — replace `parse_many(normalized_transcript)` with `llm_service.process(normalized_transcript, telegram_user_id)`, map result to existing flow
2. **`apply_voice_edit()`** — replace `parse_many(normalized)` with `llm_service.process(normalized, telegram_user_id)`
3. **`confirm_voice()`** — replace `parse_many(log.transcript_text)` with `llm_service.process(log.transcript_text, log.telegram_user_id)`

`LLMService` is injected into `VoiceFlowService` constructor (same `db` session).

### `backend/pyproject.toml`

Add to `[project.dependencies]`:
```
openai>=1.30.0
```

---

## What Does NOT Change

- `TransactionService`, repositories, ORM models — untouched
- STT pipeline (`stt_service.py`, audio handling) — unchanged
- `formatter.py`, `keyboards.py` — unchanged
- All tests for `transaction_service`, `bot_service`, `summary` — unchanged
- `ParserService` — stays in codebase; its YAML configs are read at startup to build the LLM category list in the system prompt

---

## New Tests: `backend/tests/test_llm_service.py`

All tests mock the OpenRouter HTTP client (`openai.OpenAI`) — no real API calls.

| Test | Scenario |
|---|---|
| `test_parse_simple_expense` | «купил кофе 200» → `LLMTransactionResult`, 1 item, type=expense, amount=200 |
| `test_parse_freeform` | «ну там рублей 500 на такси» → type=expense, amount=500, category=транспорт |
| `test_parse_multi_transaction` | «хлеб 80 и молоко 120» → 2 items |
| `test_parse_income` | «получил зарплату 50000» → type=income, amount=50000 |
| `test_advisor_question` | «сколько потратил на еду?» → `LLMAdvisorResult`, non-empty answer |
| `test_invalid_json_raises` | LLM returns garbage → `LLMUnavailableError` |
| `test_http_error_raises` | OpenRouter HTTP 500 → `LLMUnavailableError` |
| `test_date_extraction` | «вчера потратил 300» → item has `date` != null |
