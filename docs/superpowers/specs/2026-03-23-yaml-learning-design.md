# YAML Learning via LLM — Design Spec

**Date:** 2026-03-23
**Status:** Approved
**Scope:** Teach the bot to improve `categories.yaml` based on user corrections and LLM analysis

---

## Goal

Make `categories.yaml` self-improving: user corrections silently update synonyms, and `/improve_categories` triggers an LLM analysis that proposes new synonyms and categories for user approval.

---

## Approach

Direct YAML editing (Approach A): all changes are written into `categories.yaml` in-place. Git history serves as an audit log and rollback mechanism. No new database tables or shadow files.

---

## Feature 1: Category Correction Flow

When the bot sends a transaction confirmation message, it includes an "✏️ Изменить категорию" inline button.

**Flow:**
1. User taps "✏️ Изменить категорию"
2. Bot replies with a grid of all category buttons (from `categories.yaml`)
3. User taps the correct category
4. Bot silently:
   - Updates the transaction in the database to the new category
   - Extracts a keyword from the transaction description and appends it to the chosen category's `synonyms` list in `categories.yaml`
5. No confirmation prompt — done.

**Keyword extraction rule:** take the first token from `transaction.description` (lowercased, stripped) that is:
- length ≥ 3 characters, AND
- not in the stop-list: `{"оплата", "перевод", "платёж", "платеж", "покупка", "списание", "зачисление", "банк", "карта", "счёт", "счет"}`

If no token passes the filter, skip the YAML update but still update the transaction category in the database.

---

## Feature 2: `/improve_categories` Command

Manual trigger only (no scheduler).

