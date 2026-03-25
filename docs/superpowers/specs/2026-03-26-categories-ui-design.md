# Categories UI — Design Spec (Gap Analysis)

**Date:** 2026-03-26
**Scope:** Telegram bot (phase 1). WebApp (phase 2, out of scope).

---

## What Is Already Implemented

The categories bot UI is **largely complete**. The following exist and work:

| Component | Location | Status |
|---|---|---|
| `UserCategory` model (`user_categories` table) | `models/user_category.py` | ✅ Done |
| `CategoryService` | `services/category_service.py` | ✅ Done |
| `categories_callback_handler` | `telegram/runtime.py` L268 | ✅ Done |
| `nav:categories` in main menu | `telegram/keyboards.py` | ✅ Done |
| All category keyboards | `telegram/keyboards.py` | ✅ Done |
| Rename flow (text input via `context.user_data`) | `runtime.py` L2014 | ✅ Done |
| Emoji change flow | `runtime.py` L2033 | ✅ Done |
| Add custom category flow | `runtime.py` L2054 | ✅ Done |
| Delete with reassign flow | `runtime.py` L403 | ✅ Done |

---

## What Is Missing

### Feature: Hide / Show Category

**Goal:** Allow user to hide a category so it doesn't appear in transaction entry keyboards (add transaction, evening check-in, low-confidence pickers), while keeping historical transactions intact.

#### 1. DB: Add `is_hidden` column to `UserCategory`

```python
is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

New Alembic migration required.

#### 2. `CategoryService.toggle_hidden(telegram_user_id, slug) -> UserCategory | None`

Flips `is_hidden` on the category row. If the row doesn't exist yet (built-in category never edited), seeds it first via `ensure_seeded()` then toggles.

#### 3. `category_edit_keyboard` — add hide/show button

Current keyboard has: rename, emoji change, (delete for custom). Add a toggle row:

```
[👁 Скрыть] or [👁 Показать]   ← depends on current is_hidden state
```

Callback: `categories:toggle_hidden:{slug}`

Keyboard signature changes to:
```python
def category_edit_keyboard(slug: str, is_custom: bool, is_hidden: bool) -> InlineKeyboardMarkup
```

**Update all call sites** of `category_edit_keyboard` in `runtime.py` to pass `is_hidden` — look up the current category row before building the keyboard.

#### 4. Handler: `categories:toggle_hidden:{slug}`

In `categories_callback_handler`:
```
categories:toggle_hidden:{slug}
  → result = CategoryService.toggle_hidden(user_id, slug)
  → if result is None:
      → answer callback with "Категория не найдена" (no message edit)
  → else:
      → edit message to updated category screen with new is_hidden state
```

#### 5. Apply `is_hidden` filter in selection keyboards

`CategoryService` already has `list_categories()`. Add:
```python
def get_visible_for_type(self, telegram_user_id: int, tx_type: str) -> list[UserCategory]
```
Returns non-hidden categories for the given type (or both).

**Filtering is applied in `runtime.py` call sites** — call `get_visible_for_type()` first, then pass the filtered list to the keyboard builder. Do not change keyboard builder signatures. Apply at these locations in `runtime.py`:
- Before `low_confidence_category_keyboard()` call (low-confidence flow)
- Before `edit_categories_keyboard()` call (edit transaction flow)
- Before `evening_checkin_keyboard()` call (evening check-in scheduler)
- Before `category_grid_keyboard()` call (catfix flow)

#### 6. `toggle_hidden` edge case: unknown slug

`ensure_seeded()` seeds all system categories for the user. If after seeding `get_by_slug()` still returns `None`, the slug is invalid — method returns `None`. The handler treats `None` as a silent no-op with a callback alert.

---

## Files Changed

| File | Change |
|---|---|
| `backend/app/models/user_category.py` | Add `is_hidden` column |
| `backend/alembic/versions/YYYYMMDD_add_is_hidden_to_user_categories.py` | New migration |
| `backend/app/services/category_service.py` | Add `toggle_hidden()` and `get_visible_for_type()` |
| `backend/app/telegram/keyboards.py` | Update `category_edit_keyboard` signature + hide button |
| `backend/app/telegram/runtime.py` | Handler for `categories:toggle_hidden` + use `get_visible_for_type` in pickers |

---

## Out of Scope (Phase 1)

- WebApp `/categories` page
- API endpoint `GET /categories` for frontend
- Color customization
- Category sort order UI
- Auto-recognition of custom categories by parser
