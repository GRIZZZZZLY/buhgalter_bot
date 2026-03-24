# Savings Goals ("Копилка") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-goal savings tracking with auto-deduction from income, LLM parsing, and deadline forecasting to the Telegram finance bot.

**Architecture:** Virtual piggy bank (doesn't affect budget) stored in `savings_goals` DB table. Auto-deduction hooks into `TransactionService.create_from_parse()` for income transactions. LLM parses free-form goal creation; deadline math is deterministic Python; LLM only formats natural language responses.

**Tech Stack:** SQLAlchemy + Alembic (model/migration), difflib (fuzzy match), python-telegram-bot (UX), Groq LLM via OpenAI SDK (parsing + advice), pytest (TDD)

**Spec:** `docs/superpowers/specs/2026-03-25-savings-goals-design.md`

---

## Iteration 1 — Backend Core

---

### Task 1: ORM Model + Alembic Migration

**Files:**
- Create: `backend/app/models/savings_goal.py`
- Create: `backend/alembic/versions/20260325_0007_create_savings_goals.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_savings_goal_service.py
from app.models.savings_goal import SavingsGoal

def test_savings_goal_model_exists() -> None:
    goal = SavingsGoal(
        user_id=555,
        title="iPhone 14 Pro",
        target_amount=120000,
    )
    assert goal.title == "iPhone 14 Pro"
    assert goal.current_amount == 0
    assert goal.is_active is True
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd backend && python -m pytest tests/test_savings_goal_service.py::test_savings_goal_model_exists -v
```
Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Create the model**

```python
# backend/app/models/savings_goal.py
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SavingsGoal(Base):
    __tablename__ = "savings_goals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    auto_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
```

- [ ] **Step 4: Create Alembic migration**

```python
# backend/alembic/versions/20260325_0007_create_savings_goals.py
"""create savings_goals table

Revision ID: 20260325_0007
Revises: <previous_revision>
Create Date: 2026-03-25
"""
from alembic import op
import sqlalchemy as sa

revision = "20260325_0007"
down_revision = None  # set to previous revision id
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "savings_goals",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False, index=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("target_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("current_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("deadline", sa.Date, nullable=True),
        sa.Column("auto_percent", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("savings_goals")
```

Note: replace `down_revision = None` with the actual latest revision id. Find it with:
```bash
cd backend && alembic heads
```

- [ ] **Step 5: Register model in alembic env**

In `backend/alembic/env.py`, add the import so Alembic detects it:
```python
from app.models.savings_goal import SavingsGoal  # noqa: F401
```

- [ ] **Step 6: Run test — expect PASS**

```bash
cd backend && python -m pytest tests/test_savings_goal_service.py::test_savings_goal_model_exists -v
```

- [ ] **Step 7: Apply migration**

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/savings_goal.py backend/alembic/versions/20260325_0007_create_savings_goals.py backend/alembic/env.py
git commit -m "feat: add SavingsGoal model and migration"
```

---

### Task 2: Repository (CRUD + fuzzy match)

**Files:**
- Create: `backend/app/repositories/savings_goal_repository.py`
- Modify: `backend/tests/test_savings_goal_service.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_savings_goal_service.py
# Add these tests (keep test_savings_goal_model_exists from Task 1)

from decimal import Decimal
import pytest
from app.repositories.savings_goal_repository import SavingsGoalRepository


def test_repository_create_and_list(db_session) -> None:
    repo = SavingsGoalRepository(db_session)
    goal = repo.create(user_id=555, title="iPhone 14 Pro", target_amount=Decimal("120000"))
    goals = repo.list_active(user_id=555)
    assert len(goals) == 1
    assert goals[0].title == "iPhone 14 Pro"
    assert goals[0].current_amount == Decimal("0")


def test_repository_fuzzy_match_exact(db_session) -> None:
    repo = SavingsGoalRepository(db_session)
    repo.create(user_id=555, title="Отпуск в Турции", target_amount=Decimal("80000"))
    goal, score = repo.fuzzy_match(user_id=555, query="отпуск")
    assert goal is not None
    assert score >= 0.8


def test_repository_fuzzy_match_no_goals(db_session) -> None:
    repo = SavingsGoalRepository(db_session)
    goal, score = repo.fuzzy_match(user_id=999, query="айфон")
    assert goal is None
    assert score == 0.0


def test_repository_complete_deactivates(db_session) -> None:
    repo = SavingsGoalRepository(db_session)
    goal = repo.create(user_id=555, title="Велосипед", target_amount=Decimal("30000"))
    repo.complete(goal)
    goals = repo.list_active(user_id=555)
    assert len(goals) == 0
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && python -m pytest tests/test_savings_goal_service.py -k "repository" -v
```

- [ ] **Step 3: Implement repository**

```python
# backend/app/repositories/savings_goal_repository.py
import difflib
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.savings_goal import SavingsGoal


class SavingsGoalRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        user_id: int,
        title: str,
        target_amount: Decimal,
        deadline=None,
        auto_percent: int | None = None,
    ) -> SavingsGoal:
        goal = SavingsGoal(
            user_id=user_id,
            title=title,
            target_amount=target_amount,
            current_amount=Decimal("0"),
            deadline=deadline,
            auto_percent=auto_percent,
            is_active=True,
        )
        self.db.add(goal)
        self.db.commit()
        self.db.refresh(goal)
        return goal

    def list_active(self, user_id: int) -> list[SavingsGoal]:
        stmt = (
            select(SavingsGoal)
            .where(SavingsGoal.user_id == user_id, SavingsGoal.is_active == True)  # noqa: E712
            .order_by(SavingsGoal.created_at)
        )
        return list(self.db.execute(stmt).scalars())

    def get(self, user_id: int, goal_id: str) -> SavingsGoal | None:
        stmt = select(SavingsGoal).where(
            SavingsGoal.id == goal_id, SavingsGoal.user_id == user_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def update_amount(self, goal: SavingsGoal, new_amount: Decimal) -> SavingsGoal:
        goal.current_amount = new_amount
        self.db.commit()
        return goal

    def update_auto_percent(self, goal: SavingsGoal, percent: int) -> SavingsGoal:
        goal.auto_percent = max(0, min(100, percent))
        self.db.commit()
        return goal

    def complete(self, goal: SavingsGoal) -> SavingsGoal:
        goal.is_active = False
        self.db.commit()
        return goal

    def fuzzy_match(self, user_id: int, query: str) -> tuple[SavingsGoal | None, float]:
        """Find best matching active goal by title. Returns (goal, confidence 0-1)."""
        goals = self.list_active(user_id)
        if not goals:
            return None, 0.0
        query_lower = query.lower()
        best_goal: SavingsGoal | None = None
        best_score = 0.0
        for goal in goals:
            title_lower = goal.title.lower()
            score = difflib.SequenceMatcher(None, query_lower, title_lower).ratio()
            if query_lower in title_lower:
                score = max(score, 0.85)
            if score > best_score:
                best_score = score
                best_goal = goal
        return best_goal, best_score
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd backend && python -m pytest tests/test_savings_goal_service.py -k "repository" -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/savings_goal_repository.py backend/tests/test_savings_goal_service.py
git commit -m "feat: add SavingsGoalRepository with fuzzy match"
```

---

### Task 3: SavingsGoalService — create, deposit, list

**Files:**
- Create: `backend/app/services/savings_goal_service.py`
- Modify: `backend/tests/test_savings_goal_service.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to backend/tests/test_savings_goal_service.py

from app.services.savings_goal_service import SavingsGoalService


def test_service_create_goal(db_session) -> None:
    service = SavingsGoalService(db_session)
    goal = service.create(
        user_id=555,
        title="MacBook Pro",
        target_amount=Decimal("200000"),
        auto_percent=15,
    )
    assert goal.title == "MacBook Pro"
    assert goal.auto_percent == 15
    assert goal.current_amount == Decimal("0")


def test_service_create_rejects_zero_amount(db_session) -> None:
    service = SavingsGoalService(db_session)
    with pytest.raises(ValueError, match="target_amount"):
        service.create(user_id=555, title="Тест", target_amount=Decimal("0"))


def test_service_deposit_increases_amount(db_session) -> None:
    service = SavingsGoalService(db_session)
    goal = service.create(user_id=555, title="Велосипед", target_amount=Decimal("30000"))
    updated, reached = service.deposit(user_id=555, goal_id=goal.id, amount=Decimal("5000"))
    assert updated.current_amount == Decimal("5000")
    assert reached is False


def test_service_deposit_returns_reached_when_complete(db_session) -> None:
    service = SavingsGoalService(db_session)
    goal = service.create(user_id=555, title="Велосипед", target_amount=Decimal("1000"))
    _, reached = service.deposit(user_id=555, goal_id=goal.id, amount=Decimal("1000"))
    assert reached is True


def test_service_list_active_returns_only_active(db_session) -> None:
    service = SavingsGoalService(db_session)
    g1 = service.create(user_id=555, title="Цель 1", target_amount=Decimal("10000"))
    g2 = service.create(user_id=555, title="Цель 2", target_amount=Decimal("20000"))
    service.complete(user_id=555, goal_id=g1.id)
    active = service.list_active(user_id=555)
    assert len(active) == 1
    assert active[0].id == g2.id
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && python -m pytest tests/test_savings_goal_service.py -k "service" -v
```

- [ ] **Step 3: Implement service (create/deposit/list)**

```python
# backend/app/services/savings_goal_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from math import ceil

from sqlalchemy.orm import Session

from app.models.savings_goal import SavingsGoal
from app.repositories.savings_goal_repository import SavingsGoalRepository
from app.repositories.transaction_repository import TransactionRepository


@dataclass
class GoalForecast:
    remaining: Decimal
    monthly_rate: Decimal | None      # None if no auto_percent
    months_to_goal: float | None      # None if can't calculate
    months_to_deadline: int | None    # None if no deadline
    on_track: bool | None             # None if no deadline
    suggested_percent: int | None     # only set when behind schedule


class SavingsGoalService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._repo = SavingsGoalRepository(db)

    def create(
        self,
        user_id: int,
        title: str,
        target_amount: Decimal,
        deadline: date | None = None,
        auto_percent: int | None = None,
    ) -> SavingsGoal:
        if target_amount <= 0:
            raise ValueError("target_amount must be > 0")
        if auto_percent is not None:
            auto_percent = max(0, min(100, auto_percent))
        return self._repo.create(
            user_id=user_id,
            title=title,
            target_amount=target_amount,
            deadline=deadline,
            auto_percent=auto_percent,
        )

    def deposit(
        self, user_id: int, goal_id: str, amount: Decimal
    ) -> tuple[SavingsGoal, bool]:
        """Add amount to goal. Returns (updated_goal, reached)."""
        goal = self._repo.get(user_id, goal_id)
        if goal is None or not goal.is_active:
            raise ValueError(f"Goal {goal_id} not found or inactive")
        new_amount = goal.current_amount + amount
        updated = self._repo.update_amount(goal, new_amount)
        reached = updated.current_amount >= updated.target_amount
        return updated, reached

    def list_active(self, user_id: int) -> list[SavingsGoal]:
        return self._repo.list_active(user_id)

    def complete(self, user_id: int, goal_id: str) -> SavingsGoal:
        goal = self._repo.get(user_id, goal_id)
        if goal is None:
            raise ValueError(f"Goal {goal_id} not found")
        return self._repo.complete(goal)

    def update_auto_percent(self, user_id: int, goal_id: str, percent: int) -> SavingsGoal:
        goal = self._repo.get(user_id, goal_id)
        if goal is None:
            raise ValueError(f"Goal {goal_id} not found")
        return self._repo.update_auto_percent(goal, percent)

    def fuzzy_find(self, user_id: int, query: str) -> tuple[SavingsGoal | None, float]:
        """Returns (goal, confidence). Confidence >= 0.8 is reliable."""
        return self._repo.fuzzy_match(user_id, query)

    def process_income(
        self, user_id: int, income_amount: Decimal
    ) -> list[tuple[SavingsGoal, Decimal, bool]]:
        """Auto-deduct from each active goal with auto_percent > 0.
        Returns list of (goal, deposited_amount, reached)."""
        results = []
        for goal in self._repo.list_active(user_id):
            if not goal.auto_percent:
                continue
            deposit_amount = (income_amount * goal.auto_percent / 100).quantize(Decimal("0.01"))
            if deposit_amount <= 0:
                continue
            updated, reached = self.deposit(user_id, goal.id, deposit_amount)
            results.append((updated, deposit_amount, reached))
        return results

    def calculate_forecast(self, goal: SavingsGoal, user_id: int) -> GoalForecast:
        """Deterministic forecast — no LLM."""
        remaining = max(Decimal("0"), goal.target_amount - goal.current_amount)

        # Monthly income from last month
        tx_repo = TransactionRepository(self.db)
        summary = tx_repo.get_summary(user_id, period="month")
        avg_income = Decimal(str(summary.get("income_total", 0)))

        monthly_rate: Decimal | None = None
        months_to_goal: float | None = None
        if goal.auto_percent and avg_income > 0:
            monthly_rate = (avg_income * goal.auto_percent / 100).quantize(Decimal("0.01"))
            if monthly_rate > 0:
                months_to_goal = float(remaining / monthly_rate)

        months_to_deadline: int | None = None
        on_track: bool | None = None
        suggested_percent: int | None = None

        if goal.deadline:
            today = date.today()
            delta = (goal.deadline - today).days
            months_to_deadline = max(0, ceil(delta / 30))

            if months_to_goal is not None and months_to_deadline > 0:
                on_track = months_to_goal <= months_to_deadline
                if not on_track and avg_income > 0 and months_to_deadline > 0:
                    needed_monthly = remaining / months_to_deadline
                    suggested_percent = ceil(float(needed_monthly / avg_income * 100)) + 1

        return GoalForecast(
            remaining=remaining,
            monthly_rate=monthly_rate,
            months_to_goal=months_to_goal,
            months_to_deadline=months_to_deadline,
            on_track=on_track,
            suggested_percent=suggested_percent,
        )
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd backend && python -m pytest tests/test_savings_goal_service.py -k "service" -v
```

- [ ] **Step 5: Add forecast test**

```python
# Append to backend/tests/test_savings_goal_service.py

def test_service_forecast_on_track(db_session) -> None:
    from datetime import date, timedelta
    from app.services.savings_goal_service import SavingsGoalService
    service = SavingsGoalService(db_session)
    # Goal: 12000₽, deadline 12 months, auto 10%
    # With 0 income in test DB → monthly_rate=None → on_track=None
    deadline = date.today().replace(day=1) + timedelta(days=365)
    goal = service.create(
        user_id=555, title="Тест", target_amount=Decimal("12000"),
        deadline=deadline, auto_percent=10,
    )
    forecast = service.calculate_forecast(goal, user_id=555)
    assert forecast.remaining == Decimal("12000")
    assert forecast.months_to_deadline is not None
    assert forecast.months_to_deadline > 0


def test_service_process_income_distributes(db_session) -> None:
    service = SavingsGoalService(db_session)
    service.create(user_id=555, title="Цель А", target_amount=Decimal("50000"), auto_percent=10)
    service.create(user_id=555, title="Цель Б", target_amount=Decimal("30000"), auto_percent=5)
    results = service.process_income(user_id=555, income_amount=Decimal("10000"))
    assert len(results) == 2
    deposited = {r[0].title: r[1] for r in results}
    assert deposited["Цель А"] == Decimal("1000.00")
    assert deposited["Цель Б"] == Decimal("500.00")
```

- [ ] **Step 6: Run all savings tests — expect PASS**

```bash
cd backend && python -m pytest tests/test_savings_goal_service.py -v
```

- [ ] **Step 7: Run full suite — expect all green**

```bash
cd backend && python -m pytest --tb=short -q
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/savings_goal_service.py backend/tests/test_savings_goal_service.py
git commit -m "feat: add SavingsGoalService with deposit, forecast, auto-deduction"
```

---

## Iteration 2 — Telegram UX + LLM

---

### Task 4: LLM parsing — extract_savings_goal

**Files:**
- Modify: `backend/app/services/llm_service.py`
- Modify: `backend/tests/test_savings_goal_service.py`

- [ ] **Step 1: Write failing test**

```python
# Append to backend/tests/test_savings_goal_service.py
from unittest.mock import MagicMock, patch
from app.services.llm_service import LLMService


def test_llm_extract_savings_goal(db_session) -> None:
    service = LLMService(db_session)
    fake_response = MagicMock()
    fake_response.choices[0].message.content = (
        '{"title": "iPhone 14 Pro", "target_amount": 120000, '
        '"deadline_iso": "2026-12-01", "auto_percent": 10}'
    )
    with patch.object(service._client.chat.completions, "create", return_value=fake_response):
        result = service.extract_savings_goal("хочу накопить на iPhone 120к к декабрю, 10%")
    assert result is not None
    assert result["title"] == "iPhone 14 Pro"
    assert result["target_amount"] == 120000
    assert result["auto_percent"] == 10


def test_llm_extract_savings_goal_missing_amount_returns_none_amount(db_session) -> None:
    service = LLMService(db_session)
    fake_response = MagicMock()
    fake_response.choices[0].message.content = (
        '{"title": "Отпуск", "target_amount": null, "deadline_iso": null, "auto_percent": null}'
    )
    with patch.object(service._client.chat.completions, "create", return_value=fake_response):
        result = service.extract_savings_goal("хочу накопить на отпуск")
    assert result is not None
    assert result["target_amount"] is None
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && python -m pytest tests/test_savings_goal_service.py -k "llm_extract_savings" -v
```

- [ ] **Step 3: Add method to LLMService**

In `backend/app/services/llm_service.py`, add after `extract_recurring()`:

```python
def extract_savings_goal(self, text: str) -> dict | None:
    """Extract savings goal fields from free-form text.

    Returns dict with keys: title, target_amount, deadline_iso, auto_percent
    target_amount may be None if not mentioned — caller must prompt user.
    """
    today = date.today().isoformat()
    system = (
        f"Ты ассистент для извлечения данных. Сегодня {today}.\n"
        "Извлеки параметры цели накопления из текста.\n"
        'Верни JSON: {"title": str, "target_amount": float | null, '
        '"deadline_iso": str | null, "auto_percent": int | null}\n'
        'title: название цели (вещь или событие).\n'
        'target_amount: сумма накопления, null если не указана.\n'
        'deadline_iso: дата ISO "YYYY-MM-DD", null если не упомянута.\n'
        'auto_percent: процент от дохода (0-100), null если не указан.\n'
        'Если тип не ясен — используй null.'
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
        logger.error("extract_savings_goal error: %s", exc)
        return None
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd backend && python -m pytest tests/test_savings_goal_service.py -k "llm_extract_savings" -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm_service.py backend/tests/test_savings_goal_service.py
git commit -m "feat: add LLMService.extract_savings_goal()"
```

---

### Task 5: Income hook in TransactionService

**Files:**
- Modify: `backend/app/services/transaction_service.py`
- Modify: `backend/tests/test_transaction_service.py`

- [ ] **Step 1: Write failing test**

```python
# Append to backend/tests/test_transaction_service.py

def test_income_triggers_savings_auto_deduction(db_session) -> None:
    """Creating an income transaction must auto-deposit into savings goals."""
    from decimal import Decimal
    from app.schemas.parser import ParseResult
    from app.services.savings_goal_service import SavingsGoalService
    from app.services.transaction_service import TransactionService

    # Create a savings goal with 10% auto-deduction
    goal_service = SavingsGoalService(db_session)
    goal = goal_service.create(
        user_id=555, title="Отпуск", target_amount=Decimal("50000"), auto_percent=10
    )

    tx_service = TransactionService(db_session)
    tx_service.create_from_parse(
        telegram_user_id=555,
        source="text",
        parsed=ParseResult(
            matched=True, confidence=0.95, confidence_label="high",
            transaction_type="income", amount=Decimal("30000"),
            category="salary", description=None, pattern="test", raw_input="зп 30000",
        ),
    )

    updated_goals = goal_service.list_active(user_id=555)
    assert updated_goals[0].current_amount == Decimal("3000.00")  # 10% of 30000
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd backend && python -m pytest tests/test_transaction_service.py::test_income_triggers_savings_auto_deduction -v
```

- [ ] **Step 3: Add income hook to TransactionService**

In `backend/app/services/transaction_service.py`, modify `create_from_parse()`:

```python
def create_from_parse(
    self,
    telegram_user_id: int,
    source: str,
    parsed: ParseResult,
    override_date: "date | None" = None,
) -> Transaction:
    payload = self.build_create_payload(telegram_user_id, source, parsed)
    if override_date is not None:
        payload["created_at"] = datetime.combine(override_date, datetime.min.time())
    tx = self.repo.create(payload)

    # Auto-deduct into savings goals on income
    if tx.type.value == "income":
        from app.services.savings_goal_service import SavingsGoalService
        SavingsGoalService(self.db).process_income(telegram_user_id, tx.amount)

    return tx
```

Note: use lazy import inside the method to avoid circular imports.

- [ ] **Step 4: Run test — expect PASS**

```bash
cd backend && python -m pytest tests/test_transaction_service.py::test_income_triggers_savings_auto_deduction -v
```

- [ ] **Step 5: Run full suite**

```bash
cd backend && python -m pytest --tb=short -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/transaction_service.py backend/tests/test_transaction_service.py
git commit -m "feat: auto-deduct savings goals on income transaction"
```

---

### Task 6: Telegram keyboards for savings

**Files:**
- Modify: `backend/app/telegram/keyboards.py`
- Modify: `backend/tests/test_telegram_runtime.py`

- [ ] **Step 1: Write failing tests**

```python
# Append to backend/tests/test_telegram_runtime.py

from app.telegram.keyboards import (
    goals_list_keyboard,
    goal_confirm_keyboard,
    goal_deposit_keyboard,
    goal_settings_keyboard,
)


def test_goals_list_keyboard_has_new_goal_and_menu() -> None:
    kb = goals_list_keyboard()
    callbacks = _all_callbacks(kb)
    assert "goals:new" in callbacks
    assert "nav:menu" in callbacks


def test_goal_confirm_keyboard_has_confirm_and_cancel() -> None:
    kb = goal_confirm_keyboard()
    callbacks = _all_callbacks(kb)
    assert "goals:confirm" in callbacks
    assert "goals:cancel" in callbacks


def test_goal_deposit_keyboard_has_deposit_and_back(db_session) -> None:
    kb = goal_deposit_keyboard("test-goal-id")
    callbacks = _all_callbacks(kb)
    assert "goals:deposit:test-goal-id" in callbacks
    assert "nav:goals" in callbacks


def test_goal_settings_keyboard_has_complete_and_back() -> None:
    kb = goal_settings_keyboard("test-goal-id")
    callbacks = _all_callbacks(kb)
    assert "goals:complete:test-goal-id" in callbacks
    assert "goals:nav:test-goal-id" in callbacks
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && python -m pytest tests/test_telegram_runtime.py -k "goal" -v
```

- [ ] **Step 3: Add keyboards**

In `backend/app/telegram/keyboards.py`, add after existing keyboard functions:

```python
def goals_list_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("🎯 Новая цель", "goals:new")],
        [_menu_btn()],
    ])


