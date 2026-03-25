# Consistent Navigation Design

**Date:** 2026-03-25
**Scope:** Telegram bot — eliminate dead-end screens, add consistent inline navigation

## Problem

~80+ screens in `runtime.py` send messages without `reply_markup`, leaving the user with no inline buttons to navigate. The user must type `/menu` or a command to continue.

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

### 3. `cancel_keyboard(back_target)`

For input prompts where the user is asked to type something (amount, date, time). Provides a way to abort.

```python
def cancel_keyboard(back_target: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_btn("❌ Отмена", back_target)]])
```

## Changes Map

### File: `backend/app/telegram/keyboards.py`

Add three new functions: `done_keyboard()`, `advisor_keyboard()`, `cancel_keyboard()`.

### File: `backend/app/telegram/runtime.py`

#### 1. Categories subsystem

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L330 | "❌ Что-то пошло не так" | `done_keyboard` | `"nav:categories"` |
| L341 | "❌ {e}" (create error) | `done_keyboard` | `"nav:categories"` |
| L343 | "✅ Категория создана!" | `done_keyboard` | `None` |
| L354 | "❌ Нельзя удалить системную категорию." | `done_keyboard` | `"nav:categories"` |
| L388 | "❌ {e}" (delete error) | `done_keyboard` | `"nav:categories"` |
| L390 | "✅ Категория удалена." | `done_keyboard` | `None` |
| L395 | "❌ Неверный формат." | `done_keyboard` | `"nav:categories"` |
| L405 | "❌ {e}" (reassign error) | `done_keyboard` | `"nav:categories"` |
| L407 | "✅ Транзакции перенесены, категория удалена." | `done_keyboard` | `None` |

#### 2. Category rename/emoji (text_message_handler sub-flows)

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L1945 | "Введи новое название:" prompt | `cancel_keyboard` | `"nav:categories"` |
| L1949 | "❌ Категория не найдена." | `done_keyboard` | `"nav:categories"` |
| L1964 | "❌ {e} Попробуй ещё раз." | `done_keyboard` | `"nav:categories"` |
| L1968 | "✅ Emoji обновлён" | `done_keyboard` | `None` |
| L1970 | "❌ Категория не найдена." | `done_keyboard` | `"nav:categories"` |
| L1978 | "✅ Название обновлено" | `done_keyboard` | `None` |
| L1986 | "❌ Категория не найдена" | `done_keyboard` | `"nav:categories"` |

#### 3. Improve categories / ask command

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L196 | "Анализирую транзакции…" | skip | temporary placeholder |
| L203 | "Ошибка при анализе: {exc}" | `done_keyboard` | `None` |
| L511 | /improve result (no suggestions) | `done_keyboard` | `None` |
| L517 | /improve result (with suggestions) | skip | has suggestion_keyboard |
| L521 | "🤔 Анализирую…" | skip | temporary placeholder |
| L525 | QA answer (/ask) | `advisor_keyboard` | — |

#### 4. Edit flow

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L544 | /edit "нет записей" | `done_keyboard` | `None` |
| L570 | "❌ Не нашёл пользователя." | `done_keyboard` | `None` |
| L660 | "✅ Удалил запись." | `done_keyboard` | `None` |
| L662 | "❌ Не нашёл запись." | `done_keyboard` | `"nav:menu"` |
| L692 | "✏️ Введи новую сумму:" | `cancel_keyboard` | `"edit:select"` |

#### 5. Export

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L738 | "Записей нет" | `done_keyboard` | `None` |

#### 6. Plan / Planned expenses

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L770 | /plan parsing error | `done_keyboard` | `None` |
| L784 | /plan parsed result | `done_keyboard` | `None` |
| L799 | /plan saved | `done_keyboard` | `None` |
| L836 | "Некорректный planned expense." | `done_keyboard` | `"nav:planned_list"` |
| L842 | "Введи новую сумму для учёта:" | `cancel_keyboard` | `"nav:planned_list"` |
| L848 | "Введи новую дату:" | `cancel_keyboard` | `"nav:planned_list"` |
| L860 | planned confirmed/cancelled/updated | `done_keyboard` | `None` |

