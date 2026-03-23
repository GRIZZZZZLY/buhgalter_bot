# YAML Learning via LLM — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `categories.yaml` self-improving: user corrections silently add synonyms, and `/improve_categories` triggers LLM analysis with user-approved proposals.

**Architecture:** Direct YAML editing via `ruamel.yaml` (preserves formatting). Two new services (`YamlLearnerService`, `CategorySuggestionService`). Corrections wired via `catfix:` inline buttons on saved-transaction messages. Suggestions wired via `sugg:` inline buttons sent by `/improve_categories`.

**Tech Stack:** Python 3.12, ruamel.yaml, python-telegram-bot, existing Groq/OpenAI client pattern, SQLAlchemy sync session, pytest.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `backend/pyproject.toml` | Modify | Add `ruamel.yaml>=0.18.0` |
| `backend/app/services/yaml_learner_service.py` | **Create** | Read/write `categories.yaml` |
| `backend/app/services/category_suggestion_service.py` | **Create** | LLM analysis → suggestion list |
| `backend/app/services/transaction_service.py` | Modify | Add `update_category()` |
| `backend/app/telegram/keyboards.py` | Modify | Add 3 new keyboards |
| `backend/app/telegram/handlers.py` | Modify | Add `_pending_suggestions` store + accessors |
| `backend/app/telegram/bot_service.py` | Modify | Add `handle_category_correction()`, `improve_categories()`, `handle_suggestion_callback()` |
| `backend/app/telegram/runtime.py` | Modify | Register 2 commands + 2 callback handlers, modify `_send_saved_with_undo` |
| `backend/tests/test_yaml_learner_service.py` | **Create** | 5 tests |
| `backend/tests/test_category_suggestion_service.py` | **Create** | 4 tests |
| `backend/tests/test_handlers_category_correction.py` | **Create** | 4 tests |

---

## Task 1: ruamel.yaml dependency + YamlLearnerService

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/services/yaml_learner_service.py`
- Create: `backend/tests/test_yaml_learner_service.py`

---

- [ ] **Step 1: Add ruamel.yaml to pyproject.toml**

In `backend/pyproject.toml`, add after `"openai>=1.30.0",`:
```toml
  "ruamel.yaml>=0.18.0",
```

- [ ] **Step 2: Install dependency**

```bash
cd backend && .venv/Scripts/pip install "ruamel.yaml>=0.18.0"
```

- [ ] **Step 3: Write failing tests**

Create `backend/tests/test_yaml_learner_service.py`:

```python
import textwrap
import pytest
from app.services.yaml_learner_service import YamlLearnerService

SAMPLE_YAML = textwrap.dedent("""\
ru:
  categories:
    - slug: food
      type: expense
      synonyms: [еда, кофе]
    - slug: transport
      type: expense
      synonyms: [такси, метро]
""")


@pytest.fixture
def tmp_yaml(tmp_path):
    p = tmp_path / "categories.yaml"
    p.write_text(SAMPLE_YAML, encoding="utf-8")
    return p


@pytest.fixture
def svc(tmp_yaml):
    return YamlLearnerService(path=tmp_yaml)


def test_add_synonym_success(svc, tmp_yaml):
    result = svc.add_synonym("food", "бургер")
    assert result is True
    content = tmp_yaml.read_text(encoding="utf-8")
    assert "бургер" in content


def test_add_synonym_already_exists(svc, tmp_yaml):
    result = svc.add_synonym("food", "кофе")
    assert result is False
    # file unchanged — кофе appears exactly once
    assert tmp_yaml.read_text(encoding="utf-8").count("кофе") == 1


def test_add_synonym_unknown_slug(svc):
    result = svc.add_synonym("nonexistent", "тест")
    assert result is False


def test_add_category_success(svc, tmp_yaml):
    result = svc.add_category("sport", "expense", ["фитнес", "gym"])
    assert result is True
    content = tmp_yaml.read_text(encoding="utf-8")
    assert "sport" in content
    assert "фитнес" in content


def test_add_category_duplicate_slug(svc):
    result = svc.add_category("food", "expense", ["ещё"])
    assert result is False
