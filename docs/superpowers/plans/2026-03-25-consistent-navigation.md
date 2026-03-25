# Consistent Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all dead-end screens in the Telegram bot by adding inline keyboards to every message.

**Architecture:** Add three keyboard helper functions (`done_keyboard`, `advisor_keyboard`, `cancel_keyboard`) to `keyboards.py`, then systematically add `reply_markup=` to every `edit_message_text()` / `reply_text()` / `send_message()` call in `runtime.py` that currently lacks one.

**Tech Stack:** python-telegram-bot, InlineKeyboardMarkup

**Spec:** `docs/superpowers/specs/2026-03-25-consistent-navigation-design.md`

**IMPORTANT: Line numbers are approximate.** Tasks 3-12 all modify `runtime.py` sequentially, so each task shifts subsequent line numbers. Always search by **message text** (e.g. `grep "Удалил запись"`) rather than relying on line numbers.

**IMPORTANT: `context.user_data` cleanup.** When adding `cancel_keyboard()`, the cancel callback must also clear any `awaiting_*` keys from `context.user_data`. Otherwise the next text message will still be captured by the stale input handler. Each task notes which `user_data` keys to clean up where applicable.

---

### Task 1: Add keyboard helper functions

**Files:**
- Modify: `backend/app/telegram/keyboards.py`
- Create: `backend/tests/test_navigation_keyboards.py`

- [ ] **Step 1: Write tests for the three new keyboard functions**

```python
# backend/tests/test_navigation_keyboards.py
from app.telegram.keyboards import done_keyboard, advisor_keyboard, cancel_keyboard


def test_done_keyboard_menu_only():
    kb = done_keyboard()
    buttons = kb.inline_keyboard
    assert len(buttons) == 1  # one row
    assert len(buttons[0]) == 1  # one button
    assert buttons[0][0].text == "≡ Меню"
    assert buttons[0][0].callback_data == "nav:menu"


def test_done_keyboard_with_back():
    kb = done_keyboard(back_target="nav:categories")
    buttons = kb.inline_keyboard
    assert len(buttons) == 1
    assert len(buttons[0]) == 2  # back + menu
    assert buttons[0][0].text == "← Назад"
    assert buttons[0][0].callback_data == "nav:categories"
    assert buttons[0][1].text == "≡ Меню"
    assert buttons[0][1].callback_data == "nav:menu"


def test_advisor_keyboard():
    kb = advisor_keyboard()
    buttons = kb.inline_keyboard
    assert len(buttons) == 1
    assert len(buttons[0]) == 2
    assert buttons[0][0].text == "📊 Сводка"
    assert buttons[0][0].callback_data == "nav:stats"
    assert buttons[0][1].text == "≡ Меню"


def test_cancel_keyboard():
    kb = cancel_keyboard("nav:settings")
    buttons = kb.inline_keyboard
    assert len(buttons) == 1
    assert len(buttons[0]) == 1
    assert buttons[0][0].text == "❌ Отмена"
    assert buttons[0][0].callback_data == "nav:settings"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_navigation_keyboards.py -v`
Expected: FAIL — `ImportError: cannot import name 'done_keyboard'`

- [ ] **Step 3: Implement the three functions in keyboards.py**

Add at the end of the "Shared inline button helpers" section (after `_back_btn`, around line 48):

```python
def done_keyboard(back_target: str | None = None) -> InlineKeyboardMarkup:
    """Post-action keyboard: [← Назад] [≡ Меню] or just [≡ Меню]."""
    if back_target:
        return InlineKeyboardMarkup([[_back_btn(back_target), _menu_btn()]])
    return InlineKeyboardMarkup([[_menu_btn()]])


def advisor_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for QA/advisor responses: [📊 Сводка] [≡ Меню]."""
    return InlineKeyboardMarkup([[_btn("📊 Сводка", "nav:stats"), _menu_btn()]])


def cancel_keyboard(back_target: str) -> InlineKeyboardMarkup:
    """Keyboard for input prompts: [❌ Отмена]."""
    return InlineKeyboardMarkup([[_btn("❌ Отмена", back_target)]])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_navigation_keyboards.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/telegram/keyboards.py backend/tests/test_navigation_keyboards.py
git commit -m "feat: add done_keyboard, advisor_keyboard, cancel_keyboard helpers"
```

---

### Task 2: Add import of new keyboards in runtime.py

**Files:**
- Modify: `backend/app/telegram/runtime.py:33-56`

- [ ] **Step 1: Add imports**

