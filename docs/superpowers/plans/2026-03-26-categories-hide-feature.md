# Categories Hide/Show Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the ability to hide/show categories in the Telegram bot so they don't appear in selection keyboards while keeping historical transactions intact.

**Architecture:** Add `is_hidden` column to the `UserCategory` model, add `toggle_hidden()` and `get_visible_for_type()` to `CategoryService`, expose a toggle button in the category edit keyboard, add the callback handler, and filter hidden categories at four call sites.

**Tech Stack:** Python, SQLAlchemy, Alembic, python-telegram-bot, pytest

---

## File Map

| File | Change |
|---|---|
| `backend/app/models/user_category.py` | Add `is_hidden` column |
| `backend/alembic/versions/20260326_0001_add_is_hidden_to_user_categories.py` | New migration |
| `backend/app/services/category_service.py` | Add `toggle_hidden()`, `get_visible_for_type()` |
| `backend/app/telegram/keyboards.py` | Update `category_edit_keyboard` + `low_confidence_category_keyboard` + `edit_categories_keyboard` |
| `backend/app/telegram/runtime.py` | Handler `categories:toggle_hidden` + update 3 call sites |
| `backend/app/services/scheduler_service.py` | Filter hidden categories before `evening_checkin_keyboard` |
| `backend/tests/test_category_service.py` | New test file |

---

## Task 1: Add `is_hidden` column to model

**Files:**
- Modify: `backend/app/models/user_category.py`

- [ ] **Step 1: Add the column**

In `user_category.py`, after the `sort_order` field (line 23), add:

```python
is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

The import for `Boolean` is already in the file.

- [ ] **Step 2: Create Alembic migration**

```bash
cd backend && alembic revision -m "add_is_hidden_to_user_categories"
```

Edit the generated file — set `revision` id, fill `upgrade()` and `downgrade()`:

```python
def upgrade() -> None:
    op.add_column(
        "user_categories",
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )

def downgrade() -> None:
    op.drop_column("user_categories", "is_hidden")
```

- [ ] **Step 3: Apply migration**

```bash
cd backend && alembic upgrade head
```

Expected: `Running upgrade ... -> <rev>, add_is_hidden_to_user_categories`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/user_category.py backend/alembic/versions/
git commit -m "feat(categories): add is_hidden column to user_categories"
```

---

## Task 2: Add service methods

**Files:**
- Modify: `backend/app/services/category_service.py`
- Create: `backend/tests/test_category_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_category_service.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.services.category_service import CategoryService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


USER_ID = 12345


def test_toggle_hidden_hides_category(db):
    svc = CategoryService(db)
    svc.ensure_seeded(USER_ID)
    cat = svc.toggle_hidden(USER_ID, "food")
    assert cat is not None
    assert cat.is_hidden is True


def test_toggle_hidden_shows_hidden_category(db):
    svc = CategoryService(db)
    svc.ensure_seeded(USER_ID)
    svc.toggle_hidden(USER_ID, "food")   # hide
    cat = svc.toggle_hidden(USER_ID, "food")  # show again
    assert cat is not None
    assert cat.is_hidden is False


def test_toggle_hidden_unknown_slug_returns_none(db):
    svc = CategoryService(db)
    svc.ensure_seeded(USER_ID)
    result = svc.toggle_hidden(USER_ID, "nonexistent_slug_xyz")
    assert result is None


def test_get_visible_for_type_excludes_hidden(db):
    svc = CategoryService(db)
    svc.ensure_seeded(USER_ID)
    svc.toggle_hidden(USER_ID, "food")
    visible = svc.get_visible_for_type(USER_ID, "expense")
    slugs = [c.slug for c in visible]
    assert "food" not in slugs
    assert "transport" in slugs


def test_get_visible_for_type_includes_both(db):
    svc = CategoryService(db)
    svc.ensure_seeded(USER_ID)
    visible = svc.get_visible_for_type(USER_ID, "expense")
    slugs = [c.slug for c in visible]
    assert "other" in slugs  # type="both" should be included


def test_get_visible_for_type_income_excludes_expenses(db):
    svc = CategoryService(db)
    svc.ensure_seeded(USER_ID)
    visible = svc.get_visible_for_type(USER_ID, "income")
    types = {c.type for c in visible}
    assert "expense" not in types
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_category_service.py -v
```

Expected: `ImportError` or `AttributeError: CategoryService has no attribute toggle_hidden`

- [ ] **Step 3: Implement methods in CategoryService**

Add to `backend/app/services/category_service.py` after `change_emoji()`:

```python
def toggle_hidden(self, telegram_user_id: int, slug: str) -> "UserCategory | None":
    """Toggle is_hidden on a category. Seeds built-ins first if needed."""
    cat = self._repo.get_by_slug(telegram_user_id, slug)
    if cat is None:
        self.ensure_seeded(telegram_user_id)
        cat = self._repo.get_by_slug(telegram_user_id, slug)
    if cat is None:
        return None
    updated = self._repo.update(cat.id, is_hidden=not cat.is_hidden)
    self.db.commit()
    return updated

def get_visible_for_type(self, telegram_user_id: int, tx_type: str) -> "list[UserCategory]":
    """Return non-hidden categories matching tx_type or 'both'."""
    all_cats = self._repo.get_all(telegram_user_id)
    return [
        c for c in all_cats
        if not c.is_hidden and c.type in (tx_type, "both")
    ]
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd backend && pytest tests/test_category_service.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/category_service.py backend/tests/test_category_service.py
git commit -m "feat(categories): add toggle_hidden and get_visible_for_type to CategoryService"
```

---

## Task 3: Update keyboards

**Files:**
- Modify: `backend/app/telegram/keyboards.py`

- [ ] **Step 1: Update `category_edit_keyboard` signature**

Current (line ~164):
```python
def category_edit_keyboard(slug: str, is_custom: bool) -> InlineKeyboardMarkup:
    rows = [
        [_btn("✏️ Изменить название", f"categories:rename:{slug}")],
        [_btn("🎨 Изменить emoji", f"categories:emoji:{slug}")],
    ]
    if is_custom:
        rows.append([_btn("🗑 Удалить", f"categories:delete:{slug}")])
    rows.append([_back_btn("nav:categories")])
    return InlineKeyboardMarkup(rows)
```

Replace with:
```python
def category_edit_keyboard(slug: str, is_custom: bool, is_hidden: bool) -> InlineKeyboardMarkup:
    hide_label = "👁 Показать" if is_hidden else "🙈 Скрыть"
    rows = [
        [_btn("✏️ Изменить название", f"categories:rename:{slug}")],
        [_btn("🎨 Изменить emoji", f"categories:emoji:{slug}")],
        [_btn(hide_label, f"categories:toggle_hidden:{slug}")],
    ]
    if is_custom:
        rows.append([_btn("🗑 Удалить", f"categories:delete:{slug}")])
    rows.append([_back_btn("nav:categories")])
    return InlineKeyboardMarkup(rows)
```

- [ ] **Step 2: Update `low_confidence_category_keyboard` signature**

Add optional `categories` parameter. Current function (line ~399) hardcodes slugs. Update:

```python
def low_confidence_category_keyboard(
    tx_type: str, amount: str, categories: list[str] | None = None
) -> InlineKeyboardMarkup:
    if categories is not None:
        slugs = categories
    elif tx_type == "income":
        slugs = ["salary", "freelance", "bonus", "transfer", "refund", "other_income"]
    else:
        slugs = ["food", "transport", "housing", "health", "entertainment",
                 "subscriptions", "shopping", "other"]
    # ... rest of function unchanged
```

- [ ] **Step 3: Update `edit_categories_keyboard` signature**

Current function (line ~539) hardcodes slugs. Add optional `categories` parameter:

```python
def edit_categories_keyboard(
    transaction_id: str, categories: list[tuple[str, str]] | None = None
) -> InlineKeyboardMarkup:
    if categories is not None:
        slugs = categories
    else:
        slugs = [
            ("food", "🍽"), ("transport", "🚌"), ("housing", "🏠"), ("health", "💊"),
            ("beauty", "✨"), ("entertainment", "🎬"), ("subscriptions", "📱"), ("shopping", "🛍"),
            ("home", "🪴"), ("telecom", "📡"), ("work", "💼"), ("education", "📚"),
            ("gifts", "🎁"), ("fees", "💳"), ("salary", "💰"), ("freelance", "🖥"),
            ("bonus", "🏆"), ("other", "•"),
        ]
    # ... rest of function unchanged
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/telegram/keyboards.py
git commit -m "feat(categories): add is_hidden toggle button and categories param to keyboards"
```

---

## Task 4: Add `toggle_hidden` handler in runtime.py

**Files:**
- Modify: `backend/app/telegram/runtime.py`

- [ ] **Step 1: Update `edit` action to pass `is_hidden`**

Find the `if action == "edit":` block (line ~293). Update the call to `category_edit_keyboard`:

```python
# Before:
reply_markup=category_edit_keyboard(slug, cat.is_custom),

# After:
reply_markup=category_edit_keyboard(slug, cat.is_custom, cat.is_hidden),
```

- [ ] **Step 2: Add `toggle_hidden` handler**

After the `if action == "reassign":` block (after line ~427), add:

```python
if action == "toggle_hidden":
    slug = param
    with SessionLocal() as db:
        _ensure_user(db, update)
        svc = CategoryService(db)
        cat = svc.toggle_hidden(user_id, slug)
    if cat is None:
        await query.answer("❌ Категория не найдена", show_alert=True)
        return
    state = "скрыта" if cat.is_hidden else "показана"
    text = f"{'🙈' if cat.is_hidden else '👁'} *{cat.emoji} {cat.name_ru}* — категория {state}.\n\nЧто изменить?"
    await query.edit_message_text(
        text,
        reply_markup=category_edit_keyboard(slug, cat.is_custom, cat.is_hidden),
        parse_mode="Markdown",
    )
    return
```