```

- [ ] **Step 4: Run tests — verify FAIL**

```bash
cd backend && pytest tests/test_yaml_learner_service.py -v
```
Expected: `ModuleNotFoundError` or `ImportError` (file not created yet)

- [ ] **Step 5: Implement YamlLearnerService**

Create `backend/app/services/yaml_learner_service.py`:

```python
"""Read/write categories.yaml using ruamel.yaml (preserves formatting)."""
from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

CATEGORIES_PATH = Path(__file__).resolve().parent.parent / "config" / "categories.yaml"


class YamlLearnerService:
    def __init__(self, path: Path = CATEGORIES_PATH) -> None:
        self._path = path
        self._yaml = YAML()
        self._yaml.preserve_quotes = True

    def add_synonym(self, category_slug: str, synonym: str) -> bool:
        """Add synonym to existing category. Returns False if slug not found or synonym already exists."""
        data = self._load()
        for cat in data["ru"]["categories"]:
            if cat["slug"] == category_slug:
                if synonym in cat["synonyms"]:
                    return False
                cat["synonyms"].append(synonym)
                self._save(data)
                return True
        return False

    def add_category(self, slug: str, tx_type: str, synonyms: list[str]) -> bool:
        """Add new category entry. Returns False if slug already exists."""
        data = self._load()
        categories = data["ru"]["categories"]
        for cat in categories:
            if cat["slug"] == slug:
                return False
        categories.append({"slug": slug, "type": tx_type, "synonyms": synonyms})
        self._save(data)
        return True

    def _load(self):
        with open(self._path, encoding="utf-8") as f:
            return self._yaml.load(f)

    def _save(self, data) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            self._yaml.dump(data, f)
```

- [ ] **Step 6: Run tests — verify PASS**

```bash
cd backend && pytest tests/test_yaml_learner_service.py -v
```
Expected: 5 passed

- [ ] **Step 7: Commit**

```bash
cd backend && git add pyproject.toml app/services/yaml_learner_service.py tests/test_yaml_learner_service.py
git commit -m "feat: add YamlLearnerService with ruamel.yaml"
```

---

## Task 2: CategorySuggestionService

**Files:**
- Create: `backend/app/services/category_suggestion_service.py`
- Create: `backend/tests/test_category_suggestion_service.py`

---

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_category_suggestion_service.py`:

```python
"""Tests for CategorySuggestionService — all LLM calls are mocked."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.services.category_suggestion_service import (
    AddSynonymSuggestion,
    CategorySuggestionService,
    NewCategorySuggestion,
)
from app.services.llm_service import LLMUnavailableError


def _mock_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture
def db():
    return MagicMock(spec=Session)


@pytest.fixture
def svc(db):
    with patch("app.services.category_suggestion_service.OpenAI"):
        s = CategorySuggestionService(db)
    return s


def test_returns_add_synonym_suggestion(svc, db):
    payload = json.dumps({
        "suggestions": [
            {"type": "add_synonym", "category_slug": "food", "synonym": "бургер кинг"}
        ]
    })
    svc._client.chat.completions.create.return_value = _mock_response(payload)
    with patch("app.services.category_suggestion_service.TransactionRepository") as MockRepo:
        MockRepo.return_value.list_for_user.return_value = []
        results = svc.get_suggestions(123)
    assert len(results) == 1
    assert isinstance(results[0], AddSynonymSuggestion)
    assert results[0].category_slug == "food"
    assert results[0].synonym == "бургер кинг"


def test_returns_new_category_suggestion(svc, db):
    payload = json.dumps({
        "suggestions": [
            {"type": "new_category", "slug": "sport", "transaction_type": "expense", "synonyms": ["gym", "фитнес"]}
        ]
    })
    svc._client.chat.completions.create.return_value = _mock_response(payload)
    with patch("app.services.category_suggestion_service.TransactionRepository") as MockRepo:
        MockRepo.return_value.list_for_user.return_value = []
        results = svc.get_suggestions(123)
    assert len(results) == 1
    assert isinstance(results[0], NewCategorySuggestion)
    assert results[0].slug == "sport"
    assert results[0].synonyms == ["gym", "фитнес"]


def test_empty_suggestions(svc, db):
    payload = json.dumps({"suggestions": []})
    svc._client.chat.completions.create.return_value = _mock_response(payload)
    with patch("app.services.category_suggestion_service.TransactionRepository") as MockRepo:
        MockRepo.return_value.list_for_user.return_value = []
        results = svc.get_suggestions(123)
    assert results == []


def test_llm_error_raises(svc, db):
    from openai import APIError
    svc._client.chat.completions.create.side_effect = APIError(
        message="500", request=MagicMock(), body=None
    )
    with patch("app.services.category_suggestion_service.TransactionRepository") as MockRepo:
        MockRepo.return_value.list_for_user.return_value = []
        with pytest.raises(LLMUnavailableError):
            svc.get_suggestions(123)
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
cd backend && pytest tests/test_category_suggestion_service.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement CategorySuggestionService**

Create `backend/app/services/category_suggestion_service.py`:

```python
"""Calls LLM to suggest improvements to categories.yaml."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal

from openai import APIError, OpenAI
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.repositories.transaction_repository import TransactionRepository
from app.services.config_loader import load_yaml
from app.services.llm_service import LLMUnavailableError

logger = logging.getLogger(__name__)


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
    def __init__(self, db: Session) -> None:
        self.db = db
        settings = get_settings()
        self._client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.groq_api_key,
            timeout=60.0,
        )
        self._model = settings.llm_model
        self._categories_config = load_yaml("categories.yaml")

    def get_suggestions(self, telegram_user_id: int) -> list[Suggestion]:
        transactions = TransactionRepository(self.db).list_for_user(
            telegram_user_id, limit=200, offset=0, period="month"
        )
        system_prompt = self._build_prompt(transactions)
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Проанализируй транзакции и предложи улучшения."},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
        except APIError as exc:
            logger.error("LLM error in CategorySuggestionService: %s", exc)
            raise LLMUnavailableError(str(exc)) from exc

        raw = response.choices[0].message.content or ""
        return self._parse(raw)

    def _build_prompt(self, transactions: list) -> str:
        categories = self._categories_config["ru"]["categories"]
        cat_lines = "\n".join(
            f"- {c['slug']}: {', '.join(str(s) for s in c['synonyms'][:5])}"
            for c in categories
        )
        tx_lines = "\n".join(
            f"{tx.created_at.strftime('%d.%m')}: {tx.category} | {tx.description or ''}"
            for tx in transactions
        ) or "нет транзакций"
        return (
            f"Текущие категории:\n{cat_lines}\n\n"
            f"Транзакции:\n{tx_lines}\n\n"
            "Найди слова в описаниях, которых нет в синонимах, и транзакции с категорией 'other'.\n"
            'Верни JSON: {"suggestions": ['
            '{"type":"add_synonym","category_slug":"food","synonym":"бургер кинг"} | '
            '{"type":"new_category","slug":"sport","transaction_type":"expense","synonyms":["gym","фитнес"]}]}\n'
            "Не более 10 предложений. Только значимые улучшения."
        )

    def _parse(self, raw: str) -> list[Suggestion]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMUnavailableError("invalid JSON from LLM") from exc

        results: list[Suggestion] = []
        for item in data.get("suggestions") or []:
            t = item.get("type")
            if t == "add_synonym":
                slug = item.get("category_slug", "")
                syn = item.get("synonym", "")
                if slug and syn:
                    results.append(AddSynonymSuggestion(type="add_synonym", category_slug=slug, synonym=syn))
            elif t == "new_category":
                slug = item.get("slug", "")
                tx_type = item.get("transaction_type", "expense")
                syns = item.get("synonyms") or []
                if slug and syns:
                    results.append(NewCategorySuggestion(type="new_category", slug=slug, tx_type=tx_type, synonyms=syns))
        return results
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
cd backend && pytest tests/test_category_suggestion_service.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/services/category_suggestion_service.py tests/test_category_suggestion_service.py
git commit -m "feat: add CategorySuggestionService"
```

---

## Task 3: Category correction flow

**Files:**
- Modify: `backend/app/services/transaction_service.py` — add `update_category()`
- Modify: `backend/app/telegram/keyboards.py` — add `saved_actions_keyboard`, `category_grid_keyboard`
- Modify: `backend/app/telegram/bot_service.py` — add `handle_category_correction()`
- Modify: `backend/app/telegram/runtime.py` — modify `_send_saved_with_undo`, add `catfix_callback_handler`, register handler
- Create: `backend/tests/test_handlers_category_correction.py`

---

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_handlers_category_correction.py`:

```python
"""Tests for category correction callback flow."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.telegram.bot_service import TelegramBotService