Add `done_keyboard`, `advisor_keyboard`, `cancel_keyboard` to the existing import block at line 33:

```python
from app.telegram.keyboards import (
    advisor_keyboard,
    cancel_keyboard,
    category_grid_keyboard,
    category_resolution_keyboard,
    delete_all_confirm_keyboard,
    delete_keyboard,
    done_keyboard,
    edit_categories_keyboard,
    edit_item_keyboard,
    edit_select_keyboard,
    evening_checkin_amount_keyboard,
    evening_checkin_keyboard,
    low_confidence_category_keyboard,
    low_confidence_keyboard,
    main_menu_inline_keyboard,
    planned_expense_due_keyboard,
    planned_manage_keyboard,
    recurring_category_keyboard,
    recurring_manage_keyboard,
    saved_actions_keyboard,
    settings_keyboard,
    start_keyboard,
    suggestion_keyboard,
    undo_inline_keyboard,
    voice_confirmation_keyboard,
)
```

- [ ] **Step 2: Verify import works**

Run: `cd backend && python -c "from app.telegram.keyboards import done_keyboard, advisor_keyboard, cancel_keyboard; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "chore: import new navigation keyboards in runtime"
```

---

### Task 3: Fix categories subsystem dead-ends

**Files:**
- Modify: `backend/app/telegram/runtime.py` — lines around L330, L341, L343, L354, L388, L390, L395, L405, L407

- [ ] **Step 1: Add reply_markup to each categories dead-end**

For each line, add `reply_markup=done_keyboard(...)` parameter. Pattern:

```python
# Confirmations (L343, L390, L407) → done_keyboard()
await query.edit_message_text("✅ Категория ...", reply_markup=done_keyboard())

# Errors (L330, L341, L354, L388, L395, L405) → done_keyboard(back_target="nav:categories")
await query.edit_message_text("❌ ...", reply_markup=done_keyboard(back_target="nav:categories"))
```

Apply to all 9 locations listed in spec section "1. Categories subsystem".

- [ ] **Step 2: Run existing tests**

Run: `cd backend && python -m pytest tests/ -v -x`
Expected: All existing tests pass (no behavioral change)

- [ ] **Step 3: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat: add navigation keyboards to categories dead-end screens"
```

---

### Task 4: Fix edit flow, undo, and catfix dead-ends

**Files:**
- Modify: `backend/app/telegram/runtime.py` — search by message text (lines approximate)

- [ ] **Step 1: Add reply_markup to edit/undo/catfix dead-ends**

```python
# Catfix result (search: "catfix:set" handler result) → done_keyboard()
# After category correction is applied, add keyboard to the result message

# Edit command "no records" (search: "Записей для редактирования нет" or edit_command) → done_keyboard()
# Edit callback "no records" (search: edit_select_keyboard empty case) → done_keyboard()
# Edit callback "not found" (search: "Не найдена запись" in edit_callback_handler) → done_keyboard(back_target="nav:menu")

# Edit confirmations — "Удалил запись" → done_keyboard()
await query.edit_message_text("✅ Удалил запись.", reply_markup=done_keyboard())

# Edit errors — "Не нашёл запись" → done_keyboard(back_target="nav:menu")
await query.edit_message_text("❌ Не нашёл запись...", reply_markup=done_keyboard(back_target="nav:menu"))

# Edit type/category changed OK → done_keyboard()
# Edit type/category errors → done_keyboard(back_target="nav:menu")

# Edit amount input prompt → cancel_keyboard
# NOTE: Also clear context.user_data["awaiting_edit"] in the cancel callback handler
await query.edit_message_text("✏️ Введи новую сумму:", reply_markup=cancel_keyboard("edit:select"))

# Undo (L913, L932) → done_keyboard()
await query.edit_message_text("❌ Не удалось отменить...", reply_markup=done_keyboard())
await query.edit_message_text("↩ Отменено...", reply_markup=done_keyboard())
await query.edit_message_text("Запись уже была удалена...", reply_markup=done_keyboard())
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/ -v -x`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat: add navigation keyboards to edit/undo dead-end screens"
```

---

### Task 5: Fix category resolution and low confidence dead-ends

**Files:**
- Modify: `backend/app/telegram/runtime.py` — lines around L962, L967, L975, L986, L993, L1060, L1064

- [ ] **Step 1: Add reply_markup to catres/lowconf dead-ends**

All these are callback results → `done_keyboard()`:

```python
# L962
await query.edit_message_text("Сессия истекла...", reply_markup=done_keyboard())
# L967
await query.edit_message_text("Запись отменена.", reply_markup=done_keyboard())
# L975, L986 — saved results
await query.edit_message_text(result["message"], parse_mode="HTML", reply_markup=done_keyboard())
# L993, L1064 — errors
await query.edit_message_text("Не удалось обработать выбор.", reply_markup=done_keyboard())
# L1060 — lowconf saved
await query.edit_message_text(msg, parse_mode="HTML", reply_markup=done_keyboard())
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/ -v -x`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat: add navigation keyboards to category resolution dead-ends"
```

---

### Task 6: Fix evening check-in and nav error dead-ends

**Files:**
- Modify: `backend/app/telegram/runtime.py` — lines around L1084, L1126, L1136, L1139, L1267

- [ ] **Step 1: Add reply_markup to check-in dead-ends**

```python
# L1084 — empty day
await query.edit_message_text("👍 Хорошо, пустой день.", reply_markup=done_keyboard())
# L1126 — check-in saved
await query.edit_message_text(msg, parse_mode="HTML", reply_markup=done_keyboard())
# L1136 — amount input prompt
# NOTE: "checkin:none" triggers "nothing today" flow which is acceptable as cancel behavior.
# Also clear context.user_data["awaiting_checkin_amount"] on cancel.
await query.edit_message_text(f"{cat_label} — введи сумму:", reply_markup=cancel_keyboard("checkin:none"))
# L1139 — OK
await query.edit_message_text("Хорошо!", reply_markup=done_keyboard())
# L1267 — nav error
await update.effective_chat.send_message("❌ Ошибка...", reply_markup=done_keyboard())
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/ -v -x`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat: add navigation keyboards to check-in and nav error screens"
```

---

### Task 7: Fix budget dead-ends

**Files:**
- Modify: `backend/app/telegram/runtime.py` — lines around L1408, L1414, L1418, L1437, L1447, L1449, L1454, L1463

- [ ] **Step 1: Add reply_markup to budget dead-ends**

```python
# L1408 — user not found
await update.effective_message.reply_text("❌ Не нашёл пользователя.", reply_markup=done_keyboard())
# L1414, L1418 — budget report
await update.effective_message.reply_text(report, reply_markup=done_keyboard(back_target="nav:budgets"))
# L1437 — bad amount
await update.effective_message.reply_text("❌ Не понял сумму...", reply_markup=done_keyboard(back_target="nav:budgets"))
# L1447 — budget deleted
await update.effective_message.reply_text("✅ Бюджет удалён.", reply_markup=done_keyboard(back_target="nav:budgets"))
# L1449 — not set
await update.effective_message.reply_text("Бюджет не был установлен.", reply_markup=done_keyboard(back_target="nav:budgets"))
# L1454 — budget set
await update.effective_message.reply_text("✅ Бюджет: ...", reply_markup=done_keyboard(back_target="nav:budgets"))
# L1463 — alert (proactive, no back)
await update.effective_message.reply_text(alert, reply_markup=done_keyboard())
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/ -v -x`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat: add navigation keyboards to budget dead-end screens"
```

---

### Task 8: Fix recurring dead-ends

**Files:**
- Modify: `backend/app/telegram/runtime.py` — lines around L1478, L1496, L1512, L1530, L1536, L1542, L1566, L1571, L1577, L1585, L1587

- [ ] **Step 1: Add reply_markup to recurring dead-ends**

```python
# L1478 — list
await update.effective_message.reply_text(svc.format_list(items), reply_markup=done_keyboard())
# L1496 — parsed result
await update.effective_message.reply_text(parsed, reply_markup=done_keyboard())
# L1512 — created
await update.effective_message.reply_text(svc.format_created(rt), reply_markup=done_keyboard())
# L1530 — error
await query.edit_message_text("Некорректное правило...", reply_markup=done_keyboard(back_target="nav:recurring_list"))
# L1536 — amount prompt (clear context.user_data["awaiting_recurring_amount"] on cancel)
await query.edit_message_text("Введи новую сумму:", reply_markup=cancel_keyboard("nav:recurring_list"))
# L1542 — period prompt (clear context.user_data["awaiting_recurring_schedule"] on cancel)
await query.edit_message_text("Введи новый период:", reply_markup=cancel_keyboard("nav:recurring_list"))
# L1566 — updated/deleted
await query.edit_message_text(response["message"], reply_markup=done_keyboard())
# L1571, L1577, L1585, L1587 — command responses
# → done_keyboard()
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/ -v -x`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat: add navigation keyboards to recurring dead-end screens"
```

