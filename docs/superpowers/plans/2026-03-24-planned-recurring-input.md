# Free-Form Planned/Recurring Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "📋 Запланированные" and "🔄 Регулярные" buttons to the main menu; pressing either enters input mode where free-form text or voice is parsed by LLM and saved after user confirmation.

**Architecture:** `LLMService` gets two new extraction methods (`extract_planned`, `extract_recurring`) using Groq JSON mode. `runtime.py` routes text/voice through mode-aware handlers; confirm/cancel callbacks persist data via existing `PlannedExpenseService` and `RecurringService`.

**Tech Stack:** python-telegram-bot, OpenAI client (Groq), SQLAlchemy, `PlannedExpenseService`, `RecurringService`, `CategoryService`, `STTService`, `AudioFileService`.

---

## File Map

| File | Change |
|---|---|
| `backend/app/services/llm_service.py` | +`extract_planned()`, +`extract_recurring()` |
| `backend/app/telegram/keyboards.py` | update MENU_BTN constants + `main_menu_inline_keyboard()`, +4 keyboard functions |
| `backend/app/telegram/runtime.py` | update `nav_callback_handler`, +`_handle_planned_input`, +`_handle_recurring_input`, +`planned_input_callback_handler`, +`recurring_input_callback_handler`, update `text_message_handler`, update `voice_message_handler`, register new handlers |
| `backend/tests/test_llm_service.py` | +tests for `extract_planned` and `extract_recurring` |

---

## Task 1: LLM Extraction Methods

**Files:**
- Modify: `backend/app/services/llm_service.py`
- Test: `backend/tests/test_llm_service.py`

The existing `_make_service(mock_response_content)` helper in the test file already mocks the OpenAI client — reuse it.

- [ ] **Step 1: Write failing tests for `extract_planned`**

Add to `backend/tests/test_llm_service.py`:

```python
def test_extract_planned_returns_dict_on_valid_json():
    payload = json.dumps({
        "title": "Стоматолог",
        "amount": 8000.0,
        "category_slug": "health",
        "planned_date_iso": "2026-04-22",
    })
    svc = _make_service(mock_response_content=payload)
    user_categories = [{"slug": "health", "name_ru": "Здоровье"}, {"slug": "other", "name_ru": "Прочее"}]
    result = svc.extract_planned("стоматолог 8000 22 апреля", user_categories)
    assert result is not None
    assert result["title"] == "Стоматолог"
    assert result["amount"] == 8000.0
    assert result["category_slug"] == "health"
    assert result["planned_date_iso"] == "2026-04-22"


def test_extract_planned_returns_none_on_api_error():
    svc = _make_service(mock_response_content="{}")
    svc._client.chat.completions.create.side_effect = Exception("API down")
    result = svc.extract_planned("маникюр 2100 завтра", [])
    assert result is None


def test_extract_recurring_returns_dict_on_valid_json():
    payload = json.dumps({
        "title": "Netflix",
        "amount": 799.0,
        "transaction_type": "expense",
        "category_slug": "subscriptions",
        "frequency": "monthly",
        "day_value": 15,
    })
    svc = _make_service(mock_response_content=payload)
    user_categories = [{"slug": "subscriptions", "name_ru": "Подписки"}, {"slug": "other", "name_ru": "Прочее"}]
    result = svc.extract_recurring("Netflix 799 каждый месяц 15", user_categories)
    assert result is not None
    assert result["title"] == "Netflix"
    assert result["amount"] == 799.0
    assert result["transaction_type"] == "expense"
    assert result["frequency"] == "monthly"
    assert result["day_value"] == 15


def test_extract_recurring_returns_none_on_api_error():
    svc = _make_service(mock_response_content="{}")
    svc._client.chat.completions.create.side_effect = Exception("timeout")
    result = svc.extract_recurring("аренда 30000 каждый месяц 1", [])
    assert result is None
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
cd backend && pytest tests/test_llm_service.py::test_extract_planned_returns_dict_on_valid_json tests/test_llm_service.py::test_extract_recurring_returns_dict_on_valid_json -v
```

Expected: `AttributeError: 'LLMService' object has no attribute 'extract_planned'`

- [ ] **Step 3: Implement `extract_planned` and `extract_recurring` in `LLMService`**

Add after the `process()` method in `backend/app/services/llm_service.py`:

```python
def extract_planned(self, text: str, user_categories: list[dict]) -> dict | None:
    """Extract planned expense fields from free-form text.

    Args:
        text: user message (already transcribed if voice)
        user_categories: list of {"slug": str, "name_ru": str}

    Returns:
        dict with keys title, amount, category_slug, planned_date_iso — or None on error.
    """
    from datetime import date as _date
    category_lines = "\n".join(
        f"- {c['slug']}: {c['name_ru']}" for c in user_categories
    ) or "- other: Прочее"
    today = _date.today().isoformat()
    system = (
        f"Ты ассистент для извлечения данных. Сегодня {today}.\n"
        "Извлеки параметры запланированного расхода из текста.\n"
        'Верни JSON: {"title": str, "amount": float, "category_slug": str, "planned_date_iso": str | null}\n'
        f"Категории пользователя (используй только эти slug):\n{category_lines}\n"
        'planned_date_iso: дата ISO "YYYY-MM-DD", null если не упомянута.\n'
        'Если категория не ясна — "other".'
    )
    try:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw = response.choices[0].message.content or ""
        return json.loads(raw)
    except Exception as exc:
        logger.error("extract_planned error: %s", exc)
        return None

def extract_recurring(self, text: str, user_categories: list[dict]) -> dict | None:
    """Extract recurring transaction fields from free-form text.

    Args:
        text: user message (already transcribed if voice)
        user_categories: list of {"slug": str, "name_ru": str}

    Returns:
        dict with keys title, amount, transaction_type, category_slug, frequency, day_value
        — or None on error.
    """
    category_lines = "\n".join(
        f"- {c['slug']}: {c['name_ru']}" for c in user_categories
    ) or "- other: Прочее"
    system = (
        "Ты ассистент для извлечения данных.\n"
        "Извлеки параметры регулярного платежа из текста.\n"
        'Верни JSON: {"title": str, "amount": float, '
        '"transaction_type": "expense"|"income", "category_slug": str, '
        '"frequency": "monthly"|"weekly"|"daily"|"interval_days", "day_value": int}\n'
        f"Категории пользователя (используй только эти slug):\n{category_lines}\n"
        "monthly: day_value = день месяца (1-28).\n"
        "weekly: day_value = день недели (0=пн...6=вс).\n"
        "interval_days: day_value = количество дней.\n"
        "daily: day_value = 1.\n"
        'Если тип (расход/доход) не ясен — "expense". Если категория не ясна — "other".'
    )
    try:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw = response.choices[0].message.content or ""
        return json.loads(raw)
    except Exception as exc:
        logger.error("extract_recurring error: %s", exc)
        return None
```

- [ ] **Step 4: Run all 4 tests — verify PASS**

```bash
cd backend && pytest tests/test_llm_service.py::test_extract_planned_returns_dict_on_valid_json tests/test_llm_service.py::test_extract_planned_returns_none_on_api_error tests/test_llm_service.py::test_extract_recurring_returns_dict_on_valid_json tests/test_llm_service.py::test_extract_recurring_returns_none_on_api_error -v
```

Expected: 4 PASSED

- [ ] **Step 5: Run full test suite — verify no regressions**

```bash
cd backend && pytest -x -q
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/llm_service.py backend/tests/test_llm_service.py
git commit -m "feat: add extract_planned and extract_recurring to LLMService"
```

---

## Task 2: Keyboards Update

**Files:**
- Modify: `backend/app/telegram/keyboards.py`

The current constants and main menu (lines 54-69 in `keyboards.py`):
```python
MENU_BTN_PLANNED  = "📌 Запланированное"
MENU_BTN_RECURRING = "🔁 Регулярное"
...
[_btn(MENU_BTN_PLANNED, "nav:planned"), _btn(MENU_BTN_RECURRING, "nav:recurring")],
```

- [ ] **Step 1: Update MENU_BTN constants**

In `backend/app/telegram/keyboards.py`, replace:
```python
MENU_BTN_PLANNED  = "📌 Запланированное"
MENU_BTN_RECURRING = "🔁 Регулярное"
```
with:
```python
MENU_BTN_PLANNED   = "📋 Запланированные"
MENU_BTN_RECURRING = "🔄 Регулярные"
```

- [ ] **Step 2: Update `main_menu_inline_keyboard()` callback_data**

