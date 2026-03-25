# /ask Advisor Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the `/ask` feature with expanded financial context, 3-month history, follow-up dialog mode, and a main menu entry point.

**Architecture:** Extend `FinancialQAService._build_context()` with budget/planned/recurring data and multi-month aggregation. Add `mode = "advisor"` with 5-turn conversation history stored in `context.user_data`. Wire a `nav:advisor` callback and onboarding screen into the existing nav system.

**Tech Stack:** Python 3.11, FastAPI, python-telegram-bot, SQLAlchemy, Groq (OpenAI-compatible), pytest

**Spec:** `docs/superpowers/specs/2026-03-25-ask-advisor-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `backend/app/services/financial_qa_service.py` | Expand `_build_context()`, add `history` param to `answer()` |
| Modify | `backend/app/repositories/transaction_repository.py` | New `monthly_summary()` method |
| Modify | `backend/app/telegram/keyboards.py` | New keyboards, update menu layout |
| Modify | `backend/app/telegram/runtime.py` | Advisor mode routing in text/voice handlers, `nav:advisor` callback |
| Modify | `backend/app/telegram/handlers.py` | No changes needed — question detection stays, advisor routing handled in runtime.py |
| Create | `backend/tests/test_financial_qa_context.py` | Tests for expanded context and history |
| Create | `backend/tests/test_advisor_mode.py` | Tests for advisor session flow |
| Modify | `backend/tests/test_financial_qa_service.py` | Update existing tests for new `history` param |

---

## Task 1: Expand _build_context() with budgets, planned, recurring (Section A)

**Files:**
- Modify: `backend/app/services/financial_qa_service.py`
- Create: `backend/tests/test_financial_qa_context.py`

- [ ] **Step 1: Write failing test — budget data appears in context**

```python
# backend/tests/test_financial_qa_context.py
"""Tests for expanded FinancialQAService context."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.models.category_budget import CategoryBudget
from app.models.recurring_transaction import RecurringTransaction
from app.models.planned_expense import PlannedExpense
from app.models.user import User
from app.services.financial_qa_service import FinancialQAService


def _seed_user(db, uid: int = 555) -> None:
    from app.repositories.user_repository import UserRepository
    repo = UserRepository(db)
    if not repo.get_by_telegram_id(uid):
        repo.create_from_telegram(uid)


def test_context_includes_budgets(db_session) -> None:
    """_build_context() should include budget info when budgets exist."""
    _seed_user(db_session)
    budget = CategoryBudget(telegram_user_id=555, category="food", amount=15000)
    db_session.add(budget)
    db_session.commit()

    service = FinancialQAService(db_session)
    context = service._build_context(555)
    assert "БЮДЖЕТЫ" in context
    assert "food" in context
    assert "15000" in context


def test_context_includes_planned_expenses(db_session) -> None:
    """_build_context() should include upcoming planned expenses."""
    from datetime import date, timedelta
    _seed_user(db_session)
    pe = PlannedExpense(
        telegram_user_id=555,
        title="Стоматолог",
        amount=12000,
        category="health",
        planned_date=date.today() + timedelta(days=10),
    )
    db_session.add(pe)
    db_session.commit()

    service = FinancialQAService(db_session)
    context = service._build_context(555)
    assert "ПЛАНОВЫЕ РАСХОДЫ" in context
    assert "Стоматолог" in context
    assert "12000" in context


def test_context_includes_recurring(db_session) -> None:
    """_build_context() should include active recurring transactions."""
    _seed_user(db_session)
    rt = RecurringTransaction(
        telegram_user_id=555,
        title="Аренда",
        amount=45000,
        transaction_type="expense",
        frequency="monthly",
        day_value=1,
        is_active=True,
    )
    db_session.add(rt)
    db_session.commit()

    service = FinancialQAService(db_session)
    context = service._build_context(555)
    assert "РЕГУЛЯРНЫЕ ПЛАТЕЖИ" in context
    assert "Аренда" in context
    assert "45000" in context


def test_context_omits_empty_sections(db_session) -> None:
    """_build_context() should omit budget/planned/recurring sections when empty."""
    _seed_user(db_session)
    service = FinancialQAService(db_session)
    context = service._build_context(555)
    assert "БЮДЖЕТЫ" not in context
    assert "ПЛАНОВЫЕ РАСХОДЫ" not in context
    assert "РЕГУЛЯРНЫЕ ПЛАТЕЖИ" not in context
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_financial_qa_context.py -v`
Expected: 4 FAILED — context doesn't contain budget/planned/recurring data yet.

- [ ] **Step 3: Implement expanded _build_context()**

In `backend/app/services/financial_qa_service.py`, add imports and expand `_build_context()`:

```python
# Add to imports at top:
from app.repositories.category_budget_repository import CategoryBudgetRepository
from app.repositories.planned_expense_repository import PlannedExpenseRepository
from app.repositories.recurring_transaction_repository import RecurringTransactionRepository
```

Replace `_build_context()` method:

```python
def _build_context(self, telegram_user_id: int) -> str:
    repo = TransactionRepository(self.db)
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    summary = repo.get_summary(telegram_user_id, period="month")
    income = summary.get("income_total", 0)
    expenses = summary.get("expense_total", 0)
    balance = summary.get("balance", 0)

    by_category: dict = repo.sum_expenses_by_category(telegram_user_id, start=month_start, end=now)
    cat_lines = "\n".join(
        f"  {cat}: {total:.2f}₽"
        for cat, total in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)[:10]
    ) or "  нет расходов"

    recent = repo.list_for_user(telegram_user_id, limit=20, offset=0, period="month")
    recent_lines = "\n".join(
        f"  {tx.created_at.strftime('%d.%m')} {tx.type.value} {tx.amount}₽ [{tx.category}]"
        + (f" — {tx.description}" if tx.description else "")
        for tx in recent
    ) or "  нет транзакций"

    sections = [
        f"Сегодня: {today}",
        f"Баланс этого месяца: {balance:.2f}₽ "
        f"(доходы {income:.2f}₽, расходы {expenses:.2f}₽)",
        f"\nРасходы по категориям:\n{cat_lines}",
        f"\nПоследние транзакции:\n{recent_lines}",
    ]

    # Budgets
    budget_repo = CategoryBudgetRepository(self.db)
    budgets = budget_repo.get_all_for_user(telegram_user_id)
    if budgets:
        budget_lines = []
        for b in budgets:
            spent = float(by_category.get(b.category, 0))
            limit_val = float(b.amount)
            pct = int(spent / limit_val * 100) if limit_val > 0 else 0
            warn = " ⚠️" if pct >= 90 else ""
            budget_lines.append(f"  {b.category}: {limit_val:.0f}₽/мес, потрачено {spent:.0f}₽ ({pct}%){warn}")
        sections.append("\nБЮДЖЕТЫ:\n" + "\n".join(budget_lines))

    # Planned expenses
    planned_repo = PlannedExpenseRepository(self.db)
    planned = planned_repo.list_future_for_user(telegram_user_id)
    if planned:
        planned_lines = [
            f"  {p.title}: {float(p.amount):.0f}₽, {p.planned_date}"
            for p in planned[:10]
        ]
        sections.append("\nПЛАНОВЫЕ РАСХОДЫ:\n" + "\n".join(planned_lines))

    # Recurring payments
    recurring_repo = RecurringTransactionRepository(self.db)
    recurring = recurring_repo.list_active(telegram_user_id)
    if recurring:
        recurring_lines = [
            f"  {r.title}: {float(r.amount):.0f}₽/{r.frequency} ({r.transaction_type})"
            for r in recurring
        ]
        sections.append("\nРЕГУЛЯРНЫЕ ПЛАТЕЖИ:\n" + "\n".join(recurring_lines))

    return "\n".join(sections)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_financial_qa_context.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd backend && python -m pytest --tb=short -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/financial_qa_service.py backend/tests/test_financial_qa_context.py
git commit -m "feat(advisor): expand QA context with budgets, planned expenses, recurring payments"
```

---

## Task 2: Add monthly_summary() and multi-period context (Section B)

**Files:**
- Modify: `backend/app/repositories/transaction_repository.py`
- Modify: `backend/app/services/financial_qa_service.py`
- Modify: `backend/tests/test_financial_qa_context.py`

- [ ] **Step 1: Write failing test for monthly_summary()**

Append to `backend/tests/test_financial_qa_context.py`:

```python
from datetime import datetime, timedelta
from app.repositories.transaction_repository import TransactionRepository
from app.models.transaction import Transaction, TransactionType


def test_monthly_summary_returns_3_months(db_session) -> None:
    """monthly_summary() should return aggregated data for 3 months."""
    _seed_user(db_session)
    now = datetime.now()

    # Add transactions in current month and previous month
    tx1 = Transaction(
        telegram_user_id=555, type=TransactionType.EXPENSE,
        amount=1000, category="food", description="test",
        created_at=now,
    )
    prev_month = (now.replace(day=1) - timedelta(days=1))
    tx2 = Transaction(
        telegram_user_id=555, type=TransactionType.EXPENSE,
        amount=2000, category="food", description="test",
        created_at=prev_month,
    )
    db_session.add_all([tx1, tx2])
    db_session.commit()

    repo = TransactionRepository(db_session)
    result = repo.monthly_summary(555, months=3)

    assert isinstance(result, list)
    assert len(result) <= 3
    # Each entry has year_month, income, expenses, by_category
    for entry in result:
        assert "year_month" in entry
        assert "income" in entry
        assert "expenses" in entry
        assert "by_category" in entry
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_financial_qa_context.py::test_monthly_summary_returns_3_months -v`
Expected: FAIL — `monthly_summary` does not exist.

- [ ] **Step 3: Implement monthly_summary() in TransactionRepository**

Add to `backend/app/repositories/transaction_repository.py` before `_build_period_filter`:

```python
def monthly_summary(self, telegram_user_id: int, months: int = 3) -> list[dict]:
    """Return per-month income/expense totals and category breakdowns for the last N months."""
    now = datetime.now()
    # Start from the 1st of (months-1) months ago
    start_month = now.month - months + 1
    start_year = now.year
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    start = datetime(start_year, start_month, 1)

    # Fetch raw transactions and aggregate in Python (database-agnostic)
    stmt = (
        select(Transaction)
        .where(
            Transaction.telegram_user_id == telegram_user_id,
            Transaction.created_at >= start,
        )
        .order_by(Transaction.created_at.desc())
    )
    transactions = self.db.scalars(stmt).all()

    from collections import defaultdict
    months_data: dict[str, dict] = defaultdict(
        lambda: {"income": Decimal(0), "expenses": Decimal(0), "by_category": defaultdict(Decimal)}
    )

    for tx in transactions:
        ym = tx.created_at.strftime("%Y-%m")
        entry = months_data[ym]
        amount = Decimal(str(tx.amount))
        if tx.type == TransactionType.INCOME:
            entry["income"] += amount
        else:
            entry["expenses"] += amount
            entry["by_category"][tx.category] += amount

    result = []
    for ym in sorted(months_data.keys(), reverse=True):
        d = months_data[ym]
        by_cat = dict(sorted(d["by_category"].items(), key=lambda kv: kv[1], reverse=True)[:10])
        result.append({
            "year_month": ym,
            "income": d["income"],
            "expenses": d["expenses"],
            "by_category": by_cat,
        })
    return result
```

No new SQLAlchemy imports needed — aggregation is done in Python for database portability (SQLite dev / PostgreSQL prod).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_financial_qa_context.py::test_monthly_summary_returns_3_months -v`
Expected: PASS

- [ ] **Step 5: Write failing test — multi-month data in context**

Append to `backend/tests/test_financial_qa_context.py`:

```python
def test_context_includes_monthly_stats(db_session) -> None:
    """_build_context() should include multi-month statistics."""
    _seed_user(db_session)
    now = datetime.now()
    tx = Transaction(
        telegram_user_id=555, type=TransactionType.EXPENSE,
        amount=5000, category="food", description="test",
        created_at=now,
    )
    db_session.add(tx)
    db_session.commit()

    service = FinancialQAService(db_session)
    context = service._build_context(555)
    assert "ПОМЕСЯЧНАЯ СТАТИСТИКА" in context
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_financial_qa_context.py::test_context_includes_monthly_stats -v`
Expected: FAIL

- [ ] **Step 7: Add monthly stats to _build_context()**

In `backend/app/services/financial_qa_service.py`, add the monthly stats section to `_build_context()` — insert before the budgets section:

```python
    # Monthly stats (3 months)
    monthly = repo.monthly_summary(telegram_user_id, months=3)
    if monthly:
        monthly_lines = []
        for m in monthly:
            cat_str = ", ".join(
                f"{cat}: {amt:.0f}₽"
                for cat, amt in m["by_category"].items()
            )
            monthly_lines.append(
                f"  {m['year_month']}: доходы {m['income']:.0f}₽, расходы {m['expenses']:.0f}₽"
                + (f"\n    {cat_str}" if cat_str else "")
            )
        sections.append("\nПОМЕСЯЧНАЯ СТАТИСТИКА:\n" + "\n".join(monthly_lines))
```

- [ ] **Step 8: Run all context tests**

Run: `cd backend && python -m pytest tests/test_financial_qa_context.py -v`
Expected: All PASSED

- [ ] **Step 9: Run full test suite**

Run: `cd backend && python -m pytest --tb=short -q`
Expected: All pass.

- [ ] **Step 10: Commit**

```bash
git add backend/app/repositories/transaction_repository.py backend/app/services/financial_qa_service.py backend/tests/test_financial_qa_context.py
git commit -m "feat(advisor): add 3-month history and multi-period context to QA"
```

---

## Task 3: Add history parameter to answer() (Section C2 — service layer)

**Files:**
- Modify: `backend/app/services/financial_qa_service.py`
- Modify: `backend/tests/test_financial_qa_service.py`

- [ ] **Step 1: Write failing test — answer() accepts history**

Append to `backend/tests/test_financial_qa_service.py`:

```python
def test_financial_qa_passes_history_to_llm(db_session) -> None:
    """answer() should include conversation history in LLM messages."""
    service = FinancialQAService(db_session)
    captured_messages: list = []

    def fake_create(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        fake_resp = MagicMock()
        fake_resp.choices[0].message.content = '{"answer": "Ответ с историей"}'
        return fake_resp

    history = [
        {"role": "user", "content": "сколько я потратил?"},
        {"role": "assistant", "content": "5000₽ за этот месяц."},
    ]

    with patch.object(service._client.chat.completions, "create", side_effect=fake_create):
        result = service.answer("а на еду?", telegram_user_id=555, history=history)

    assert result == "Ответ с историей"
    # Messages should be: system, history[0], history[1], user question
    assert len(captured_messages) == 4
    assert captured_messages[0]["role"] == "system"
    assert captured_messages[1]["content"] == "сколько я потратил?"
    assert captured_messages[2]["content"] == "5000₽ за этот месяц."
    assert captured_messages[3]["content"] == "а на еду?"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_financial_qa_service.py::test_financial_qa_passes_history_to_llm -v`
Expected: FAIL — `answer()` doesn't accept `history` param.

- [ ] **Step 3: Update answer() to accept history**

In `backend/app/services/financial_qa_service.py`, update the `answer()` method:

```python
def answer(self, question: str, telegram_user_id: int, history: list[dict] | None = None) -> str:
    """Answer a financial question using the user's real transaction data."""
    context = self._build_context(telegram_user_id)
    system = self._build_system_prompt(context)
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})
    try:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        raw = response.choices[0].message.content or ""
        data = json.loads(raw)
        return (data.get("answer") or "").strip() or _FALLBACK
    except APIError as exc:
        logger.error("FinancialQA LLM error: %s", exc)
        return _FALLBACK
    except Exception as exc:
        logger.error("FinancialQA unexpected error: %s", exc)
        return _FALLBACK
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_financial_qa_service.py -v`
Expected: All PASSED (existing tests still work because `history` defaults to `None`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/financial_qa_service.py backend/tests/test_financial_qa_service.py
git commit -m "feat(advisor): add conversation history support to FinancialQAService.answer()"
```