@pytest.fixture
def db():
    return MagicMock(spec=Session)


@pytest.fixture
def svc(db):
    return TelegramBotService(db)


def _mock_tx(description="кофе старбакс", category="food"):
    tx = MagicMock()
    tx.description = description
    tx.category = category
    return tx


def test_correction_updates_transaction(svc):
    tx_id = str(uuid4())
    with patch.object(svc.transaction_service, "update_category", return_value=_mock_tx()) as mock_update:
        result = svc.handle_category_correction(123, tx_id, "transport")
    mock_update.assert_called_once_with(123, tx_id, "transport")
    assert result["message"]


def test_correction_adds_synonym_to_yaml(svc):
    tx_id = str(uuid4())
    tx = _mock_tx(description="бургер кинг 500", category="food")
    with patch.object(svc.transaction_service, "update_category", return_value=tx):
        with patch("app.telegram.bot_service.YamlLearnerService") as MockLearner:
            svc.handle_category_correction(123, tx_id, "food")
    MockLearner.return_value.add_synonym.assert_called_once_with("food", "бургер")


def test_correction_skips_yaml_on_empty_description(svc):
    tx_id = str(uuid4())
    tx = _mock_tx(description="", category="food")
    with patch.object(svc.transaction_service, "update_category", return_value=tx):
        with patch("app.telegram.bot_service.YamlLearnerService") as MockLearner:
            svc.handle_category_correction(123, tx_id, "food")
    MockLearner.return_value.add_synonym.assert_not_called()


def test_correction_skips_yaml_on_stopword(svc):
    tx_id = str(uuid4())
    tx = _mock_tx(description="оплата услуг", category="housing")
    with patch.object(svc.transaction_service, "update_category", return_value=tx):
        with patch("app.telegram.bot_service.YamlLearnerService") as MockLearner:
            svc.handle_category_correction(123, tx_id, "housing")
    MockLearner.return_value.add_synonym.assert_not_called()
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
cd backend && pytest tests/test_handlers_category_correction.py -v
```
Expected: `AttributeError` — `update_category` / `handle_category_correction` not defined

- [ ] **Step 3: Add `update_category` to TransactionService**

`TransactionService` already has `self.repository = TransactionRepository(db)` in `__init__`, and `TransactionRepository` already has `get(telegram_user_id, transaction_id)`. Use them:

Read `backend/app/services/transaction_service.py`, find the end of the class, add:

```python
def update_category(self, telegram_user_id: int, transaction_id: str, new_category: str):
    """Update the category of a transaction. Returns the updated transaction or None."""
    from uuid import UUID
    return self.repository.update(
        telegram_user_id, UUID(transaction_id), {"category": new_category}
    )
```

- [ ] **Step 4: Add `handle_category_correction` to bot_service.py**

At the top of `backend/app/telegram/bot_service.py`, the import section already has what's needed. Add this method to `TelegramBotService`:

```python
def handle_category_correction(self, telegram_user_id: int, transaction_id: str, new_category: str) -> dict:
    from app.services.yaml_learner_service import YamlLearnerService
    tx = self.transaction_service.update_category(telegram_user_id, transaction_id, new_category)
    if tx is None:
        return {"message": "Транзакция не найдена."}
    if tx.description:
        keyword = _extract_keyword(tx.description)
        if keyword:
            YamlLearnerService().add_synonym(new_category, keyword)
    return {"message": f"✅ Категория изменена на <b>{new_category}</b>"}
