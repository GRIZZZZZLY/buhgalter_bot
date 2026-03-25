# Design: /ask Advisor Improvements (A+B+C2+D1)

**Date:** 2026-03-25
**Status:** Approved

## Overview

Enhance the existing `/ask` Conversational Financial Intelligence feature with:
- **A** — Expanded data context (budgets, planned expenses, recurring payments)
- **B** — Multi-period analysis (3-month breakdown)
- **C2** — Full follow-up dialog (5-turn conversation memory)
- **D1** — Main menu button + onboarding screen with example questions

## A: Expanded Data Context

### Current state
`FinancialQAService._build_context()` collects: monthly balance, expenses by category, last 20 transactions.

### Changes
Add three new sections to the LLM system prompt context:

**Budgets:**
```
БЮДЖЕТЫ:
  food: 15000₽/мес, потрачено 8200₽ (55%)
  transport: 5000₽/мес, потрачено 4800₽ (96%) ⚠️
```
Source: `BudgetRepository.get_all_for_user()` + `TransactionRepository.sum_expenses_by_category()`.

**Planned expenses:**
```
ПЛАНОВЫЕ РАСХОДЫ:
  Стоматолог: 12000₽, 2026-04-01
  Страховка авто: 35000₽, 2026-04-15
```
Source: `PlannedExpenseRepository.list_upcoming()`.

**Recurring payments:**
```
РЕГУЛЯРНЫЕ ПЛАТЕЖИ:
  Аренда: 45000₽/мес (расход)
  Зарплата: 150000₽/мес (доход)
```
Source: `RecurringTransactionRepository.list_for_user()`.

### Files changed
- `backend/app/services/financial_qa_service.py` — `_build_context()` method

## B: Multi-Period Analysis

### Current state
Only current month data is provided to LLM.

### Changes
Provide 3-month rolling breakdown in the prompt:

```
ПОМЕСЯЧНАЯ СТАТИСТИКА:
  Март 2026: доходы 150000₽, расходы 82000₽
    food: 15200₽, transport: 4800₽, entertainment: 8500₽ ...
  Февраль 2026: доходы 150000₽, расходы 75000₽
    food: 14100₽, transport: 5200₽, entertainment: 6300₽ ...
  Январь 2026: доходы 148000₽, расходы 79000₽
    food: 13800₽, transport: 4500₽, entertainment: 9200₽ ...
```

LLM selects relevant data from the context based on the question. No period extraction logic on Python side.

Last 20 transactions remain current-month only (for detail).

### Files changed
- `backend/app/repositories/transaction_repository.py` — new method `monthly_summary(telegram_user_id, months=3)` returning per-month income/expense totals and category breakdowns
- `backend/app/services/financial_qa_service.py` — `_build_context()` uses `monthly_summary()`

## C2: Follow-Up Dialog (5-Turn Memory)

### State management
- `context.user_data["advisor_history"]: list[dict]` — conversation messages
- `context.user_data["advisor_last_active"]: float` — timestamp of last interaction
- `context.user_data["mode"] = "advisor"` — routes all text/voice to QA

### Conversation flow
1. User enters advisor mode (menu button or `/ask`)
2. `advisor_history` initialized as `[]`
3. Each exchange appends `{"role": "user", "content": question}` and `{"role": "assistant", "content": answer}`
4. Max 5 pairs (10 messages). On overflow — oldest pair removed (FIFO)
5. History passed to `FinancialQAService.answer(question, user_id, history=...)`
6. LLM call: `[system_prompt, *history, {"role": "user", "content": question}]`

### Exit conditions
- Button `[✕ Завершить]` — clears history, returns to main menu
- Auto-clear: if `advisor_last_active` > 10 minutes ago — reset history on next message
- Any nav callback or other command — exits advisor mode

### Message routing
- When `mode == "advisor"`: text messages → `FinancialQAService`, bypassing transaction parser
- Voice in advisor mode: STT → text → QA (not treated as transaction)

### Keyboard after each answer
```
[🔄 Ещё вопрос] [✕ Завершить]
```

### Files changed
- `backend/app/services/financial_qa_service.py` — `answer()` accepts `history` parameter, passes to LLM
- `backend/app/telegram/handlers.py` — advisor mode routing in `process_message()`
- `backend/app/telegram/runtime.py` — advisor mode handling for text and voice messages
- `backend/app/telegram/keyboards.py` — new `advisor_session_keyboard()`

## D1: Main Menu Button + Onboarding

### Main menu layout
```
[📊 Сводка]
[📋 Запланированные | 🔄 Регулярные]
[💰 Бюджеты   | 🧠 Советник]
[⚙️ Настройки  | ℹ️ Помощь]
```

Callback: `nav:advisor`.

### Onboarding screen (on button press)
```
🧠 Финансовый советник

Задай любой вопрос о своих финансах. Например:
• Сколько я трачу на еду в месяц?
• Укладываюсь ли я в бюджеты?
• Какие крупные платежи скоро?
• Как изменились мои расходы за 3 месяца?

Напиши вопрос текстом или голосом 👇

[✕ Назад]
```

Sets `mode = "advisor"`, initializes `advisor_history = []`.

### Auto-detected questions outside advisor mode
When `_looks_like_question()` catches a question outside advisor mode, the response keyboard changes from `advisor_keyboard()` to include `[🧠 Продолжить в советнике]` — allowing the user to enter follow-up dialog mode.

### Files changed
- `backend/app/telegram/keyboards.py` — update `main_menu_inline_keyboard()`, new `advisor_onboarding_keyboard()`, update `advisor_keyboard()` with "continue in advisor" button
- `backend/app/services/nav_service.py` — handle `nav:advisor`
- `backend/app/telegram/runtime.py` — register `nav:advisor` callback

## Implementation Order

1. **A** — Expand `_build_context()` with budgets, planned, recurring
2. **B** — Add `monthly_summary()` repo method, integrate into context
3. **D1** — Menu button, onboarding screen, nav callback
4. **C2** — Follow-up dialog with history management

Each step is a separate commit with tests.

## Testing Strategy

- **A**: Test that prompt contains budget/planned/recurring data when present
- **B**: Test `monthly_summary()` returns correct aggregation; test prompt contains multi-month data
- **C2**: Test history accumulates, caps at 5 pairs, auto-clears after timeout, exits on nav
- **D1**: Test `nav:advisor` sets mode, onboarding message sent, keyboard correct

## Risks

- **Prompt size**: Adding 3 months of data + budgets + planned + recurring may approach token limits for users with many categories. Mitigation: cap category lines at 10 per month (top by amount).
- **Mode conflicts**: Advisor mode must be cleared when user navigates elsewhere. Mitigation: clear `mode` in all nav callbacks (already done for other modes).
- **LLM latency**: More context = slower responses. Mitigation: Groq is fast; 3 months of aggregated data is ~500 tokens max.