- [ ] **Step 3: Verify handler is registered**

Confirm that `categories_callback_handler` is registered in the `Application` setup with pattern `^categories:`. If it uses a prefix pattern like `^categories:`, the new `toggle_hidden` action is automatically covered — no new registration needed.

Run a quick grep to confirm:
```bash
grep -n "categories_callback_handler\|categories:" backend/app/telegram/runtime.py | tail -20
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat(categories): add toggle_hidden handler and pass is_hidden to edit keyboard"
```

---

## Task 5: Filter hidden categories at call sites

**Files:**
- Modify: `backend/app/telegram/runtime.py`
- Modify: `backend/app/services/scheduler_service.py`

- [ ] **Step 1: Filter at `low_confidence_category_keyboard` call site (runtime.py L~1053)**

Find:
```python
reply_markup=low_confidence_category_keyboard(action, amount),
```

Replace with:
```python
with SessionLocal() as _cat_db:
    _ensure_user(_cat_db, update)
    _cat_svc = CategoryService(_cat_db)
    _cat_svc.ensure_seeded(user_id)
    _visible = [c.slug for c in _cat_svc.get_visible_for_type(user_id, action)]
reply_markup=low_confidence_category_keyboard(action, amount, categories=_visible),
```

- [ ] **Step 2: Filter at `edit_categories_keyboard` call site (runtime.py L~739)**

> **Design note:** The edit keyboard shows ALL non-hidden categories (both expense and income) regardless of the transaction's type — this is intentional. It allows re-categorizing a transaction to any visible category. If scoped filtering is needed in the future, look up the transaction type first.

Find:
```python
reply_markup=edit_categories_keyboard(tx_id),
```

Replace with:
```python
with SessionLocal() as _cat_db:
    _ensure_user(_cat_db, update)
    _cat_svc = CategoryService(_cat_db)
    _cat_svc.ensure_seeded(user_id)
    _all_visible = (
        _cat_svc.get_visible_for_type(user_id, "expense")
        + _cat_svc.get_visible_for_type(user_id, "income")
    )
    # "both"-type categories appear in both lists — dedupe by slug
    seen: set[str] = set()
    _visible: list[tuple[str, str]] = []
    for c in _all_visible:
        if c.slug not in seen:
            seen.add(c.slug)
            _visible.append((c.slug, c.emoji))
reply_markup=edit_categories_keyboard(tx_id, categories=_visible),
```

- [ ] **Step 3: Filter at `category_grid_keyboard` call site (runtime.py L~194)**

Find:
```python
reply_markup=category_grid_keyboard(tx_id, _CATFIX_CATEGORIES)
```

Replace with:
```python
with SessionLocal() as _cat_db:
    _ensure_user(_cat_db, update)
    _cat_svc = CategoryService(_cat_db)
    _cat_svc.ensure_seeded(user_id)
    _all_visible = (
        [c.slug for c in _cat_svc.get_visible_for_type(user_id, "expense")]
        + [c.slug for c in _cat_svc.get_visible_for_type(user_id, "income")]
    )
    _visible_catfix = [s for s in _CATFIX_CATEGORIES if s in _all_visible]
reply_markup=category_grid_keyboard(tx_id, _visible_catfix or _CATFIX_CATEGORIES),
```

- [ ] **Step 4: Filter in scheduler_service.py**

Find the evening check-in block (line ~141–147):
```python
message, top_categories = reminder_service.build_evening_checkin(user)
if message:
    keyboard = evening_checkin_keyboard(top_categories)
```

Replace with:
```python
message, top_categories = reminder_service.build_evening_checkin(user)
if message:
    from app.services.category_service import CategoryService
    cat_svc = CategoryService(db)
    cat_svc.ensure_seeded(user.telegram_user_id)
    visible_slugs = {c.slug for c in cat_svc.get_visible_for_type(user.telegram_user_id, "expense")}
    filtered_top = [c for c in top_categories if c in visible_slugs]
    keyboard = evening_checkin_keyboard(filtered_top or top_categories)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/telegram/runtime.py backend/app/services/scheduler_service.py
git commit -m "feat(categories): filter hidden categories from all selection keyboards"
```

---

## Task 6: Run full test suite

- [ ] **Step 1: Run all backend tests**

```bash
cd backend && pytest -v
```

Expected: all tests PASS, no regressions.

- [ ] **Step 2: Fix any failures before proceeding**

If tests fail due to the `is_hidden` column missing in test DB fixtures, ensure all test fixtures that create `UserCategory` rows either set `is_hidden=False` explicitly or rely on the column default.

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -p
git commit -m "fix(categories): update test fixtures for is_hidden column"
```
