# Savings Goals ("Копилка") — Design Spec

**Date:** 2026-03-25
**Status:** Approved
**Project:** buhgalter_bot

---

## Overview

Allows users to create multiple savings goals (e.g. "iPhone 14 Pro — 120 000₽", "Отпуск в Турции — 80 000₽"), track progress, and auto-deduct a configurable percentage from each income transaction. LLM handles parsing and natural language advice; deadline calculations are deterministic.

---

## Data Model

Table: `savings_goals`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | — |
| `user_id` | int | telegram_user_id, indexed |
| `title` | str | "Отпуск в Турции" |
| `target_amount` | Decimal | required, > 0 |
| `current_amount` | Decimal | default 0 |
| `deadline` | date? | optional |
| `auto_percent` | int? | 0–100, % of each income |
| `is_active` | bool | default True |
| `created_at` | datetime | UTC |

Constraints: `auto_percent` between 0 and 100 inclusive; `target_amount` > 0.

---

## Architecture

### New files

- `backend/app/models/savings_goal.py` — ORM model
- `backend/app/repositories/savings_goal_repository.py` — CRUD + fuzzy title match (difflib)
- `backend/app/services/savings_goal_service.py` — business logic
- `backend/alembic/versions/XXXX_create_savings_goals.py` — migration
- `backend/tests/test_savings_goal_service.py` — TDD tests

### Modified files

- `backend/app/services/llm_service.py` — add `extract_savings_goal(text)`
- `backend/app/services/transaction_service.py` — income hook → `SavingsGoalService.process_income()`
- `backend/app/telegram/handlers.py` — add `_looks_like_savings_deposit()`, route before parser
- `backend/app/telegram/runtime.py` — `/goals`, `/goal` commands
- `backend/app/telegram/keyboards.py` — goal list and confirmation keyboards

---

## Core Service: SavingsGoalService

```
create(user_id, title, target_amount, deadline?, auto_percent?) → SavingsGoal
deposit(user_id, goal_id, amount) → (SavingsGoal, reached: bool)
process_income(user_id, income_amount) → list[(SavingsGoal, deposited, reached)]
list_active(user_id) → list[SavingsGoal]
complete(user_id, goal_id) → SavingsGoal
delete(user_id, goal_id) → bool
calculate_forecast(goal) → {months_remaining, needed_per_month, on_track: bool, suggested_percent?}
```

`calculate_forecast` is fully deterministic — no LLM:
```
remaining = target - current
monthly_rate = avg_monthly_income × auto_percent / 100
months = remaining / monthly_rate  (or None if rate == 0)
on_track = months <= months_to_deadline (if deadline set)
suggested_percent = ceil(remaining / months_to_deadline / avg_income × 100) + 1
```

---

## LLM Integration

### Role 1 — Parsing goal creation
`LLMService.extract_savings_goal(text) → {title, target_amount, deadline_iso?, auto_percent?}`

Called when user creates a goal via free text. If `target_amount` is missing from LLM result, bot asks the user before creating the goal (no silent zero-amount goals).

### Role 2 — Deposit recognition (fuzzy-first)
When `_looks_like_savings_deposit(text)` is True:
1. Extract amount with `ParserService._extract_amount()`
2. Fuzzy-match goal title with `difflib.SequenceMatcher` against active goals
3. If confidence ≥ 0.8 → deposit directly
4. If confidence < 0.8 → call LLM with goal list to resolve
5. If amount missing → ask user

### Role 3 — Advisor (deterministic + LLM formatting)
When user asks "когда накоплю на iPhone?":
1. Python calculates forecast (months, rate, on_track)
2. Pass calculated numbers + goal data to `FinancialQAService`
3. LLM formats natural language answer — no token waste on math

### Role 4 — Behind-schedule warning
Triggered deterministically (not by LLM) when deposit occurs and `on_track == False`:
- Python computes gap and `suggested_percent`
- LLM formats warning message
- Inline button: "Увеличить до X%?" → updates `auto_percent`

---

## Telegram UX

### Creating a goal
Free text: `"хочу накопить на iPhone 120к к декабрю, откладывать 10%"`
Or command: `/goal`

Bot shows confirmation card:
```
🎯 iPhone 14 Pro
Цель: 120 000₽  |  Накоплено: 0₽
Дедлайн: декабрь 2026
Авто: 10% от каждого дохода
[✅ Создать]  [✏️ Изменить]
```

If LLM couldn't extract `target_amount` → bot asks: "Сколько нужно накопить?"

### Viewing goals — `/goals`
```
🎯 iPhone 14 Pro
████░░░░░░ 35% (42 000 / 120 000₽)
До дедлайна: 8 мес. • Авто: 10%
[+ Пополнить]  [⚙️ Настроить]

🎯 Отпуск в Турции
██████████ 100% 🎉
[✅ Завершить]
```

### Manual deposit
`"положил 3000 на отпуск"` or `"пополнил копилку на айфон"`
→ fuzzy match → deposit → confirmation message

### Behind-schedule warning (on deposit)
```
⚠️ Отстаёшь от графика!
Нужно: 6 500₽/мес | Откладываешь: ~4 200₽/мес
Увеличить авто-процент с 10% до 16%?
[Да, увеличить]  [Оставить как есть]
```

### Goal reached
```
🎉 Цель достигнута! iPhone 14 Pro — 120 000₽ накоплено!
[✅ Завершить копилку]  [🔄 Новая цель]
```

---

## Auto-deduction Flow

When `TransactionService.create_from_parse()` creates an income transaction:
```python
income_amount = tx.amount
results = savings_goal_service.process_income(user_id, income_amount)
for goal, deposited, reached in results:
    # bot notifies about auto-deposit
    # if reached → congratulation message
```

Each active goal with `auto_percent > 0` receives `income × auto_percent / 100`.

---

## Deposit Detection

```python
@staticmethod
def _looks_like_savings_deposit(text: str) -> bool:
    keywords = ["отложил", "положил в копилку", "пополнил копилку",
                "пополнил цель", "накопил", "добавил в копилку"]
    t = text.lower()
    return any(kw in t for kw in keywords)
```

Checked in `handle_text()` AFTER `voice_edit` check, BEFORE `_looks_like_question` and `ParserService`.

---

## Validation Rules

- `target_amount` must be > 0 — bot prompts if LLM returns None
- `auto_percent` must be 0–100 — clamp silently
- `deadline` must be in the future — warn if in the past
- Cannot deposit to completed (`is_active=False`) goals

---

## Implementation Iterations

### Iteration 1 — Backend core
1. ORM model + Alembic migration
2. Repository (CRUD + fuzzy match)
3. `SavingsGoalService` (create, deposit, process_income, forecast)
4. TDD tests

### Iteration 2 — Telegram UX + LLM
1. `extract_savings_goal` in LLMService
2. `_looks_like_savings_deposit` + routing in handlers.py
3. `/goals`, `/goal` commands in runtime.py
4. Keyboards
5. Auto-deduction hook in transaction_service.py

---

## Testing Strategy

TDD throughout. Key test cases:
- `create` with valid/invalid amounts
- `deposit` increments `current_amount`, returns `reached=True` at 100%
- `process_income` distributes to all goals with `auto_percent > 0`
- `calculate_forecast` correct math for on-track / behind-schedule
- Fuzzy match: "айфон" matches "iPhone 14 Pro"
- `_looks_like_savings_deposit` positive/negative cases
- LLM unavailable → graceful fallback (goal not created, user prompted)