---

## Task 4: Add advisor keyboards (Section D1 — keyboards)

**Files:**
- Modify: `backend/app/telegram/keyboards.py`

- [ ] **Step 1: Add MENU_BTN_ADVISOR constant and update main_menu_inline_keyboard()**

In `backend/app/telegram/keyboards.py`, add the constant after `MENU_BTN_CATEGORIES`:

```python
MENU_BTN_ADVISOR  = "🧠 Советник"
```

Update `main_menu_inline_keyboard()` to:

```python
def main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("📊 Сводка", "nav:stats")],
        [_btn(MENU_BTN_PLANNED, "nav:planned_input"), _btn(MENU_BTN_RECURRING, "nav:recurring_input")],
        [_btn(MENU_BTN_BUDGETS, "nav:budgets"), _btn(MENU_BTN_ADVISOR, "nav:advisor")],
        [_btn(MENU_BTN_SETTINGS, "nav:settings"), _btn(MENU_BTN_HELP, "nav:help")],
    ])
```

Note: `MENU_BTN_CATEGORIES` button is removed from menu — categories are accessible via settings. This matches the spec.

- [ ] **Step 2: Add advisor_session_keyboard() and advisor_enter_keyboard()**

Add after `advisor_keyboard()`:

```python
def advisor_session_keyboard() -> InlineKeyboardMarkup:
    """Keyboard shown after each advisor answer in dialog mode: [✕ Завершить]."""
    return InlineKeyboardMarkup([[_btn("✕ Завершить", "nav:menu")]])


def advisor_onboarding_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for advisor onboarding screen: [✕ Назад]."""
    return InlineKeyboardMarkup([[_back_btn(), _menu_btn()]])
```