def goal_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("✅ Создать", "goals:confirm"), _btn("✏️ Изменить", "goals:edit")],
        [_btn("❌ Отмена", "goals:cancel")],
    ])


def goal_deposit_keyboard(goal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("💰 Пополнить", f"goals:deposit:{goal_id}")],
        [_btn("⚙️ Настроить", f"goals:settings:{goal_id}"), _btn("◀️ Назад", "nav:goals")],
    ])


def goal_settings_keyboard(goal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("✅ Завершить", f"goals:complete:{goal_id}")],
        [_btn("◀️ Назад", f"goals:nav:{goal_id}")],
    ])
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd backend && python -m pytest tests/test_telegram_runtime.py -k "goal" -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/telegram/keyboards.py backend/tests/test_telegram_runtime.py
git commit -m "feat: add savings goal keyboards"
```

---

### Task 7: handlers.py — deposit detection routing

**Files:**
- Modify: `backend/app/telegram/handlers.py`
- Modify: `backend/tests/test_telegram_bot_service.py`

- [ ] **Step 1: Write failing test**

```python
# Append to backend/tests/test_telegram_bot_service.py

def test_savings_deposit_text_routes_to_goal(db_session) -> None:
    """'Положил 3000 в копилку' must route to savings deposit, not transaction."""
    from app.services.savings_goal_service import SavingsGoalService
    from decimal import Decimal
    goal_service = SavingsGoalService(db_session)
    goal_service.create(user_id=555, title="Отпуск", target_amount=Decimal("50000"))

    service = TelegramBotService(db_session)
    response = service.process_text_message(
        telegram_user_id=555, text="положил в копилку 3000 на отпуск"
    )
    assert response["action"] in ("savings_deposited", "savings_clarify")
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd backend && python -m pytest tests/test_telegram_bot_service.py::test_savings_deposit_text_routes_to_goal -v
```

- [ ] **Step 3: Add deposit detection to handlers.py**

In `backend/app/telegram/handlers.py`:

Add import at top:
```python
from app.services.savings_goal_service import SavingsGoalService
```

Add static method to `TelegramTextFlow`:
```python
@staticmethod
def _looks_like_savings_deposit(text: str) -> bool:
    keywords = [
        "положил в копилку", "пополнил копилку", "пополнил цель",
        "отложил в копилку", "добавил в копилку", "в копилку",
        "на копилку", "накопил",
    ]
    t = text.lower()
    return any(kw in t for kw in keywords)