Replace the row:
```python
[_btn(MENU_BTN_PLANNED, "nav:planned"), _btn(MENU_BTN_RECURRING, "nav:recurring")],
```
with:
```python
[_btn(MENU_BTN_PLANNED, "nav:planned_input"), _btn(MENU_BTN_RECURRING, "nav:recurring_input")],
```

- [ ] **Step 3: Add 4 new keyboard functions**

Add after `recurring_inline_keyboard()` (line 77):

```python
def planned_input_keyboard() -> InlineKeyboardMarkup:
    """Shown when entering planned input mode."""
    return InlineKeyboardMarkup([
        [_btn("📋 Мои запланированные", "nav:planned_list")],
        [_back_btn("nav:menu")],
    ])


def recurring_input_keyboard() -> InlineKeyboardMarkup:
    """Shown when entering recurring input mode."""
    return InlineKeyboardMarkup([
        [_btn("🔄 Мои регулярные", "nav:recurring_list")],
        [_back_btn("nav:menu")],
    ])


def planned_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirmation keyboard after LLM extraction of planned expense."""
    return InlineKeyboardMarkup([
        [_btn("✅ Сохранить", "planned_input:confirm"),
         _btn("❌ Отмена", "planned_input:cancel")],
    ])


def recurring_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirmation keyboard after LLM extraction of recurring transaction."""
    return InlineKeyboardMarkup([
        [_btn("✅ Сохранить", "recurring_input:confirm"),
         _btn("❌ Отмена", "recurring_input:cancel")],
    ])
```

- [ ] **Step 4: Run full test suite — verify no regressions**

```bash
cd backend && pytest -x -q
```

Expected: all tests pass (if `test_navigation_menu.py` fails on button label assertions — update the expected strings to match new labels)

- [ ] **Step 5: Commit**

```bash
git add backend/app/telegram/keyboards.py
git commit -m "feat: update main menu buttons and add planned/recurring input keyboards"
```

---

## Task 3: nav_callback_handler + Confirm/Cancel Handlers

**Files:**
- Modify: `backend/app/telegram/runtime.py`

**Context:** `nav_callback_handler` is at line ~1130. The existing `section == "planned"` (line 1172) calls `nav.planned_screen()` and `section == "recurring"` (line 1174) calls `nav.recurring_screen()`. These are replaced.

- [ ] **Step 1: Update `nav_callback_handler` — clear mode and add new sections**

Inside `nav_callback_handler`, at the top of the handler (before `try:`), add mode clearing:

```python
# Clear any pending input mode on any navigation action
if context.user_data:
    context.user_data.pop("mode", None)
    context.user_data.pop("pending_planned", None)
    context.user_data.pop("pending_recurring", None)
```

Then replace the two existing sections (around line 1172-1175):

```python
# BEFORE:
elif section == "planned":
    screen = nav.planned_screen(user_id)
elif section == "recurring":
    screen = nav.recurring_screen(user_id)
```

```python
# AFTER:
elif section == "planned_list":
    screen = nav.planned_screen(user_id)
elif section == "recurring_list":
    screen = nav.recurring_screen(user_id)
elif section == "planned_input":
    # Enter input mode — do NOT set mode here (mode is set only for text/voice routing)
    # Instead show a prompt and set mode via user_data AFTER clearing above
    context.user_data["mode"] = "planned_input"
    await query.edit_message_text(
        "Опиши запланированный расход — название, сумму и дату.\n"
        "Например: «маникюр 2100 рублей 15 апреля»",
        reply_markup=planned_input_keyboard(),
    )
    return
elif section == "recurring_input":
    context.user_data["mode"] = "recurring_input"
    await query.edit_message_text(
        "Опиши регулярный платёж — название, сумму и периодичность.\n"
        "Например: «аренда 30000 каждый месяц 1 числа»\n"
        "          «зарплата 120000 каждый месяц 10 числа»",
        reply_markup=recurring_input_keyboard(),
    )
    return
```

**Important:** The mode clearing happens at the top, but for `planned_input` / `recurring_input` sections we re-set it after. This is correct — the clearing is for all OTHER navigation actions.

Add the new keyboard imports at the top of the function or ensure they are imported at module level. Verify that `planned_input_keyboard` and `recurring_input_keyboard` are imported from `app.telegram.keyboards`.

- [ ] **Step 2: Add `planned_input_callback_handler` function**

Add before the `if __name__ == "__main__"` block or near the other callback handlers:

```python
async def planned_input_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles planned_input:confirm and planned_input:cancel."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    action = query.data.split(":")[1]  # "confirm" or "cancel"
    user_id = update.effective_user.id

    if action == "cancel":
        if context.user_data:
            context.user_data.pop("pending_planned", None)
        try:
            await query.edit_message_text(
                "Отменено.",
                reply_markup=main_menu_inline_keyboard(),
            )
        except BadRequest:
            pass
        return

    # confirm
    pending = (context.user_data or {}).pop("pending_planned", None)
    if not pending:
        try:
            await query.edit_message_text(
                "❌ Данные устарели. Начни заново.",
                reply_markup=main_menu_inline_keyboard(),
            )
        except BadRequest:
            pass
        return

    from datetime import date as _date
    from app.services.planned_expense_service import PlannedExpenseService

    with SessionLocal() as db:
        svc = PlannedExpenseService(db)
        item = svc.create_manual(
            telegram_user_id=user_id,
            title=pending["title"],
            amount=float(pending["amount"]),
            category=pending["category"],
            planned_date=_date.fromisoformat(pending["planned_date"]),
        )

    try:
        await query.edit_message_text(
            f"✅ Запланировано: {item.title} — {float(item.amount):,.0f} ₽ на {item.planned_date}",
            reply_markup=main_menu_inline_keyboard(),
        )
    except BadRequest:
        pass
```

- [ ] **Step 3: Add `recurring_input_callback_handler` function**

```python
async def recurring_input_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles recurring_input:confirm and recurring_input:cancel."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    action = query.data.split(":")[1]  # "confirm" or "cancel"
    user_id = update.effective_user.id

    if action == "cancel":
        if context.user_data:
            context.user_data.pop("pending_recurring", None)
        try:
            await query.edit_message_text(
                "Отменено.",
                reply_markup=main_menu_inline_keyboard(),
            )
        except BadRequest:
            pass
        return

    # confirm
    pending = (context.user_data or {}).pop("pending_recurring", None)
    if not pending:
        try:
            await query.edit_message_text(
                "❌ Данные устарели. Начни заново.",
                reply_markup=main_menu_inline_keyboard(),
            )
        except BadRequest:
            pass
        return

    from app.services.recurring_service import RecurringService

    with SessionLocal() as db:
        svc = RecurringService(db)
        rt = svc.create(
            telegram_user_id=user_id,
            title=pending["title"],
            amount=float(pending["amount"]),
            transaction_type=pending["transaction_type"],
            category=pending["category"],
            frequency=pending["frequency"],
            day_value=int(pending["day_value"]),
        )

    sign = "+" if rt.transaction_type == "income" else "−"
    freq_label = RecurringService(None)._format_schedule(rt) if False else _format_recurring_schedule(rt)
    try:
        await query.edit_message_text(
            f"✅ Добавлено: {rt.title} {sign}{float(rt.amount):,.0f} ₽ — {_format_recurring_schedule(rt)}",
            reply_markup=main_menu_inline_keyboard(),
        )
    except BadRequest:
        pass
```

**Note on `_format_recurring_schedule`:** Add a small helper near the handlers (to avoid instantiating `RecurringService` with `None`):

```python
def _format_recurring_schedule(rt) -> str:
    """Format schedule label for a RecurringTransaction object."""
    weekday_labels = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    if rt.frequency == "daily":
        return "каждый день"
    if rt.frequency == "interval_days":
        return f"каждые {rt.day_value} дн."
    if rt.frequency == "weekly":
        label = weekday_labels[rt.day_value] if 0 <= rt.day_value <= 6 else "?"
        return f"каждую неделю ({label})"
    return f"каждый месяц, {rt.day_value}-го"
```

- [ ] **Step 4: Register new handlers**

Find where `application.add_handler(...)` calls are grouped (near the end of the runtime setup function). Add:

```python
application.add_handler(
    CallbackQueryHandler(planned_input_callback_handler, pattern=r"^planned_input:")
)
application.add_handler(
    CallbackQueryHandler(recurring_input_callback_handler, pattern=r"^recurring_input:")
)
```

- [ ] **Step 5: Run full test suite — verify no regressions**

```bash
cd backend && pytest -x -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat: add planned/recurring nav sections and confirm/cancel handlers"
```

---

## Task 4: Input Handlers + Text/Voice Routing