- [ ] **Step 3: Update advisor_keyboard() to include "continue in advisor" button**

Replace `advisor_keyboard()`:

```python
def advisor_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for one-off QA responses (outside advisor mode): [🧠 Продолжить в советнике] [≡ Меню]."""
    return InlineKeyboardMarkup([
        [_btn("🧠 Продолжить в советнике", "nav:advisor")],
        [_btn("📊 Сводка", "nav:stats"), _menu_btn()],
    ])
```

- [ ] **Step 4: Run full test suite to check for regressions**

Run: `cd backend && python -m pytest --tb=short -q`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/telegram/keyboards.py
git commit -m "feat(advisor): add advisor keyboards and menu button"
```

---

## Task 5: Wire nav:advisor callback and onboarding screen (Section D1 — routing)

**Files:**
- Modify: `backend/app/telegram/runtime.py`

- [ ] **Step 1: Add nav:advisor handler in nav_callback_handler()**

In `backend/app/telegram/runtime.py`, inside `nav_callback_handler()`, add a new `elif` branch after the `elif section == "categories":` block (around line 1251) and before `elif section == "help":`:

```python
            elif section == "advisor":
                context.user_data["mode"] = "advisor"
                context.user_data["advisor_history"] = []
                context.user_data["advisor_last_active"] = _time_now()
                from app.telegram.keyboards import advisor_onboarding_keyboard
                try:
                    await query.edit_message_text(
                        _ADVISOR_ONBOARDING,
                        reply_markup=advisor_onboarding_keyboard(),
                        parse_mode="Markdown",
                    )
                except BadRequest:
                    await update.effective_chat.send_message(
                        _ADVISOR_ONBOARDING,
                        reply_markup=advisor_onboarding_keyboard(),
                        parse_mode="Markdown",
                    )
                return
