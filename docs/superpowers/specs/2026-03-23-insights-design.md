# Insights & Motivational Replies — Design Spec

**Date:** 2026-03-23
**Status:** Approved
**Scope:** Proactive spending insights and motivational messages based on usage patterns

---

## Goal

Send smart, personalized insights to the user at two moments:
1. **Real-time** — right after saving a transaction (max once per day)
2. **Scheduled** — as an appended paragraph in existing morning and evening messages

Rules decide *when* and *what* to notice; LLM writes the *text*.

---

## Architecture

### New file: `backend/app/services/insight_service.py`

```python
class InsightService:
    def __init__(self, db: Session) -> None: ...

    def get_realtime_insight(self, user: User, transaction) -> str | None:
        """Called after transaction save. Returns insight text or None.
        Skips if user already received an insight today (cooldown)."""

    def get_scheduled_insight(self, user: User) -> str | None:
        """Called from scheduler (morning only). Applies same daily cooldown as get_realtime_insight."""
```

### `InsightFact` dataclass

```python
@dataclass
class InsightFact:
    type: str    # "category_spike" | "budget_milestone" | "weekly_anomaly" | "category_record" | "motivational_streak"
    data: dict   # detector-specific payload, passed as-is to LLM
```

---

## Date Window Definitions

All detectors use **rolling windows** (no ISO calendar):

- **"this week"** = last 7 days (days 0–6 ago, inclusive of today)
- **"last week"** = days 7–13 ago
- **"this month"** = last 30 days
- **"last month"** = days 30–59 ago

---

## Detectors

Five detectors run in priority order. First match wins. Each is a private method returning `InsightFact | None`.

### 1. `_detect_category_spike`
Query expense transactions for "this week" and "last week" grouped by `category`.
For each category: if `this_week_sum > last_week_sum * 1.5` AND `this_week_sum - last_week_sum > 500` → return fact.
Return the category with the largest absolute delta. If no category passes → `None`.

```python
InsightFact(type="category_spike", data={
    "category": "еда", "this_week": 3200, "last_week": 1800, "delta_pct": 78
})
```

### 2. `_detect_budget_milestone`
Skip if `user.budget_amount is None` → return `None`.

Daily budget limit = `user.budget_amount / 30` (fixed denominator, simple).