```

In `handle_text()`, add AFTER voice_edit check and BEFORE question check:

```python
# Savings deposit detection
if self._looks_like_savings_deposit(normalized_text):
    return self._handle_savings_deposit(telegram_user_id, normalized_text)
```

Add new method to `TelegramTextFlow`:
```python
def _handle_savings_deposit(self, telegram_user_id: int, text: str) -> dict[str, object]:
    amount = self.parser_service._extract_amount(text)
    if amount is None:
        return {"action": "savings_clarify", "message": "💰 Сколько кладём в копилку?"}

    goal, confidence = SavingsGoalService(self.db).fuzzy_find(telegram_user_id, text)
    if goal is None:
        return {"action": "savings_clarify", "message": "🎯 Укажи цель — на что копишь?"}

    if confidence < 0.8:
        return {
            "action": "savings_clarify",
            "message": f'🎯 Уточни: имеешь в виду "{goal.title}"?',
            "goal_id": goal.id,
            "amount": str(amount),
        }

    updated, reached = SavingsGoalService(self.db).deposit(
        user_id=telegram_user_id, goal_id=goal.id, amount=amount
    )
    progress = int(updated.current_amount / updated.target_amount * 100)
    msg = (
        f"💰 +{amount}₽ → {goal.title}\n"
        f"{'█' * (progress // 10)}{'░' * (10 - progress // 10)} {progress}%\n"
        f"Накоплено: {updated.current_amount}₽ из {updated.target_amount}₽"
    )
    if reached:
        msg += "\n\n🎉 Цель достигнута!"
    return {"action": "savings_deposited", "message": msg, "goal_id": goal.id}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd backend && python -m pytest tests/test_telegram_bot_service.py::test_savings_deposit_text_routes_to_goal -v