```

- [ ] **Step 2: Add _time_now() helper and onboarding constant at module level**

Add near top of `runtime.py` (after imports):

```python
import time as _time

def _time_now() -> float:
    return _time.time()

_ADVISOR_ONBOARDING = (
    "🧠 *Финансовый советник*\n\n"
    "Задай любой вопрос о своих финансах. Например:\n"
    "• Сколько я трачу на еду в месяц?\n"
    "• Укладываюсь ли я в бюджеты?\n"
    "• Какие крупные платежи скоро?\n"
    "• Как изменились мои расходы за 3 месяца?\n\n"
    "Напиши вопрос текстом или голосом 👇"
)
```

Use `_ADVISOR_ONBOARDING` in both the `nav:advisor` handler (Task 5 Step 1) and `ask_command` (Task 8 Step 1) instead of duplicating the text.

- [ ] **Step 3: Update mode-clearing in nav_callback_handler to also clear advisor state**

The existing code at line 1188-1191 already clears `mode`. Add `advisor_history` and `advisor_last_active` cleanup:

```python
    # Clear any pending input mode on navigation
    if context.user_data:
        context.user_data.pop("mode", None)
        context.user_data.pop("pending_planned", None)
        context.user_data.pop("pending_recurring", None)
        context.user_data.pop("advisor_history", None)
        context.user_data.pop("advisor_last_active", None)
