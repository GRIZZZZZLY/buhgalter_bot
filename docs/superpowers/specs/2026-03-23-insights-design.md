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
        """Called from scheduler (morning/evening). No cooldown check."""
```

### `InsightFact` dataclass

```python
@dataclass
class InsightFact:
    type: str    # "category_spike" | "budget_milestone" | "weekly_anomaly" | "category_record" | "motivational_streak"
    data: dict   # detector-specific payload, passed as-is to LLM
```

---

## Detectors

Five detectors run in priority order. First match wins.

| Priority | Name | Trigger condition |
|---|---|---|
| 1 | `category_spike` | A category this week > 150% of last week AND delta > 500 ₽ |
| 2 | `budget_milestone` | User has N consecutive days within budget (thresholds: 7, 14, 30) |
| 3 | `weekly_anomaly` | Total spend this week > 130% of average weekly spend over last month |
| 4 | `category_record` | A category this month > 140% of same category last month |
| 5 | `motivational_streak` | 3rd or more transaction saved today |

Detectors are private methods of `InsightService`. Each returns `InsightFact | None`.

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

### Cooldown (real-time only)

- New column `last_insight_at: DateTime | None` on `users` table (Alembic migration)
- Before running detectors: if `last_insight_at.date() == today` (user's timezone) → return `None`
- After successful send: `user.last_insight_at = datetime.now(tz)`
- Scheduled insights (morning/evening) do not check cooldown — they fire at most once per day by the scheduler's own logic

### Delivery

| Context | How delivered |
|---|---|
| After transaction save (`runtime.py`) | Separate message immediately after save confirmation |
| Morning briefing | Appended as extra paragraph at end of existing message |
| Evening check-in | Appended as extra paragraph at end of existing message |

If the morning/evening message has no content (no transactions to report), the insight is also skipped — it lives inside existing messages, not as standalone noise.

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
In `_check_morning_reminders` and `_check_evening_reminders`, after building the main message:
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
| `backend/app/services/scheduler_service.py` | Modify — call `get_scheduled_insight` in morning/evening jobs |

---

## What Does NOT Change

- `LLMService`, `TransactionService`, `ReminderService` — untouched
- `categories.yaml`, parser, STT pipeline — untouched
- Existing morning/evening message format — insight is appended, not replacing anything

---

## Known Limitations

- `motivational_streak` detector counts all transactions for today — if user deletes transactions it may still fire
- LLM tone is not configurable — consistent casual/friendly style
- No per-detector opt-out — all or nothing (acceptable for v1)

---

## Tests

### `backend/tests/test_insight_service.py`

| Test | Scenario |
|---|---|
| `test_category_spike_detected` | Current week food > 150% last week → fact returned |
| `test_category_spike_below_threshold` | Delta < 500 ₽ → no fact |
| `test_budget_milestone_7_days` | 7 consecutive days in budget → fact returned |
| `test_weekly_anomaly_detected` | This week > 130% average → fact returned |
| `test_cooldown_skips_realtime` | `last_insight_at` = today → `get_realtime_insight` returns None |
| `test_no_cooldown_for_scheduled` | `last_insight_at` = today → `get_scheduled_insight` still returns insight |
| `test_llm_error_returns_none` | LLM raises → returns None, no exception |
| `test_motivational_streak_third_tx` | 3rd transaction today → fact returned |