```

- [ ] **Step 5: Run full suite**

```bash
cd backend && python -m pytest --tb=short -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/telegram/handlers.py backend/tests/test_telegram_bot_service.py
git commit -m "feat: route savings deposit text to SavingsGoalService"
```

---

### Task 8: runtime.py — /goals and /goal commands

**Files:**
- Modify: `backend/app/telegram/runtime.py`

- [ ] **Step 1: Add imports to runtime.py**

At the top of `backend/app/telegram/runtime.py`, add:
```python
from app.services.savings_goal_service import SavingsGoalService
from app.telegram.keyboards import (
    # existing imports...
    goals_list_keyboard,
    goal_confirm_keyboard,
    goal_deposit_keyboard,
    goal_settings_keyboard,
)
```

- [ ] **Step 2: Add /goals command handler**

Add after `ask_command`:

```python
async def goals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all active savings goals with progress bars."""
    with SessionLocal() as db:
        _ensure_user(db, update)
        service = SavingsGoalService(db)
        goals = service.list_active(update.effective_user.id)

    if not goals:
        await update.effective_message.reply_text(
            "🎯 У тебя пока нет целей накопления.\n"
            "Напиши /goal чтобы создать первую!",
            reply_markup=goals_list_keyboard(),
        )
        return

    lines = []
    for goal in goals:
        pct = min(100, int(goal.current_amount / goal.target_amount * 100))
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        deadline_str = f" • До: {goal.deadline.strftime('%d.%m.%Y')}" if goal.deadline else ""
        auto_str = f" • Авто: {goal.auto_percent}%" if goal.auto_percent else ""
        lines.append(
            f"🎯 *{goal.title}*\n"
            f"{bar} {pct}% ({goal.current_amount}₽ / {goal.target_amount}₽)"
            f"{deadline_str}{auto_str}"
        )

    text = "\n\n".join(lines)
    await update.effective_message.reply_text(
        text, parse_mode="Markdown", reply_markup=goals_list_keyboard()
    )


async def goal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a new savings goal from free-form text or start interactive dialog."""
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.effective_message.reply_text(
            "🎯 Напиши что хочешь накопить, например:\n"
            "/goal iPhone 14 Pro 120к к декабрю, откладывать 10%"
        )
        return

    await update.effective_message.reply_text("🤔 Разбираю…")
    with SessionLocal() as db:
        _ensure_user(db, update)
        from app.services.llm_service import LLMService
        result = LLMService(db).extract_savings_goal(text)

    if result is None:
        await update.effective_message.reply_text(
            "Не смог разобрать. Попробуй: /goal iPhone 120000 к декабрю"
        )
        return

    if not result.get("target_amount"):
        context.user_data["pending_goal"] = result
        context.user_data["mode"] = "goal_amount_input"
        await update.effective_message.reply_text(
            f"🎯 {result.get('title', 'Новая цель')}\nСколько нужно накопить (₽)?"
        )
        return

    await _confirm_goal_creation(update, context, result)