```

- [ ] **Step 4: Run full test suite**

Run: `cd backend && python -m pytest --tb=short -q`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat(advisor): wire nav:advisor callback with onboarding screen"
```

---

## Task 6: Advisor mode routing for text messages (Section C2 — text)

**Files:**
- Modify: `backend/app/telegram/runtime.py`
- Create: `backend/tests/test_advisor_mode.py`

- [ ] **Step 1: Write test for advisor mode text routing**

```python
# backend/tests/test_advisor_mode.py
"""Tests for advisor dialog mode."""
import time
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


def test_advisor_history_caps_at_5_pairs() -> None:
    """History should keep max 5 question-answer pairs (10 messages)."""
    history: list[dict] = []
    for i in range(6):
        history.append({"role": "user", "content": f"q{i}"})
        history.append({"role": "assistant", "content": f"a{i}"})
        # Trim to 5 pairs
        if len(history) > 10:
            history = history[2:]

    assert len(history) == 10
    assert history[0]["content"] == "q1"  # q0/a0 was trimmed
    assert history[-1]["content"] == "a5"


def test_advisor_auto_clears_after_timeout() -> None:
    """If advisor_last_active > 10 min ago, history should be cleared."""
    last_active = time.time() - 700  # 11+ minutes ago
    timeout = 600  # 10 minutes
    should_clear = (time.time() - last_active) > timeout
    assert should_clear is True


def test_advisor_no_clear_within_timeout() -> None:
    """If advisor_last_active < 10 min ago, history should be kept."""
    last_active = time.time() - 300  # 5 minutes ago
    timeout = 600
    should_clear = (time.time() - last_active) > timeout
    assert should_clear is False


def test_financial_qa_called_with_history(db_session) -> None:
    """FinancialQAService.answer() should receive history from advisor mode."""
    from unittest.mock import patch, MagicMock
    from app.services.financial_qa_service import FinancialQAService

    service = FinancialQAService(db_session)
    captured_history = []

    original_answer = service.answer

    def spy_answer(question, telegram_user_id, history=None):
        captured_history.append(history)
        fake_resp = MagicMock()
        fake_resp.choices[0].message.content = '{"answer": "test"}'
        with patch.object(service._client.chat.completions, "create", return_value=fake_resp):
            return original_answer(question, telegram_user_id, history=history)

    history = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]

    with patch.object(service, "answer", side_effect=spy_answer):
        service.answer("q2", 555, history=history)

    assert len(captured_history) == 1
    assert captured_history[0] == history
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_advisor_mode.py -v`
Expected: All PASSED (these are unit logic tests).