---

### Task 9: Fix settings dead-ends

**Files:**
- Modify: `backend/app/telegram/runtime.py` — lines around L1607, L1613, L1619, L1625, L1636

- [ ] **Step 1: Add reply_markup to settings dead-ends**

```python
# All settings prompts: clear context.user_data["awaiting_setting"] on cancel
# L1607 — budget day prompt
await query.edit_message_text("Введи день начала...", reply_markup=cancel_keyboard("nav:settings"))
# L1613 — morning reminder prompt
await query.edit_message_text("Введи время утреннего...", reply_markup=cancel_keyboard("nav:settings"))
# L1619 — evening reminder prompt
await query.edit_message_text("Введи время вечернего...", reply_markup=cancel_keyboard("nav:settings"))
# L1625 — timezone prompt
await query.edit_message_text("Введи часовой пояс:", reply_markup=cancel_keyboard("nav:settings"))
# L1636 — reminders disabled
await query.edit_message_text("✅ Все напоминания отключены.", reply_markup=done_keyboard(back_target="nav:settings"))
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/ -v -x`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat: add navigation keyboards to settings dead-end screens"
```

---

### Task 10: Fix planned/recurring input flows and category rename/emoji

**Files:**
- Modify: `backend/app/telegram/runtime.py` — lines around L1674-L1695, L1757-L1765, L1878, L1891, L1902, L1920, L1931, L1945-L1986

- [ ] **Step 1: Add reply_markup to planned/recurring input errors**

All error messages in these flows → `done_keyboard()`:

```python
# L1674, L1681, L1689, L1695 — planned input errors
await update.effective_message.reply_text(..., reply_markup=done_keyboard())
# L1757, L1765 — recurring input errors
await update.effective_message.reply_text(..., reply_markup=done_keyboard())
# L1878 — record not found
await update.effective_message.reply_text("❌ Запись не найдена.", reply_markup=done_keyboard())
# L1891 — bad amount
await update.effective_message.reply_text("❌ Не понял сумму...", reply_markup=done_keyboard())
# L1902, L1931 — updated OK
await update.effective_message.reply_text(response["message"], reply_markup=done_keyboard())
# L1920 — bad date
await update.effective_message.reply_text("❌ Не понял дату...", reply_markup=done_keyboard())
```

- [ ] **Step 2: Add reply_markup to category rename/emoji screens**

```python
# L1945 — rename prompt → cancel_keyboard("nav:categories")
# L1949, L1970, L1986 — not found → done_keyboard(back_target="nav:categories")
# L1964 — emoji error → done_keyboard(back_target="nav:categories")
# L1968 — emoji OK → done_keyboard()
# L1978 — rename OK → done_keyboard()
```

- [ ] **Step 3: Run tests**

Run: `cd backend && python -m pytest tests/ -v -x`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat: add navigation keyboards to planned/recurring/category-edit screens"
```

---

### Task 11: Fix text handler, voice, and callback dead-ends

**Files:**
- Modify: `backend/app/telegram/runtime.py` — lines around L2021, L2029, L2040, L2053, L2160, L2173, L2206, L2211, L2282, L2301, L2332, L2335, L2363

- [ ] **Step 1: Add reply_markup to text handler dead-ends**

```python
# L2021 — saved in settings/edit context
await update.effective_message.reply_text(response["message"], reply_markup=done_keyboard())
# L2029 — settings response
await update.effective_message.reply_text(parsed, reply_markup=done_keyboard(back_target="nav:settings"))
# L2040 — fallback
await update.effective_message.reply_text(response["message"], reply_markup=done_keyboard())
# L2053 — bad amount in budget
await update.effective_message.reply_text("❌ Не понял сумму...", reply_markup=done_keyboard(back_target="nav:budgets"))
# L2160 — multi-transaction saved
await update.effective_message.reply_text(..., reply_markup=done_keyboard())
# L2282 — advisor
await update.effective_message.reply_text(response["message"], parse_mode="HTML", reply_markup=advisor_keyboard())
```

- [ ] **Step 2: Add reply_markup to voice dead-ends**

```python
# L2173 — no payload
await update.effective_message.reply_text("Не нашёл voice payload.", reply_markup=done_keyboard())
# L2206, L2211 — voice errors
await update.effective_message.reply_text(..., reply_markup=done_keyboard())
```

- [ ] **Step 3: Add reply_markup to callback dead-ends**