```

Add module-level helper at the bottom of `bot_service.py` (outside the class):

```python
_KEYWORD_STOPLIST = {
    "оплата", "перевод", "платёж", "платеж", "покупка",
    "списание", "зачисление", "банк", "карта", "счёт", "счет",
}


def _extract_keyword(description: str) -> str | None:
    """Return first meaningful token from description, or None."""
    for token in description.lower().split():
        token = token.strip(".,!?;:()")
        if len(token) >= 3 and token not in _KEYWORD_STOPLIST:
            return token
    return None
```

- [ ] **Step 5: Run tests — verify PASS**

```bash
cd backend && pytest tests/test_handlers_category_correction.py -v
```
Expected: 4 passed

- [ ] **Step 6: Add keyboards**

In `backend/app/telegram/keyboards.py`, add after the `undo_inline_keyboard` function:

```python
def saved_actions_keyboard(transaction_ids: list[str], correction_tx_id: str) -> InlineKeyboardMarkup:
    """Undo + category correction buttons for a saved transaction."""
    ids_str = ",".join(transaction_ids)
    return InlineKeyboardMarkup([[
        _btn("↩ Отменить", f"undo:{ids_str}"),
        _btn("✏️ Категория", f"catfix:change:{correction_tx_id}"),
    ]])


def category_grid_keyboard(tx_id: str, slugs: list[str]) -> InlineKeyboardMarkup:
    """Grid of category slug buttons for correction flow."""
    rows = []
    for i in range(0, len(slugs), 3):
        rows.append([_btn(slug, f"catfix:set:{tx_id}:{slug}") for slug in slugs[i:i+3]])
    rows.append([_btn("❌ Отмена", f"catfix:cancel:{tx_id}")])
    return InlineKeyboardMarkup(rows)
```

- [ ] **Step 7: Wire runtime.py**

**7a.** In `backend/app/telegram/runtime.py` imports section, add to the keyboard imports:
```python
    saved_actions_keyboard,
    category_grid_keyboard,
```

**7b.** Modify `_send_saved_with_undo` signature and body (around line 459).

> **Note:** `_send_saved_with_undo` is called from multiple places (lines ~553, 564, 636, 702, 1067, 1264). All other call sites omit `correction_tx_id` — they keep working unchanged because it defaults to `None`. Only the call at ~line 1121 (single saved text transaction) passes `correction_tx_id`. Do NOT change the other call sites.
```python
async def _send_saved_with_undo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    transaction_ids: list[str],
    correction_tx_id: str | None = None,
) -> None:
    kb = (
        saved_actions_keyboard(transaction_ids, correction_tx_id)
        if correction_tx_id
        else undo_inline_keyboard(transaction_ids)
    )
    msg = await update.effective_message.reply_text(
        text,
        reply_markup=kb,
        parse_mode="HTML",
    )
    asyncio.create_task(
        _auto_remove_keyboard(context.bot, msg.chat_id, msg.message_id)
    )
```

**7c.** At line 1121-1127, pass `correction_tx_id`:
```python
    if action == "saved" and response.get("saved_transaction_id"):
        await _send_saved_with_undo(
            update, context,
            response["message"],
            [response["saved_transaction_id"]],
            correction_tx_id=response["saved_transaction_id"],
        )
        return
```

**7d.** Add `catfix_callback_handler` function in `runtime.py` (near the other callback handlers):

```python
async def catfix_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    parts = query.data.split(":")
    if len(parts) < 3:
        return
    sub = parts[1]   # "change", "set", "cancel"
    tx_id = parts[2]

    if sub == "change":
        from app.services.config_loader import load_yaml
        cats = load_yaml("categories.yaml")
        slugs = [c["slug"] for c in cats["ru"]["categories"]]
        await query.edit_message_reply_markup(
            reply_markup=category_grid_keyboard(tx_id, slugs)
        )

    elif sub == "set" and len(parts) >= 4:
        slug = parts[3]
        user_id = update.effective_user.id
        with SessionLocal() as db:
            service = TelegramBotService(db)
            result = service.handle_category_correction(user_id, tx_id, slug)
        await query.edit_message_text(result["message"], parse_mode="HTML")

    elif sub == "cancel":
        await query.edit_message_reply_markup(reply_markup=None)