For each of the last 30 days: sum all expense transactions on that date (user's timezone). Count the longest consecutive streak of days where `daily_sum <= daily_limit`. If streak ∈ {7, 14, 30} AND today is the last day of the streak → return fact.

```python
InsightFact(type="budget_milestone", data={"streak_days": 7, "daily_limit": 1667})
```

### 3. `_detect_weekly_anomaly`
Sum expenses for "this week". Compute average weekly spend over "last month" (= total last-month expenses / 4).
If `this_week_sum > avg_weekly * 1.3` → return fact. If no history → `None`.

```python
InsightFact(type="weekly_anomaly", data={"this_week": 12400, "avg_weekly": 9000, "delta_pct": 38})
```

### 4. `_detect_category_record`
For each category: compare "this month" vs "last month" totals.
If `this_month > last_month * 1.4` AND `last_month > 0` → return fact (largest relative delta).

```python
InsightFact(type="category_record", data={"category": "кафе", "this_month": 4200, "last_month": 2800})
```

### 5. `_detect_motivational_streak`
Read `user.transactions_today` (existing cached int counter on `User` model, maintained by the save flow).
If `user.transactions_today >= 3` → return fact.

```python
InsightFact(type="motivational_streak", data={"count": 5})
```

New detectors (e.g., savings goals, debt payoff progress) can be added later by inserting a new method into the priority list — no other changes required.

---

## LLM Text Generation

When a detector fires, one LLM call (Groq `llama-3.3-70b-versatile`) generates the message text.

**System prompt:**
```
Ты финансовый ассистент. Напиши 1-2 живых предложения на русском языке
по данному инсайту. Тон: дружелюбный, без занудства, с уместным эмодзи.
```

**User message:** the `InsightFact` serialized as JSON.

**Example outputs:**
- `category_spike` → *"Кажется, на еду в этот раз уходит заметно больше — уже 3 200 ₽, это +80% к прошлой неделе 🍕 Может, стоит притормозить?"*
- `budget_milestone` → *"7 дней в бюджете — это уже серьёзно 💪 Так держать!"*
- `weekly_anomaly` → *"Эта неделя идёт на треть дороже обычной — 12 400 ₽ против ~9 000 ₽ 📈"*

If `LLMUnavailableError` is raised → catch silently, return `None`. The bot continues working normally.

---

## Cooldown & Delivery

### Cooldown (shared — real-time and scheduled)

- New column `last_insight_at: DateTime(timezone=True) | None` on `users` table
- **`today`** is always derived as `datetime.now(ZoneInfo(user.timezone)).date()`
- Before running detectors in **both** `get_realtime_insight` and `get_scheduled_insight`: if `last_insight_at` is not None AND `last_insight_at.astimezone(ZoneInfo(user.timezone)).date() == today` → return `None`
- After generating text: `user.last_insight_at = datetime.now(timezone.utc)`, then `db.commit()`
- Result: maximum **one insight per user per day** regardless of source (real-time or scheduled)

### Delivery

| Context | How delivered |
|---|---|
| After transaction save (`runtime.py`) | Separate message immediately after save confirmation |
| Morning briefing (`scheduler_service.py`) | Appended as extra paragraph at end of existing message |

**Evening check-in is excluded** — it already has action buttons and category UI; appending an insight there would add noise. Scheduled insights are morning-only.

If the morning message has no content (no transactions to report), the insight is also skipped — it lives inside an existing message, not standalone.

---

## DB Change

Add one column to `users` table:

```python
last_insight_at = Column(DateTime(timezone=True), nullable=True, default=None)
```

Migration: `backend/alembic/versions/YYYYMMDD_NNNN_add_last_insight_at_to_users.py`

---

## Wiring

### `runtime.py`
After the `action == "saved"` block that sends the confirmation:
```python
insight = InsightService(db).get_realtime_insight(user, saved_tx)
if insight:
    await update.effective_message.reply_text(insight, parse_mode="HTML")
```

### `scheduler_service.py`
In `_check_morning_reminders` only, after building the main message:
```python
insight = InsightService(db).get_scheduled_insight(user)
if insight:
    message += f"\n\n💡 {insight}"
```

---

## Files Changed

| File | Action |
|---|---|
| `backend/app/services/insight_service.py` | **Create** |
| `backend/app/models/user.py` | Modify — add `last_insight_at` column |
| `backend/alembic/versions/..._add_last_insight_at.py` | **Create** |
| `backend/app/telegram/runtime.py` | Modify — call `get_realtime_insight` after save |
| `backend/app/services/scheduler_service.py` | Modify — call `get_scheduled_insight` in morning briefing only (`_check_morning_reminders`) |

---

## What Does NOT Change

- `LLMService`, `TransactionService`, `ReminderService` — untouched
- `categories.yaml`, parser, STT pipeline — untouched
- Existing morning/evening message format — insight is appended, not replacing anything

---

## Known Limitations

- `motivational_streak` uses `user.transactions_today` cached counter — if user deletes transactions it may still fire
- LLM tone is not configurable — consistent casual/friendly style
- No per-detector opt-out — all or nothing (acceptable for v1)

---

## Tests

### `backend/tests/test_insight_service.py`

| Test | Scenario |
|---|---|
| `test_category_spike_detected` | Current week food > 150% last week AND delta > 500 ₽ → fact returned |
| `test_category_spike_below_threshold` | Delta < 500 ₽ → no fact |
| `test_budget_milestone_7_days` | 7 consecutive days under daily limit → fact returned |
| `test_budget_milestone_no_budget_set` | `user.budget_amount is None` → detector returns None, no crash |
| `test_weekly_anomaly_detected` | This week > 130% average → fact returned |
| `test_weekly_anomaly_no_history` | No transactions in last month → returns None, no crash |
| `test_cooldown_skips_realtime` | `last_insight_at` = today (user tz) → `get_realtime_insight` returns None |
| `test_cooldown_skips_scheduled` | `last_insight_at` = today (user tz) → `get_scheduled_insight` also returns None |
| `test_llm_error_returns_none` | LLM raises `LLMUnavailableError` → returns None, no exception propagated |
| `test_motivational_streak_uses_cached_counter` | `user.transactions_today = 3` → fact returned (no DB query) |
| `test_no_transactions_returns_none` | User has zero transactions → all detectors return None, no crash |
