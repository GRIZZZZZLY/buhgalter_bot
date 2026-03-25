# Consistent Navigation Design

**Date:** 2026-03-25
**Scope:** Telegram bot — eliminate dead-end screens, add consistent inline navigation

## Problem

~20 screens in `runtime.py` send messages without `reply_markup`, leaving the user with no inline buttons to navigate. The user must type `/menu` or a command to continue.

## Design Principle

**Every bot message must contain an inline keyboard.** No exceptions except temporary "processing" placeholders that get replaced.

## Navigation Keyboard Types

### 1. `done_keyboard(back_target=None)`

For confirmations and errors after completing an action.

- `back_target=None` → `[≡ Меню]`
- `back_target="nav:categories"` → `[← Назад] [≡ Меню]`

```python
def done_keyboard(back_target: str | None = None) -> InlineKeyboardMarkup:
    if back_target:
        return InlineKeyboardMarkup([[_back_btn(back_target), _menu_btn()]])
    return InlineKeyboardMarkup([[_menu_btn()]])
```

### 2. `advisor_keyboard()`

For financial QA / advisor responses.

```python
def advisor_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_btn("📊 Сводка", "nav:stats"), _menu_btn()]])
```

## Changes Map

### File: `backend/app/telegram/keyboards.py`

Add two new functions: `done_keyboard()` and `advisor_keyboard()`.

### File: `backend/app/telegram/runtime.py`

#### Confirmations → `done_keyboard()`

| Line | Message | back_target |
|------|---------|-------------|
| L343 | "✅ Категория создана!" | `None` |
| L390 | "✅ Категория удалена." | `None` |
| L407 | "✅ Транзакции перенесены, категория удалена." | `None` |
| L660 | "✅ Удалил запись." | `None` |

#### Errors → `done_keyboard(back_target=...)`

| Line | Message | back_target |
|------|---------|-------------|
| L330 | "❌ Что-то пошло не так" | `"nav:categories"` |
| L354 | "❌ Нельзя удалить системную категорию." | `"nav:categories"` |
| L388 | "❌ {e}" (category delete error) | `"nav:categories"` |
| L395 | "❌ Неверный формат." | `"nav:categories"` |
| L405 | "❌ {e}" (reassign error) | `"nav:categories"` |
| L570 | "❌ Не нашёл пользователя." | `None` |
| L662 | "❌ Не нашёл запись." | `"nav:menu"` |
| L2053 | "❌ Не понял сумму" | contextual |
| L2301 | "Некорректный callback payload." | `None` |

#### Advisor/QA → `advisor_keyboard()`

| Line | Context |
|------|---------|
| L525 | `/ask` command response |
| L2282 | Advisor response from text handler |

#### Skip (temporary placeholders)

| Line | Reason |
|------|--------|
| L196 | "Анализирую транзакции…" — replaced by result |
| L521 | "🤔 Анализирую…" — replaced by result |
| L2176 | "🎤 Обрабатываю голосовое…" — replaced by result |

### File: `backend/app/telegram/handlers.py`

No changes. Business logic returns `dict` with `action`/`message`. Keyboards are assigned in `runtime.py` at the send layer — correct separation of concerns.

## Testing

1. Create a custom category → verify "✅ Создана" has `[≡ Меню]`
2. Delete a category → verify "✅ Удалена" has `[≡ Меню]`
3. Delete category with transactions → verify reassign flow ends with `[≡ Меню]`
4. Try deleting a system category → verify "❌" has `[← Назад] [≡ Меню]`
5. Delete a transaction → verify "✅ Удалил" has `[≡ Меню]`
6. Delete already-deleted transaction → verify "❌" has `[← Назад] [≡ Меню]`
7. Ask a financial question → verify answer has `[📊 Сводка] [≡ Меню]`
8. All "← Назад" buttons navigate to the correct parent screen
9. All "≡ Меню" buttons open main menu