async def _confirm_goal_creation(update, context, parsed: dict) -> None:
    from decimal import Decimal
    title = parsed.get("title", "Новая цель")
    amount = parsed.get("target_amount")
    deadline = parsed.get("deadline_iso", "не задан")
    auto = parsed.get("auto_percent")

    msg = (
        f"🎯 *{title}*\n"
        f"Цель: {amount}₽\n"
        f"Дедлайн: {deadline}\n"
        f"Авто: {f'{auto}% от каждого дохода' if auto else 'не задан'}"
    )
    context.user_data["pending_goal"] = parsed
    await update.effective_message.reply_text(
        msg, parse_mode="Markdown", reply_markup=goal_confirm_keyboard()
    )
```

- [ ] **Step 3: Add goals callback handler**

```python
async def goals_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data  # e.g. "goals:confirm", "goals:deposit:uuid"

    if data == "goals:confirm":
        parsed = context.user_data.pop("pending_goal", None)
        if not parsed:
            await query.edit_message_text("Сессия истекла. Попробуй снова /goal")
            return
        from decimal import Decimal
        from datetime import date as _date
        with SessionLocal() as db:
            _ensure_user(db, update)
            service = SavingsGoalService(db)
            deadline = None
            if parsed.get("deadline_iso"):
                try:
                    deadline = _date.fromisoformat(parsed["deadline_iso"])
                except ValueError:
                    pass
            goal = service.create(
                user_id=query.from_user.id,
                title=parsed["title"],
                target_amount=Decimal(str(parsed["target_amount"])),
                deadline=deadline,
                auto_percent=parsed.get("auto_percent"),
            )
        await query.edit_message_text(f"✅ Цель создана: {goal.title} — {goal.target_amount}₽")

    elif data == "goals:cancel":
        context.user_data.pop("pending_goal", None)
        await query.edit_message_text("Отменено.")

    elif data.startswith("goals:complete:"):
        goal_id = data.split(":", 2)[2]
        with SessionLocal() as db:
            SavingsGoalService(db).complete(query.from_user.id, goal_id)
        await query.edit_message_text("✅ Цель завершена! Поздравляем!")

    elif data.startswith("goals:deposit:"):
        goal_id = data.split(":", 2)[2]
        context.user_data["pending_deposit_goal_id"] = goal_id
        context.user_data["mode"] = "goal_deposit_input"
        await query.edit_message_text("💰 Сколько кладём в копилку (₽)?")