**Files:**
- Modify: `backend/app/telegram/runtime.py`

- [ ] **Step 1: Add `_handle_planned_input` private async function**

Add before `text_message_handler`:

```python
async def _handle_planned_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    """Process free-form text as a planned expense via LLM extraction."""
    from datetime import date as _date
    from app.services.category_service import CategoryService
    from app.services.llm_service import LLMService
    from app.telegram.keyboards import planned_confirm_keyboard

    user_id = update.effective_user.id

    with SessionLocal() as db:
        cat_svc = CategoryService(db)
        cat_svc.ensure_seeded(user_id)
        categories_grouped = cat_svc.list_categories(user_id)
        user_categories = [
            {"slug": c.slug, "name_ru": c.name_ru}
            for group in categories_grouped.values()
            for c in group
        ]
        llm = LLMService(db)
        result = llm.extract_planned(text, user_categories)

    # Clear mode — from this point, new text is a regular transaction
    if context.user_data:
        context.user_data.pop("mode", None)

    if result is None:
        await update.effective_message.reply_text(
            "❌ Не смог разобрать. Попробуй ещё раз."
        )
        return

    planned_date_iso = result.get("planned_date_iso")
    if not planned_date_iso:
        await update.effective_message.reply_text(
            "❌ Не понял дату. Укажи, например: «15 апреля» или «через 2 недели»."
        )
        return

    try:
        planned_date = _date.fromisoformat(planned_date_iso)
    except ValueError:
        await update.effective_message.reply_text(
            "❌ Не понял дату. Укажи, например: «15 апреля» или «через 2 недели»."
        )
        return

    if planned_date < _date.today():
        await update.effective_message.reply_text(
            "❌ Дата уже прошла. Укажи будущую дату."
        )
        return

    # Validate category slug — fallback to "other"
    valid_slugs = {c["slug"] for c in user_categories}
    category_slug = result.get("category_slug") or "other"
    if category_slug not in valid_slugs:
        category_slug = "other"

    title = result.get("title") or ""
    amount = float(result.get("amount") or 0)

    if context.user_data is not None:
        context.user_data["pending_planned"] = {
            "title": title,
            "amount": amount,
            "category": category_slug,
            "planned_date": planned_date_iso,
        }

    cat_label = formatter.category_label(category_slug)
    msg = (
        "Запланировал:\n"
        f"🏷 {title}\n"
        f"💰 {amount:,.0f} ₽\n"
        f"📅 {planned_date_iso}\n"
        f"🗂 {cat_label}"
    )
    await update.effective_message.reply_text(msg, reply_markup=planned_confirm_keyboard())
```

- [ ] **Step 2: Add `_handle_recurring_input` private async function**

Add right after `_handle_planned_input`:

```python
async def _handle_recurring_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    """Process free-form text as a recurring transaction via LLM extraction."""
    from app.services.category_service import CategoryService
    from app.services.llm_service import LLMService
    from app.telegram.keyboards import recurring_confirm_keyboard

    user_id = update.effective_user.id

    with SessionLocal() as db:
        cat_svc = CategoryService(db)
        cat_svc.ensure_seeded(user_id)
        categories_grouped = cat_svc.list_categories(user_id)
        user_categories = [
            {"slug": c.slug, "name_ru": c.name_ru}
            for group in categories_grouped.values()
            for c in group
        ]
        llm = LLMService(db)
        result = llm.extract_recurring(text, user_categories)

    # Clear mode
    if context.user_data:
        context.user_data.pop("mode", None)

    if result is None:
        await update.effective_message.reply_text(
            "❌ Не смог разобрать. Попробуй ещё раз."
        )
        return

    required_keys = ("title", "amount", "transaction_type", "category_slug", "frequency", "day_value")
    missing = [k for k in required_keys if result.get(k) is None]
    if missing:
        await update.effective_message.reply_text(
            f"❌ Не понял: {', '.join(missing)}. Попробуй ещё раз."
        )
        return

    # Validate category slug — fallback to "other"
    valid_slugs = {c["slug"] for c in user_categories}
    category_slug = result.get("category_slug") or "other"
    if category_slug not in valid_slugs:
        category_slug = "other"

    tx_type = result.get("transaction_type", "expense")
    if tx_type not in ("income", "expense"):
        tx_type = "expense"

    title = result.get("title") or ""
    amount = float(result.get("amount") or 0)
    frequency = result.get("frequency", "monthly")
    day_value = int(result.get("day_value") or 1)

    if context.user_data is not None:
        context.user_data["pending_recurring"] = {
            "title": title,
            "amount": amount,
            "transaction_type": tx_type,
            "category": category_slug,
            "frequency": frequency,
            "day_value": day_value,
        }

    sign = "+" if tx_type == "income" else "−"
    cat_label = formatter.category_label(category_slug)
    # Build frequency label inline
    weekday_labels = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    if frequency == "daily":
        freq_label = "каждый день"
    elif frequency == "interval_days":
        freq_label = f"каждые {day_value} дн."
    elif frequency == "weekly":
        wl = weekday_labels[day_value] if 0 <= day_value <= 6 else "?"
        freq_label = f"каждую неделю ({wl})"
    else:
        freq_label = f"каждый месяц, {day_value}-го"

    msg = (
        "Регулярный платёж:\n"
        f"🏷 {title}\n"
        f"💰 {sign}{amount:,.0f} ₽\n"
        f"📅 {freq_label.capitalize()}\n"
        f"🗂 {cat_label}"
    )
    await update.effective_message.reply_text(msg, reply_markup=recurring_confirm_keyboard())
```

