# Categories UI — Design Spec

**Date:** 2026-03-26
**Scope:** Telegram bot (phase 1). WebApp (phase 2, not in this spec).
**Entry point:** Main menu button "🗂 Категории"

---

## Goal

Allow users to manage expense/income categories directly in the Telegram bot:
- Rename built-in categories
- Change emoji for any category
- Hide categories (remove from selection keyboards)
- Create custom categories
- Delete custom categories (with transaction reassignment)

---

## Data Layer

### New table: `category_settings`

| Column | Type | Notes |
|---|---|---|
| id | Integer PK autoincrement | |
| telegram_user_id | BigInteger, indexed | |
| slug | String(50) | unique per user |
| name_ru | String(100) | display name |
| emoji | String(10) | single emoji |
| tx_type | String(10) | `expense` / `income` / `both` |
| is_hidden | Boolean, default False | hides from selection UIs |
| is_custom | Boolean, default False | user-created, can be deleted |
| created_at | DateTime | |
| updated_at | DateTime | |

**Unique constraint:** `(telegram_user_id, slug)`

**Lazy creation:** Built-in categories (food, transport, etc.) are NOT pre-populated. They are created in `category_settings` only on first edit. Until then, defaults from `CATEGORY_EMOJI` and `formatter.category_label()` are used.

**Custom categories** are written to `category_settings` immediately upon creation with `is_custom=True`.

### Alembic migration

New revision file in `backend/alembic/versions/`.

---

## Backend Service: `CategoryService`

File: `backend/app/services/category_service.py`

```
get_all(user_id) -> list[CategoryRow]
  Returns merged list: built-in defaults overridden by user's category_settings rows.
  Groups by tx_type for display.

get_or_default(user_id, slug) -> CategoryRow
  Returns user's override if exists, else built-in default.

upsert(user_id, slug, **fields) -> CategoryRow
  Create or update category_settings row.

delete(user_id, slug) -> None
  Only allowed for is_custom=True rows.

reassign_and_delete(user_id, from_slug, to_slug, db) -> int
  Update all transactions from from_slug → to_slug, then delete category.

get_categories_for_keyboard(user_id, tx_type) -> list[CategoryRow]
  Returns non-hidden categories filtered by tx_type (or both).
```

`CategoryRow` dataclass: `slug, name_ru, emoji, tx_type, is_hidden, is_custom`

---

## Bot Handlers

### Navigation

Add to `main_menu_inline_keyboard()`:
```python
[_btn(MENU_BTN_CATEGORIES, "nav:categories"), _btn(MENU_BTN_ADVISOR, "nav:advisor")]
```
(replaces the current Budgets+Advisor row, moving Categories next to Advisor)

### Callback flow

```
nav:categories
  → CategoryService.get_all(user_id)
  → message: list of categories grouped (Расходы / Доходы / Кастомные)
  → keyboard: categories_nav_keyboard(categories_by_type)  [already in keyboards.py]

categories:noop:{slug}
  → no-op (informational button, ignore)

categories:edit:{slug}
  → message: "Категория: {emoji} {name_ru}"
  → keyboard: category_edit_keyboard(slug, is_custom)  [already in keyboards.py]

categories:rename:{slug}
  → set pending state: {action: "rename", slug: slug}
  → message: "Введи новое название для категории {name_ru}:"
  → keyboard: cancel_keyboard("nav:categories")

categories:emoji:{slug}
  → set pending state: {action: "emoji", slug: slug}
  → message: "Отправь один эмодзи для категории {name_ru}:"
  → keyboard: cancel_keyboard("nav:categories")

categories:add
  → set pending state: {action: "add_type"}
  → message: "Выбери тип новой категории:"
  → keyboard: category_type_keyboard()  [already in keyboards.py]

categories:set_type:{tx_type}
  → update pending state: {action: "add_name", tx_type: tx_type}
  → message: "Введи название новой категории:"
  → keyboard: cancel_keyboard("nav:categories")

categories:delete:{slug}
  → if category has transactions:
      → message: "Перенести транзакции в другую категорию перед удалением:"
      → keyboard: category_reassign_keyboard(same_type_categories, slug)
  → else:
      → keyboard: category_delete_confirm_keyboard(slug)

categories:reassign:{from}__{to}
  → CategoryService.reassign_and_delete(user_id, from, to)
  → message: "Готово. Транзакции перенесены в {to_name}, категория удалена."
  → keyboard: done_keyboard("nav:categories")

categories:confirm_delete:{slug}
  → CategoryService.delete(user_id, slug)
  → message: "Категория удалена."
  → keyboard: done_keyboard("nav:categories")
```

### Text input handling (pending state)

In `bot_service.py`, add module-level `_pending_categories: dict[int, dict]`.

In `handle_text()`, check pending categories state **before** parsing as transaction:

```python
pending_cat = _cat_store_get(user_id)
if pending_cat:
    return self._handle_category_input(user_id, text, pending_cat)
```

`_handle_category_input` cases:
- `action == "rename"` → `CategoryService.upsert(user_id, slug, name_ru=text)`
- `action == "emoji"` → validate single emoji → `CategoryService.upsert(user_id, slug, emoji=text)`
- `action == "add_name"` → `CategoryService.upsert(user_id, new_slug, name_ru=text, tx_type=..., is_custom=True, emoji="•")`

After each action → show updated category screen or nav:categories.

---

## Integration Points

### `formatter.py`

Add standalone helper (no DB dependency):
```python
def resolve_category_label(slug: str, category_overrides: dict[str, str]) -> str:
    return category_overrides.get(slug) or CATEGORY_LABELS.get(slug, slug)
```

Callers load overrides via `CategoryService.get_all(user_id)` before calling formatter.

### Hidden categories

`CategoryService.get_categories_for_keyboard(user_id, tx_type)` excludes `is_hidden=True` rows. Use this in:
- `low_confidence_category_keyboard()`
- `edit_categories_keyboard()`
- `category_grid_keyboard()` (catfix flow)
- Evening check-in category picker

### Custom categories in parser

Custom categories are **not** auto-recognized by `ParserService` YAML patterns in v1. Users select them manually from keyboards. This is acceptable for the initial release.

---

## Files Changed

| File | Change |
|---|---|
| `backend/app/models/category_settings.py` | New model |
| `backend/alembic/versions/YYYYMMDD_category_settings.py` | New migration |
| `backend/app/services/category_service.py` | New service |
| `backend/app/telegram/handlers.py` | New `categories:*` and `nav:categories` handlers |
| `backend/app/telegram/keyboards.py` | Add Categories button to main menu |
| `backend/app/telegram/bot_service.py` | Pending state + `handle_text` update |
| `backend/app/telegram/formatter.py` | `resolve_category_label` helper |

---

## Out of Scope (Phase 1)

- WebApp `/categories` page (phase 2)
- API endpoint `GET /categories` for frontend
- Auto-recognition of custom categories by parser
- Color customization (deferred)
- Category sort order (deferred)