```

**7e.** Register the handler in `run_polling` (after existing `CallbackQueryHandler` registrations):
```python
    application.add_handler(CallbackQueryHandler(catfix_callback_handler, pattern=r"^catfix:"))
```

- [ ] **Step 8: Smoke test**

Start the bot, send a transaction (e.g. "кофе 200"), verify the message has both "↩ Отменить" and "✏️ Категория" buttons. Tap "✏️ Категория" — should show a grid of slugs. Tap a slug — message should update to "✅ Категория изменена на…".

- [ ] **Step 9: Commit**

```bash
cd backend && git add app/services/transaction_service.py app/repositories/transaction_repository.py app/telegram/bot_service.py app/telegram/keyboards.py app/telegram/runtime.py tests/test_handlers_category_correction.py
git commit -m "feat: add category correction flow with YAML synonym learning"
```

---

## Task 4: /improve_categories command + suggestion flow

**Files:**
- Modify: `backend/app/telegram/keyboards.py` — add `suggestion_keyboard`
- Modify: `backend/app/telegram/handlers.py` — add `_pending_suggestions` store + accessors
- Modify: `backend/app/telegram/bot_service.py` — add `improve_categories()`, `handle_suggestion_callback()`
- Modify: `backend/app/telegram/runtime.py` — add command + `sugg_callback_handler`, register both

---

> **Architecture note:** The spec places `/improve_categories` handling in `handlers.py`. In practice, business logic lives in `bot_service.py` and async wiring in `runtime.py`, matching all other commands. `_pending_suggestions` store is in `handlers.py` as specified; command handler and callbacks are in `bot_service.py`/`runtime.py`.

> **Testing note:** Task 4 async handlers (`improve_categories_command`, `sugg_callback_handler`) are not unit-tested here — they are thin async wrappers around `bot_service` methods already tested in Task 3. The integration is verified via smoke test in Step 6.

- [ ] **Step 1: Add `suggestion_keyboard` to keyboards.py**

In `backend/app/telegram/keyboards.py`, add after `category_grid_keyboard`:

```python
def suggestion_keyboard(key: str) -> InlineKeyboardMarkup:
    """Yes/No buttons for an LLM suggestion. key = 'sugg:{uuid}'"""
    return InlineKeyboardMarkup([[
        _btn("✅ Да", f"{key}_yes"),
        _btn("❌ Нет", f"{key}_no"),
    ]])
```

- [ ] **Step 2: Add `_pending_suggestions` store to handlers.py**

In `backend/app/telegram/handlers.py`, add after the existing `_pending_store` block (around line 40):

```python
# ---------------------------------------------------------------------------
# Module-level store for pending LLM category suggestions: key → Suggestion
# Lost on bot restart — acceptable. Key format: "sugg:{8-char hex}"
# ---------------------------------------------------------------------------
from app.services.category_suggestion_service import Suggestion as _Suggestion

_pending_suggestions: dict[str, "_Suggestion"] = {}


def _sugg_set(key: str, suggestion: "_Suggestion") -> None:
    _pending_suggestions[key] = suggestion


def _sugg_pop(key: str) -> "_Suggestion | None":
    return _pending_suggestions.pop(key, None)
```

- [ ] **Step 3: Add improve_categories + handle_suggestion_callback to bot_service.py**

In `backend/app/telegram/bot_service.py`, add these methods to `TelegramBotService`:

```python
def improve_categories(self, telegram_user_id: int) -> list[dict]:
    """Call LLM and return suggestion dicts ready to send as Telegram messages.

    Each dict: {"key": "sugg:abc12345", "message": "Добавить 'X' как синоним Y?"}
    Side-effect: stores suggestions in handlers._pending_suggestions.
    """
    import uuid
    from app.services.category_suggestion_service import (
        AddSynonymSuggestion, CategorySuggestionService, NewCategorySuggestion,
    )
    from app.telegram.handlers import _sugg_set

    service = CategorySuggestionService(self.db)
    suggestions = service.get_suggestions(telegram_user_id)

    result = []
    for s in suggestions:
        key = f"sugg:{uuid.uuid4().hex[:8]}"
        _sugg_set(key, s)
        if isinstance(s, AddSynonymSuggestion):
            msg = f"Добавить <b>'{s.synonym}'</b> как синоним категории <i>{s.category_slug}</i>?"
        else:  # NewCategorySuggestion
            syn_preview = ", ".join(s.synonyms[:4])
            msg = f"Создать новую категорию <b>'{s.slug}'</b> ({syn_preview})?"
        result.append({"key": key, "message": msg})
    return result