- [ ] **Step 3: Update `text_message_handler` to check mode**

In `text_message_handler` (line ~1452), add mode check right at the start, before the existing `awaiting_setting` check:

```python
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text or ""

    # --- NEW: handle input modes ---
    mode = context.user_data.get("mode") if context.user_data else None
    if mode == "planned_input":
        await _handle_planned_input(update, context, text.strip())
        return
    if mode == "recurring_input":
        await _handle_recurring_input(update, context, text.strip())
        return
    # --- END NEW ---

    # Handle settings input
    awaiting = context.user_data.get("awaiting_setting") if context.user_data else None
    ...
```

- [ ] **Step 4: Update `voice_message_handler` to check mode after download**

In `voice_message_handler` (line ~1786), after the file is downloaded to `temp_path` and before the `try:` block that calls `process_voice_message`, add the mode intercept:

```python
    await telegram_file.download_to_drive(custom_path=temp_path)

    # --- NEW: handle input modes via STT ---
    mode = context.user_data.get("mode") if context.user_data else None
    if mode in ("planned_input", "recurring_input"):
        try:
            from app.services.audio_file_service import AudioFileService
            from app.services.stt_service import STTService
            audio_svc = AudioFileService()
            wav_path = audio_svc.prepare_wav_from_ogg(temp_path)
            stt = STTService()
            stt_result = stt.transcribe(wav_path)
            transcribed = stt_result.text or ""
            if transcribed:
                if mode == "planned_input":
                    await _handle_planned_input(update, context, transcribed)
                else:
                    await _handle_recurring_input(update, context, transcribed)
            else:
                await update.effective_message.reply_text(
                    "❌ Не удалось распознать речь. Попробуй ещё раз."
                )
        except Exception as exc:
            logger.error("voice mode input error: %s", exc)
            await update.effective_message.reply_text(
                "❌ Не смог обработать голосовое. Попробуй ещё раз."
            )
        finally:
            import os as _os
            from pathlib import Path as _Path
            _Path(temp_path).unlink(missing_ok=True)
            try:
                await placeholder.delete()
            except Exception:
                pass
        return
    # --- END NEW ---

    try:
        with SessionLocal() as db:
            ...
```

- [ ] **Step 5: Run full test suite — verify no regressions**

```bash
cd backend && pytest -x -q
```

Expected: all tests pass

- [ ] **Step 6: Smoke test the flow manually**

Start the bot and:
1. Open menu → tap "📋 Запланированные" → bot shows input prompt
2. Send "маникюр 2100 рублей 15 апреля" → bot shows confirmation
3. Tap ✅ → bot saves and shows main menu
4. Open menu → tap "🔄 Регулярные" → bot shows input prompt
5. Send "аренда 30000 каждый месяц 1 числа" → bot shows confirmation
6. Tap ✅ → bot saves
7. Send a voice message "стоматолог восемь тысяч 22 апреля" while in planned mode

- [ ] **Step 7: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat: add free-form planned/recurring input with LLM extraction and confirmation"
```

---

## Final Check

- [ ] Run full suite one last time:

```bash
cd backend && pytest -q
```

Expected: all tests pass, 0 failures.