#### 7. Undo

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L913 | "❌ Не удалось отменить: ID не найден." | `done_keyboard` | `None` |
| L930 | "↩ Отменено" | `done_keyboard` | `None` |
| L932 | "Запись уже была удалена" | `done_keyboard` | `None` |

#### 8. Category resolution (catres callbacks)

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L962 | "Сессия истекла." | `done_keyboard` | `None` |
| L967 | "Запись отменена." | `done_keyboard` | `None` |
| L975 | catres:use result (saved) | `done_keyboard` | `None` |
| L986 | catres:create result (saved) | `done_keyboard` | `None` |
| L993 | "Не удалось обработать выбор." | `done_keyboard` | `None` |

#### 9. Low confidence (lowconf callbacks)

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L1060 | lowconf saved | `done_keyboard` | `None` |
| L1064 | "Не удалось обработать выбор." | `done_keyboard` | `None` |

#### 10. Evening check-in

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L1084 | "👍 Хорошо, пустой день." | `done_keyboard` | `None` |
| L1126 | check-in saved | `done_keyboard` | `None` |
| L1136 | "{cat_label} — введи сумму:" | `cancel_keyboard` | `"checkin:none"` |
| L1139 | "Хорошо!" | `done_keyboard` | `None` |

#### 11. Nav error

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L1267 | "❌ Ошибка при открытии раздела." | `done_keyboard` | `None` |

#### 12. Budget

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L1408 | "❌ Не нашёл пользователя." | `done_keyboard` | `None` |
| L1414 | Budget report | `done_keyboard` | `"nav:budgets"` |
| L1418 | Budget usage text | `done_keyboard` | `"nav:budgets"` |
| L1437 | "❌ Не понял сумму" | `done_keyboard` | `"nav:budgets"` |
| L1447 | "✅ Бюджет удалён." | `done_keyboard` | `"nav:budgets"` |
| L1449 | "Бюджет не был установлен." | `done_keyboard` | `"nav:budgets"` |
| L1454 | "✅ Бюджет: {amount}" | `done_keyboard` | `"nav:budgets"` |
| L1463 | Budget alert | `done_keyboard` | `None` |

#### 13. Recurring

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L1478 | Recurring list | `done_keyboard` | `None` |
| L1480 | "📋 Правила регулярных операций:" | skip | followed by per-item keyboards |
| L1496 | /recurring parsed | `done_keyboard` | `None` |
| L1512 | Recurring created | `done_keyboard` | `None` |
| L1530 | "Некорректное правило recurring." | `done_keyboard` | `"nav:recurring_list"` |
| L1536 | "Введи новую сумму для правила:" | `cancel_keyboard` | `"nav:recurring_list"` |
| L1542 | "Введи новый период:" | `cancel_keyboard` | `"nav:recurring_list"` |
| L1566 | Recurring updated/deleted | `done_keyboard` | `None` |
| L1571 | /recurring_del format hint | `done_keyboard` | `None` |
| L1577 | "❌ Номер должен быть числом" | `done_keyboard` | `None` |
| L1585 | "✅ Транзакция удалена." | `done_keyboard` | `None` |
| L1587 | "❌ Транзакция не найдена." | `done_keyboard` | `None` |

#### 14. Settings

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L1607 | "Введи день начала периода (1–28):" | `cancel_keyboard` | `"nav:settings"` |
| L1613 | "Введи время утреннего напоминания:" | `cancel_keyboard` | `"nav:settings"` |
| L1619 | "Введи время вечернего напоминания:" | `cancel_keyboard` | `"nav:settings"` |
| L1625 | "Введи часовой пояс:" | `cancel_keyboard` | `"nav:settings"` |
| L1636 | "✅ Все напоминания отключены." | `done_keyboard` | `"nav:settings"` |