```

- [ ] **Step 4: Handle mode in text_message_handler**

In the existing text message handler in `runtime.py`, find the mode-dispatch section and add:

```python
elif mode == "goal_amount_input":
    # User is providing target amount for pending goal
    context.user_data.pop("mode", None)
    from app.services.parser_service import ParserService
    amount = ParserService._extract_amount(text)
    if amount is None:
        await update.effective_message.reply_text("Введи сумму числом, например: 120000")
        return
    pending = context.user_data.get("pending_goal", {})
    pending["target_amount"] = float(amount)
    await _confirm_goal_creation(update, context, pending)
    return

elif mode == "goal_deposit_input":
    context.user_data.pop("mode", None)
    goal_id = context.user_data.pop("pending_deposit_goal_id", None)
    from app.services.parser_service import ParserService
    from decimal import Decimal
    amount = ParserService._extract_amount(text)
    if amount is None or goal_id is None:
        await update.effective_message.reply_text("Введи сумму числом.")
        return
    with SessionLocal() as db:
        updated, reached = SavingsGoalService(db).deposit(
            update.effective_user.id, goal_id, amount
        )
    pct = min(100, int(updated.current_amount / updated.target_amount * 100))
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    msg = f"💰 +{amount}₽ → {updated.title}\n{bar} {pct}%"
    if reached:
        msg += "\n\n🎉 Цель достигнута!"
    await update.effective_message.reply_text(msg)
    return
```

- [ ] **Step 5: Register handlers**

In `create_application()`, add:
```python
application.add_handler(CommandHandler("goals", goals_command))
application.add_handler(CommandHandler("goal", goal_command))
application.add_handler(CallbackQueryHandler(goals_callback_handler, pattern=r"^goals:"))
```

- [ ] **Step 6: Run full suite**

```bash
cd backend && python -m pytest --tb=short -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/telegram/runtime.py
git commit -m "feat: add /goals and /goal Telegram commands with inline UX"
```

---

## Final Verification

- [ ] Run complete test suite — all green:
```bash
cd backend && python -m pytest --tb=short -q
```

- [ ] Manual smoke test (with running bot):
  1. `/goal iPhone 120к к декабрю, 10%` → карточка подтверждения
  2. Нажать ✅ Создать → цель создана
  3. `/goals` → список с прогресс-баром
  4. Записать доход 30000 → цель автопополняется на 3000₽
  5. "положил в копилку 5000 на айфон" → пополнение через fuzzy match
  6. "когда накоплю на iPhone?" → FinancialQAService отвечает с реальными данными

- [ ] Final commit:
```bash
git add -A
git commit -m "feat: complete savings goals feature (копилка)"
```