- [ ] **Step 3: Add advisor mode handling in text_message_handler()**

In `backend/app/telegram/runtime.py`, in `text_message_handler()`, add after the existing mode checks (after line 1868 — `budget_category_input` return) and before the settings check:

```python
    if mode == "advisor":
        await _handle_advisor_text(update, context, text.strip())
        return
```

- [ ] **Step 4: Implement _handle_advisor_text()**

Add the helper function in `runtime.py` (near other `_handle_*` functions):

```python
_ADVISOR_TIMEOUT = 600  # 10 minutes


async def _handle_advisor_text(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str) -> None:
    """Handle text input in advisor mode — route to FinancialQAService with history."""
    from app.telegram.keyboards import advisor_session_keyboard

    # Auto-clear stale history
    last_active = context.user_data.get("advisor_last_active", 0)
    if (_time_now() - last_active) > _ADVISOR_TIMEOUT:
        context.user_data["advisor_history"] = []

    history: list[dict] = context.user_data.get("advisor_history", [])

    await update.effective_message.reply_text("🤔 Анализирую…")

    with SessionLocal() as db:
        _ensure_user(db, update)
        answer = FinancialQAService(db).answer(question, update.effective_user.id, history=history)

    # Update history (cap at 5 pairs = 10 messages)
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": answer})
    if len(history) > 10:
        history = history[2:]
    context.user_data["advisor_history"] = history
    context.user_data["advisor_last_active"] = _time_now()

    await update.effective_message.reply_text(answer, reply_markup=advisor_session_keyboard())
```

- [ ] **Step 5: Update action == "advisor" routing for one-off questions**

In `text_message_handler()`, the advisor action from `handle_text()` falls through to the generic handler at line 2195. Add explicit handling before that fallthrough (around line 2194):