```python
# L2301 — bad callback
await query.edit_message_text("Некорректный callback payload.", reply_markup=done_keyboard())
# L2332, L2335 — voice confirmed/cancelled
await query.edit_message_text(response["message"], parse_mode="HTML", reply_markup=done_keyboard())
# L2363 — delete result
await query.edit_message_text(response["message"], reply_markup=done_keyboard())
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/ -v -x`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat: add navigation keyboards to text/voice/callback dead-end screens"
```

---

### Task 12: Fix remaining dead-ends (export, plan, improve, budget text input)

**Files:**
- Modify: `backend/app/telegram/runtime.py` — search by message text

- [ ] **Step 1: Add reply_markup to remaining dead-ends**

```python
# L203 — improve error
await update.effective_message.reply_text(f"Ошибка при анализе: {exc}", reply_markup=done_keyboard())
# L207 — "Предложений нет." (improve, no suggestions — separate from L511)
await update.effective_message.reply_text("Предложений нет.", reply_markup=done_keyboard())
# L511 — improve no suggestions (different code path)
await update.effective_message.reply_text(response["message"], reply_markup=done_keyboard())
# L525 — /ask answer
await update.effective_message.reply_text(answer, reply_markup=advisor_keyboard())
# L738 — export empty
await update.effective_message.reply_text(f"Записей нет.", reply_markup=done_keyboard())
# L770, L784, L799 — /plan results
await update.effective_message.reply_text(..., reply_markup=done_keyboard())
# L836 — bad planned id
await query.edit_message_text("Некорректный planned expense.", reply_markup=done_keyboard(back_target="nav:planned_list"))
# L842 — amount prompt (clear context.user_data["awaiting_planned_amount"] on cancel)
await query.edit_message_text("Введи новую сумму:", reply_markup=cancel_keyboard("nav:planned_list"))
# L848 — date prompt (clear context.user_data["awaiting_planned_date"] on cancel)
await query.edit_message_text("Введи новую дату:", reply_markup=cancel_keyboard("nav:planned_list"))
# L860 — planned confirmed/cancelled
await query.edit_message_text(response["message"], reply_markup=done_keyboard())
# L2454, L2481 — budget text input errors (_handle_budget_total_input, _handle_budget_category_input)
await update.effective_message.reply_text(..., reply_markup=done_keyboard(back_target="nav:budgets"))
```

- [ ] **Step 2: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat: add navigation keyboards to export/plan/improve dead-end screens"
```

---

### Task 13: Clean up `context.user_data` on cancel callbacks

**Files:**
- Modify: `backend/app/telegram/runtime.py` — nav_callback_handler and relevant callback handlers

When a cancel button routes to a nav target (e.g. `nav:settings`, `nav:recurring_list`, `edit:select`), the `nav_callback_handler` (or the respective handler) must clear any `awaiting_*` keys so the next text message isn't captured by a stale input handler.

- [ ] **Step 1: Add user_data cleanup in nav_callback_handler**

At the top of `nav_callback_handler`, before processing the nav target, clear all awaiting keys:

```python
# Clear any pending input states when navigating
for key in list(context.user_data.keys()):
    if key.startswith("awaiting_"):
        del context.user_data[key]
```

This is a safe catch-all: any time the user navigates via an inline button, input-awaiting states are cleared.

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/ -v -x`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "fix: clear awaiting_* user_data on nav callback to prevent stale input capture"
```

---

### Task 14: Final verification

- [ ] **Step 1: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Grep for remaining dead-ends**

Run a grep to find any `reply_text(` or `edit_message_text(` or `send_message(` calls that still lack `reply_markup`. Compare results against the skip list:
- "Анализирую транзакции…" (temporary)
- "🤔 Анализирую…" (temporary)
- "🎤 Обрабатываю голосовое…" (temporary)
- Lines with `suggestion_keyboard` (already have keyboard)
- Lines with `saved_actions_keyboard` (already have keyboard)
- "📋 Правила регулярных операций:" header (followed by per-item keyboards)

```bash
cd backend && grep -n "reply_text\|edit_message_text\|send_message" app/telegram/runtime.py | grep -v "reply_markup" | grep -v "placeholder\|Анализирую\|Обрабатываю\|suggestion_keyboard\|saved_actions"
```

Any remaining lines not in the skip list must be fixed.

- [ ] **Step 3: Commit if any fixes needed**

```bash
git add backend/app/telegram/runtime.py
git commit -m "fix: patch any remaining dead-end screens"
```