def handle_suggestion_callback(self, key: str, accepted: bool) -> dict:
    """Apply or discard a pending suggestion. Returns status message."""
    from app.services.category_suggestion_service import AddSynonymSuggestion, NewCategorySuggestion
    from app.services.yaml_learner_service import YamlLearnerService
    from app.telegram.handlers import _sugg_pop

    suggestion = _sugg_pop(key)
    if suggestion is None:
        return {"message": "Предложение уже обработано или устарело."}

    if not accepted:
        return {"message": "❌ Пропущено."}

    learner = YamlLearnerService()
    if isinstance(suggestion, AddSynonymSuggestion):
        learner.add_synonym(suggestion.category_slug, suggestion.synonym)
        return {"message": f"✅ Синоним <b>'{suggestion.synonym}'</b> добавлен в <i>{suggestion.category_slug}</i>."}
    else:  # NewCategorySuggestion
        learner.add_category(suggestion.slug, suggestion.tx_type, suggestion.synonyms)
        return {"message": f"✅ Категория <b>'{suggestion.slug}'</b> создана."}
```

- [ ] **Step 4: Wire runtime.py — command handler**

**4a.** Add to imports in `runtime.py`:
```python
    suggestion_keyboard,
```

**4b.** Add `improve_categories_command` async handler function:

```python
async def improve_categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None:
        return
    user_id = update.effective_user.id
    await update.effective_message.reply_text("Анализирую транзакции…")
    with SessionLocal() as db:
        service = TelegramBotService(db)
        try:
            suggestions = service.improve_categories(user_id)
        except Exception as exc:
            logger.error("improve_categories error: %s", exc)
            await update.effective_message.reply_text("Не удалось получить предложения. Попробуй позже.")
            return

    if not suggestions:
        await update.effective_message.reply_text("Улучшений не найдено — категории уже хорошо настроены.")
        return

    for s in suggestions:
        await update.effective_message.reply_text(
            s["message"],
            reply_markup=suggestion_keyboard(s["key"]),
            parse_mode="HTML",
        )
```

**4c.** Add `sugg_callback_handler`:

```python
async def sugg_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    # callback_data: "sugg:abc12345_yes" or "sugg:abc12345_no"
    raw = query.data  # e.g. "sugg:abc12345_yes"
    key = raw.rsplit("_", 1)[0]   # "sugg:abc12345"
    accepted = raw.endswith("_yes")

    with SessionLocal() as db:
        service = TelegramBotService(db)
        result = service.handle_suggestion_callback(key, accepted)

    await query.edit_message_text(result["message"], parse_mode="HTML")
```

**4d.** Register in `run_polling` (add after `catfix:` handler):
```python
    application.add_handler(CommandHandler("improve_categories", improve_categories_command))
    application.add_handler(CallbackQueryHandler(sugg_callback_handler, pattern=r"^sugg:"))
```

- [ ] **Step 5: Run all tests**

```bash
cd backend && pytest -v
```
Expected: 233+ passed, 3 pre-existing failures unchanged.

- [ ] **Step 6: Smoke test**

Send `/improve_categories` — should reply "Анализирую транзакции…" then send suggestion messages with ✅/❌ buttons. Tap ✅ — message updates to "✅ Синоним '...' добавлен". Check `backend/app/config/categories.yaml` to confirm the change was written.

- [ ] **Step 7: Commit**

```bash
cd backend && git add app/services/category_suggestion_service.py app/telegram/keyboards.py app/telegram/handlers.py app/telegram/bot_service.py app/telegram/runtime.py
git commit -m "feat: add /improve_categories command with LLM suggestions and YAML updates"
```