```python
    if action == "advisor":
        from app.telegram.keyboards import advisor_keyboard
        await update.effective_message.reply_text(
            response["message"],
            parse_mode="HTML",
            reply_markup=advisor_keyboard(),
        )
        return
```

This ensures one-off questions (outside advisor mode) get the `[🧠 Продолжить в советнике]` button.

- [ ] **Step 6: Run full test suite**

Run: `cd backend && python -m pytest --tb=short -q`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/telegram/runtime.py backend/tests/test_advisor_mode.py
git commit -m "feat(advisor): add follow-up dialog mode for text messages"
```

---

## Task 7: Advisor mode routing for voice messages (Section C2 — voice)

**Files:**
- Modify: `backend/app/telegram/runtime.py`

- [ ] **Step 1: Add advisor mode handling in voice_message_handler()**

In `voice_message_handler()`, in the mode check block (line 2223), add `"advisor"` to the recognized modes:

```python
    if mode in ("planned_input", "recurring_input", "budget_total_input", "budget_category_input", "advisor"):
```

Then inside the `if transcribed:` block, add the advisor branch:

```python
                if mode == "planned_input":
                    await _handle_planned_input(update, context, transcribed)
                elif mode == "recurring_input":
                    await _handle_recurring_input(update, context, transcribed)
                elif mode == "budget_total_input":
                    await _handle_budget_total_input(update, context, transcribed)
                elif mode == "advisor":
                    await _handle_advisor_text(update, context, transcribed)
                else:
                    await _handle_budget_category_input(update, context, transcribed)
```

- [ ] **Step 2: Run full test suite**

Run: `cd backend && python -m pytest --tb=short -q`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat(advisor): support voice input in advisor dialog mode"
```

---

## Task 8: Update /ask command to enter advisor mode (polish)

**Files:**
- Modify: `backend/app/telegram/runtime.py`

- [ ] **Step 1: Update ask_command to set advisor mode when no question provided**

Replace the `ask_command` function (lines 517-529):

```python
async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        # Enter advisor mode (same as nav:advisor button)
        context.user_data["mode"] = "advisor"
        context.user_data["advisor_history"] = []
        context.user_data["advisor_last_active"] = _time_now()
        from app.telegram.keyboards import advisor_onboarding_keyboard
        await update.effective_message.reply_text(
            _ADVISOR_ONBOARDING,
            reply_markup=advisor_onboarding_keyboard(),
            parse_mode="Markdown",
        )
        return
    # Direct question — answer immediately (one-off, no dialog mode)
    await update.effective_message.reply_text("🤔 Анализирую…")
    with SessionLocal() as db:
        _ensure_user(db, update)
        answer = FinancialQAService(db).answer(question, update.effective_user.id)
    await update.effective_message.reply_text(answer, reply_markup=advisor_keyboard())
```

- [ ] **Step 2: Run full test suite**

Run: `cd backend && python -m pytest --tb=short -q`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat(advisor): /ask without args enters advisor dialog mode"
```

---

## Task 9: Final integration verification

- [ ] **Step 1: Run full test suite**

Run: `cd backend && python -m pytest -v`
Expected: All tests pass.

- [ ] **Step 2: Run lint/typecheck on changed files**

Run: `cd backend && python -m py_compile app/services/financial_qa_service.py && python -m py_compile app/repositories/transaction_repository.py && python -m py_compile app/telegram/runtime.py && python -m py_compile app/telegram/keyboards.py && echo "OK"`
Expected: OK

- [ ] **Step 3: Manual smoke test checklist** (if bot is running)

1. Open Telegram → main menu shows `[🧠 Советник]` button
2. Tap `[🧠 Советник]` → onboarding screen with examples appears
3. Type "сколько я потратил?" → get answer with `[✕ Завершить]` button
4. Type follow-up "а на еду?" → get answer using context from previous question
5. Tap `[✕ Завершить]` → returns to main menu
6. Type a question outside advisor mode → get answer with `[🧠 Продолжить в советнике]` button
7. Send `/ask сколько я потратил на еду?` → get direct answer
8. Send `/ask` without args → enter advisor mode

- [ ] **Step 4: Commit if any fixes were needed**

```bash
git add -u
git commit -m "fix(advisor): integration fixes"
```