#### 15. Planned/recurring text input flows

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L1674 | Planned input error | `done_keyboard` | `None` |
| L1681 | Planned input error | `done_keyboard` | `None` |
| L1689 | Planned input error | `done_keyboard` | `None` |
| L1695 | Planned input error | `done_keyboard` | `None` |
| L1757 | Recurring input error | `done_keyboard` | `None` |
| L1765 | Recurring input error | `done_keyboard` | `None` |
| L1878 | "❌ Запись не найдена." | `done_keyboard` | `None` |
| L1891 | "❌ Не понял сумму." | `done_keyboard` | `None` |
| L1902 | Planned date/amount updated | `done_keyboard` | `None` |
| L1920 | "❌ Не понял дату." | `done_keyboard` | `None` |
| L1931 | Recurring amount updated | `done_keyboard` | `None` |

#### 16. Text message handler (saved/fallback/advisor)

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L2021 | Saved response (settings/edit context) | `done_keyboard` | `None` |
| L2029 | Settings response | `done_keyboard` | `"nav:settings"` |
| L2040 | Fallback "не понял" | `done_keyboard` | `None` |
| L2053 | "❌ Не понял сумму." (budget input) | `done_keyboard` | `"nav:budgets"` |
| L2153 | Saved transaction | skip | has saved_actions_keyboard |
| L2160 | Saved multi-transaction | `done_keyboard` | `None` |
| L2282 | Advisor response | `advisor_keyboard` | — |

#### 17. Voice

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L2173 | "Не нашёл voice payload." | `done_keyboard` | `None` |
| L2176 | "🎤 Обрабатываю голосовое…" | skip | temporary placeholder |
| L2206 | Voice error | `done_keyboard` | `None` |
| L2211 | Voice error | `done_keyboard` | `None` |

#### 18. Voice/delete callbacks

| Line | Message | Keyboard | back_target |
|------|---------|----------|-------------|
| L2301 | "Некорректный callback payload." | `done_keyboard` | `None` |
| L2332 | Voice confirmed/saved | `done_keyboard` | `None` |
| L2335 | Voice cancelled | `done_keyboard` | `None` |
| L2363 | Delete response | `done_keyboard` | `None` |

### File: `backend/app/telegram/handlers.py`

No changes. Business logic returns `dict` with `action`/`message`. Keyboards are assigned in `runtime.py` at the send layer — correct separation of concerns.

## Skip List (no keyboard needed)

| Line | Message | Reason |
|------|---------|--------|
| L196 | "Анализирую транзакции…" | Temporary — replaced by result |
| L521 | "🤔 Анализирую…" | Temporary — replaced by result |
| L2176 | "🎤 Обрабатываю голосовое…" | Temporary — replaced by result |
| L517 | /improve suggestions | Already has suggestion_keyboard per item |
| L1480 | Recurring list header | Followed by per-item messages with keyboards |
| L2153 | Single saved transaction | Already has saved_actions_keyboard |

## Testing

### Automated
- Unit test: every `reply_text` / `edit_message_text` / `send_message` call in `runtime.py` includes `reply_markup` (except skip list lines)
- Can be a grep-based lint check in CI

### Manual smoke tests
1. Create a custom category → "✅ Создана" has `[≡ Меню]`
2. Delete a category → "✅ Удалена" has `[≡ Меню]`
3. Delete category with transactions → reassign → "✅ Перенесены" has `[≡ Меню]`
4. Try deleting system category → "❌" has `[← Назад] [≡ Меню]`
5. Delete a transaction → "✅ Удалил" has `[≡ Меню]`
6. Delete already-deleted → "❌" has `[← Назад] [≡ Меню]`
7. Ask financial question → answer has `[📊 Сводка] [≡ Меню]`
8. Undo a transaction → "↩ Отменено" has `[≡ Меню]`
9. Evening check-in → "👍 Пустой день" has `[≡ Меню]`
10. Settings input prompts → "Введи..." has `[❌ Отмена]`
11. Edit amount prompt → "Введи сумму:" has `[❌ Отмена]`
12. Recurring amount/period prompts → have `[❌ Отмена]`
13. Budget set/delete → confirmations have `[← Назад Бюджеты] [≡ Меню]`
14. All "← Назад" buttons navigate to correct parent screen
15. All "≡ Меню" buttons open main menu