**Flow:**
1. User sends `/improve_categories`
2. Bot replies: "Анализирую транзакции…"
3. `CategorySuggestionService.get_suggestions()` is called synchronously (same pattern as existing `LLMService` usage in handlers — sync call inside `run_in_executor` is NOT needed; the whole handler chain is already sync via `python-telegram-bot`'s thread pool)
4. LLM returns JSON list of suggestions (see schema below)
5. Bot sends each suggestion as a separate message with ✅ / ❌ inline buttons
6. User taps ✅ → `YamlLearnerService` applies the change immediately
7. User taps ❌ → suggestion discarded silently

**Pending suggestions** are stored in a module-level dict in `handlers.py` (same pattern as existing `_pending_store`):

```python
# module-level, shared across all handler instances
_pending_suggestions: dict[str, Suggestion] = {}
```

Keyed by `callback_data` string. Lost on bot restart — acceptable.

**`callback_data` format:** buttons use `"sugg:{8-char hex uuid}_yes"` and `"sugg:{8-char hex uuid}_no"`, e.g. `"sugg:a3f2c891_yes"`. `_pending_suggestions` is keyed by the base UUID part (`"sugg:a3f2c891"`). The handler strips the `_yes`/`_no` suffix before lookup: `key = callback_data.rsplit("_", 1)[0]`. Max button length well within Telegram's 64-byte limit.

---

## LLM Suggestion Schema

```json
{
  "suggestions": [
    {
      "type": "add_synonym",
      "category_slug": "food",
      "synonym": "бургер кинг",
      "reason": "встречается 5 раз в транзакциях без синонима"
    },
    {
      "type": "new_category",
      "slug": "sport",
      "transaction_type": "expense",
      "synonyms": ["gym", "фитнес", "бассейн", "спортзал"],
      "reason": "8 транзакций с описанием о спорте, все в категории other"
    }
  ]
}
```

Note: `new_category` has no `display_name` — `categories.yaml` schema does not include this field (`slug`, `type`, `synonyms` only).

**Telegram message format per suggestion:**

- `add_synonym`: "Добавить **'бургер кинг'** как синоним категории *еда*?"
- `new_category`: "Создать новую категорию **'sport'** (gym, фитнес, бассейн, спортзал)?"

Each message has two inline buttons: `[✅ Да | callback_data="sugg:a3f2c891_yes"]` and `[❌ Нет | callback_data="sugg:a3f2c891_no"]`.

---

## New Components

### `backend/app/services/yaml_learner_service.py`

Responsible for reading and writing `categories.yaml`.

```python
class YamlLearnerService:
    def add_synonym(self, category_slug: str, synonym: str) -> bool:
        """Add synonym to existing category. Returns False if slug not found or synonym already exists."""

    def add_category(self, slug: str, tx_type: str, synonyms: list[str]) -> bool:
        """Add new category entry. Returns False if slug already exists."""
```

Uses `ruamel.yaml` to preserve formatting and comments when writing.

### `backend/app/services/category_suggestion_service.py`

Calls LLM synchronously and returns parsed suggestions.

```python
@dataclass
class AddSynonymSuggestion:
    type: Literal["add_synonym"]
    category_slug: str
    synonym: str

@dataclass
class NewCategorySuggestion:
    type: Literal["new_category"]
    slug: str
    tx_type: str
    synonyms: list[str]

Suggestion = AddSynonymSuggestion | NewCategorySuggestion

class CategorySuggestionService:
    def __init__(self, db: Session) -> None: ...

    def get_suggestions(self, telegram_user_id: int) -> list[Suggestion]: ...
```

Raises `LLMUnavailableError` on failure (reuses existing error type from `llm_service.py`).

### Modified: `backend/app/telegram/handlers.py`

- Add "✏️ Изменить категорию" button to transaction confirmation message
- Add `_handle_category_correction(callback_query)` — shows category grid
- Add `_handle_category_selected(callback_query, transaction_id, new_category)` — updates DB + YAML silently
- Add module-level `_pending_suggestions: dict[str, Suggestion] = {}`
- Add `/improve_categories` command handler — calls `CategorySuggestionService`, populates `_pending_suggestions`, sends suggestion messages
- Add `_handle_suggestion_callback(callback_query)` — applies or discards pending suggestion

---

## Dependencies

Add to `pyproject.toml`:
```
ruamel.yaml>=0.18.0
```

---

## What Does NOT Change

- `categories.yaml` schema — same format (`slug`, `type`, `synonyms`), just more entries added over time
- `LLMService`, `TransactionService`, repositories — untouched
- STT pipeline, formatter — untouched

---

## Known Limitations

- `_pending_suggestions` lost on bot restart — user needs to re-run `/improve_categories`
- YAML grows unbounded over time — no pruning mechanism
- LLM may suggest low-quality synonyms — mitigated by user confirmation gate
- Concurrent writes not safe — acceptable for single-process deployment

---

## Tests

### `backend/tests/test_yaml_learner_service.py`

| Test | Scenario |
|---|---|
| `test_add_synonym_success` | adds synonym to existing category, YAML updated |
| `test_add_synonym_already_exists` | returns False, YAML unchanged |
| `test_add_synonym_unknown_slug` | returns False |
| `test_add_category_success` | new slug added to YAML |
| `test_add_category_duplicate_slug` | returns False |

### `backend/tests/test_category_suggestion_service.py`

| Test | Scenario |
|---|---|
| `test_returns_add_synonym_suggestion` | LLM suggests synonym → parsed correctly |
| `test_returns_new_category_suggestion` | LLM suggests new category → parsed correctly |
| `test_llm_error_raises` | LLM fails → `LLMUnavailableError` propagated |
| `test_empty_suggestions` | LLM returns empty list → no crash |

### `backend/tests/test_handlers_category_correction.py`

| Test | Scenario |
|---|---|
| `test_correction_updates_transaction` | user selects new category → DB transaction updated |
| `test_correction_adds_synonym_to_yaml` | valid description → keyword added to YAML |
| `test_correction_skips_yaml_on_empty_description` | empty description → YAML unchanged, transaction updated |
| `test_correction_skips_yaml_on_stopword` | description is "оплата" → YAML unchanged |
