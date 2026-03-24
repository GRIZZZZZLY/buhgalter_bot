# Categories Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a «Категории» section to the Telegram bot where users can view all categories, add custom ones, and rename/change emoji on any (system or custom), with safe deletion of custom categories.

**Architecture:** New `user_categories` table stores per-user category definitions (seeded from `categories.yaml` on first open). `CategoryService` handles business logic. A new `categories_callback_handler` in `runtime.py` handles all UI interactions following the existing `edit_callback_handler` pattern.

**Tech Stack:** SQLAlchemy mapped columns, Alembic manual migration, python-telegram-bot `CallbackQueryHandler`, `context.user_data` for multi-step input state.

**Spec:** `docs/superpowers/specs/2026-03-24-categories-design.md`

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/app/models/user_category.py` | ORM model |
| Create | `backend/alembic/versions/20260324_0008_create_user_categories.py` | Migration |
| Create | `backend/app/repositories/user_category_repository.py` | CRUD + seeding |
| Create | `backend/app/services/category_service.py` | Business logic |
| Modify | `backend/tests/conftest.py` | Import new model |
| Create | `backend/tests/test_category_service.py` | Service tests |
| Modify | `backend/app/telegram/keyboards.py` | 4 new keyboard functions + menu button |
| Modify | `backend/app/services/nav_service.py` | `categories_screen` method |
| Modify | `backend/app/telegram/runtime.py` | New callback handler + `awaiting_*` blocks + registration |

---

## Phase 1 — Backend (data layer)

### Task 1: UserCategory model

**Files:**
- Create: `backend/app/models/user_category.py`

- [ ] **Step 1: Create the model file**

```python
# backend/app/models/user_category.py
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserCategory(Base):
    __tablename__ = "user_categories"
    __table_args__ = (
        UniqueConstraint("telegram_user_id", "slug", name="uq_user_category_slug"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(50), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(100), nullable=False)
    emoji: Mapped[str] = mapped_column(String(10), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # expense / income / both
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

- [ ] **Step 2: Commit**

```bash
cd backend && git add app/models/user_category.py
git commit -m "feat(categories): add UserCategory ORM model"
```

---

### Task 2: Alembic migration

**Files:**
- Create: `backend/alembic/versions/20260324_0008_create_user_categories.py`

- [ ] **Step 1: Create migration file**

```python
# backend/alembic/versions/20260324_0008_create_user_categories.py
"""create user_categories table

Revision ID: 20260324_0008
Revises: 20260316_0007
Create Date: 2026-03-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260324_0008"
down_revision = "20260316_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("name_ru", sa.String(length=100), nullable=False),
        sa.Column("emoji", sa.String(length=10), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id", "slug", name="uq_user_category_slug"),
    )
    op.create_index(
        op.f("ix_user_categories_telegram_user_id"),
        "user_categories",
        ["telegram_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_user_categories_telegram_user_id"),
        table_name="user_categories",
    )
    op.drop_table("user_categories")
```

- [ ] **Step 2: Run migration and verify**

```bash
cd backend && alembic upgrade head
```
Expected: `Running upgrade 20260316_0007 -> 20260324_0008, create user_categories table`

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/20260324_0008_create_user_categories.py
git commit -m "feat(categories): add user_categories migration"
```

---

### Task 3: UserCategoryRepository

**Files:**
- Create: `backend/app/repositories/user_category_repository.py`

- [ ] **Step 1: Create repository**

```python
# backend/app/repositories/user_category_repository.py
from __future__ import annotations

import yaml
from pathlib import Path
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.user_category import UserCategory

# System category seed data: slug -> (name_ru, emoji, type)
# emoji matches keyboards.CATEGORY_EMOJI, name_ru matches formatter.CATEGORY_LABELS_RU
_SYSTEM_CATEGORIES: list[dict] = [
    {"slug": "food",          "name_ru": "Еда",          "emoji": "🍕", "type": "expense"},
    {"slug": "transport",     "name_ru": "Транспорт",    "emoji": "🚗", "type": "expense"},
    {"slug": "housing",       "name_ru": "Жильё",        "emoji": "🏠", "type": "expense"},
    {"slug": "telecom",       "name_ru": "Связь",        "emoji": "📱", "type": "expense"},
    {"slug": "entertainment", "name_ru": "Развлечения",  "emoji": "🎮", "type": "expense"},
    {"slug": "subscriptions", "name_ru": "Подписки",     "emoji": "📺", "type": "expense"},
    {"slug": "health",        "name_ru": "Здоровье",     "emoji": "💊", "type": "expense"},
    {"slug": "beauty",        "name_ru": "Красота",      "emoji": "💅", "type": "expense"},
    {"slug": "shopping",      "name_ru": "Покупки",      "emoji": "🛍", "type": "expense"},
    {"slug": "home",          "name_ru": "Дом",          "emoji": "🏡", "type": "expense"},
    {"slug": "work",          "name_ru": "Работа",       "emoji": "💼", "type": "expense"},
    {"slug": "education",     "name_ru": "Обучение",     "emoji": "📚", "type": "expense"},
    {"slug": "gifts",         "name_ru": "Подарки",      "emoji": "🎁", "type": "expense"},
    {"slug": "fees",          "name_ru": "Комиссии",     "emoji": "🏦", "type": "expense"},
    {"slug": "salary",        "name_ru": "Зарплата",     "emoji": "💰", "type": "income"},
    {"slug": "freelance",     "name_ru": "Фриланс",      "emoji": "🧑‍💻", "type": "income"},
    {"slug": "bonus",         "name_ru": "Премии",       "emoji": "🏆", "type": "income"},
    {"slug": "transfer",      "name_ru": "Переводы",     "emoji": "↔️", "type": "income"},
    {"slug": "refund",        "name_ru": "Возвраты",     "emoji": "↩️", "type": "income"},
    {"slug": "other",         "name_ru": "Прочее",       "emoji": "📦", "type": "both"},
]


class UserCategoryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_all(self, telegram_user_id: int) -> list[UserCategory]:
        stmt = (
            select(UserCategory)
            .where(UserCategory.telegram_user_id == telegram_user_id)
            .order_by(UserCategory.sort_order)
        )
        return list(self.db.scalars(stmt).all())

    def get_by_slug(self, telegram_user_id: int, slug: str) -> UserCategory | None:
        stmt = select(UserCategory).where(
            UserCategory.telegram_user_id == telegram_user_id,
            UserCategory.slug == slug,
        )
        return self.db.scalar(stmt)

    def create(
        self,
        telegram_user_id: int,
        slug: str,
        name_ru: str,
        emoji: str,
        cat_type: str,
        is_custom: bool = True,
        sort_order: int | None = None,
    ) -> UserCategory:
        if sort_order is None:
            max_order_stmt = select(func.max(UserCategory.sort_order)).where(
                UserCategory.telegram_user_id == telegram_user_id
            )
            max_order = self.db.scalar(max_order_stmt) or 0
            sort_order = max_order + 1
        cat = UserCategory(
            telegram_user_id=telegram_user_id,
            slug=slug,
            name_ru=name_ru,
            emoji=emoji,
            type=cat_type,
            is_custom=is_custom,
            sort_order=sort_order,
        )
        self.db.add(cat)
        self.db.flush()
        return cat

    def update(self, category_id: int, **kwargs) -> UserCategory | None:
        stmt = select(UserCategory).where(UserCategory.id == category_id)
        cat = self.db.scalar(stmt)
        if cat is None:
            return None
        for key, value in kwargs.items():
            setattr(cat, key, value)
        self.db.flush()
        return cat

    def delete(self, category_id: int) -> None:
        stmt = select(UserCategory).where(UserCategory.id == category_id)
        cat = self.db.scalar(stmt)
        if cat:
            self.db.delete(cat)
            self.db.flush()

    def seed_system_categories(self, telegram_user_id: int) -> None:
        """Idempotent: inserts system categories using ON CONFLICT DO NOTHING."""
        for i, entry in enumerate(_SYSTEM_CATEGORIES):
            self.db.execute(
                text(
                    "INSERT INTO user_categories "
                    "(telegram_user_id, slug, name_ru, emoji, type, is_custom, sort_order, "
                    " created_at, updated_at) "
                    "VALUES (:uid, :slug, :name, :emoji, :type, 0, :order, "
                    " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) "
                    "ON CONFLICT (telegram_user_id, slug) DO NOTHING"
                ),
                {
                    "uid": telegram_user_id,
                    "slug": entry["slug"],
                    "name": entry["name_ru"],
                    "emoji": entry["emoji"],
                    "type": entry["type"],
                    "order": i,
                },
            )
        self.db.flush()
```

- [ ] **Step 2: Commit**

```bash
git add app/repositories/user_category_repository.py
git commit -m "feat(categories): add UserCategoryRepository with race-safe seeding"
```

---

### Task 4: CategoryService

**Files:**
- Create: `backend/app/services/category_service.py`

- [ ] **Step 1: Create service**

```python
# backend/app/services/category_service.py
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.user_category_mapping import UserCategoryMapping
from app.repositories.user_category_repository import UserCategoryRepository

_TRANSLIT: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    " ": "_",
}


def _to_slug(name: str) -> str:
    """Transliterate Russian name to ASCII slug [a-z0-9_], max 50 chars."""
    result = name.lower()
    out = []
    for ch in result:
        out.append(_TRANSLIT.get(ch, ch))
    slug = "".join(out)
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    return slug[:50] or "custom"


def _is_emoji(text: str) -> bool:
    """Return True if text contains at least one emoji character."""
    for ch in text:
        cat = unicodedata.category(ch)
        cp = ord(ch)
        if cat in ("So", "Sm") or 0x1F300 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x26FF:
            return True
    return False


class CategoryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._repo = UserCategoryRepository(db)

    def ensure_seeded(self, telegram_user_id: int) -> None:
        """Seed system categories if not yet done (idempotent)."""
        self._repo.seed_system_categories(telegram_user_id)
        self.db.commit()

    def list_categories(self, telegram_user_id: int) -> dict[str, list]:
        """Return categories grouped by type: {'expense': [...], 'income': [...], 'both': [...]}."""
        all_cats = self._repo.get_all(telegram_user_id)
        groups: dict[str, list] = {"expense": [], "income": [], "both": []}
        for cat in all_cats:
            groups.setdefault(cat.type, []).append(cat)
        return groups

    def add_custom(
        self,
        telegram_user_id: int,
        name_ru: str,
        emoji: str,
        cat_type: str,
    ) -> "UserCategory":
        """Create a custom category. Raises ValueError on invalid emoji or type."""
        if not _is_emoji(emoji):
            raise ValueError(f"Не похоже на emoji: {emoji!r}")
        if cat_type not in ("expense", "income", "both"):
            raise ValueError(f"Неизвестный тип: {cat_type!r}")
        slug = _to_slug(name_ru)
        base = slug
        counter = 2
        while self._repo.get_by_slug(telegram_user_id, slug) is not None:
            slug = f"{base}_{counter}"[:50]
            counter += 1
        cat = self._repo.create(
            telegram_user_id=telegram_user_id,
            slug=slug,
            name_ru=name_ru,
            emoji=emoji,
            cat_type=cat_type,
            is_custom=True,
        )
        self.db.commit()
        return cat

    def rename(self, telegram_user_id: int, slug: str, new_name: str) -> "UserCategory | None":
        cat = self._repo.get_by_slug(telegram_user_id, slug)
        if cat is None:
            return None
        updated = self._repo.update(cat.id, name_ru=new_name)
        self.db.commit()
        return updated

    def change_emoji(self, telegram_user_id: int, slug: str, new_emoji: str) -> "UserCategory | None":
        if not _is_emoji(new_emoji):
            raise ValueError(f"Не похоже на emoji: {new_emoji!r}")
        cat = self._repo.get_by_slug(telegram_user_id, slug)
        if cat is None:
            return None
        updated = self._repo.update(cat.id, emoji=new_emoji)
        self.db.commit()
        return updated

    def count_transactions(self, telegram_user_id: int, slug: str) -> int:
        from sqlalchemy import func, select
        stmt = select(func.count()).where(
            Transaction.telegram_user_id == telegram_user_id,
            Transaction.category == slug,
        )
        return self.db.scalar(stmt) or 0

    def delete_custom(
        self,
        telegram_user_id: int,
        slug: str,
        reassign_to_slug: str,
    ) -> None:
        """Reassign transactions and mappings, then delete the custom category."""
        cat = self._repo.get_by_slug(telegram_user_id, slug)
        if cat is None or not cat.is_custom:
            raise ValueError("Категория не найдена или не является кастомной.")
        # Reassign transactions
        self.db.execute(
            sa_update(Transaction)
            .where(
                Transaction.telegram_user_id == telegram_user_id,
                Transaction.category == slug,
            )
            .values(category=reassign_to_slug)
        )
        # Reassign user_category_mappings
        self.db.execute(
            sa_update(UserCategoryMapping)
            .where(
                UserCategoryMapping.telegram_user_id == telegram_user_id,
                UserCategoryMapping.category == slug,
            )
            .values(category=reassign_to_slug)
        )
        self._repo.delete(cat.id)
        self.db.commit()
```

- [ ] **Step 2: Commit**

```bash
git add app/services/category_service.py
git commit -m "feat(categories): add CategoryService with CRUD and safe deletion"
```

---

### Task 5: Update conftest + write tests

**Files:**
- Modify: `backend/tests/conftest.py` (add model import)
- Create: `backend/tests/test_category_service.py`

- [ ] **Step 1: Add import to conftest.py**

In `backend/tests/conftest.py` add after the last `# noqa: F401` import:
```python
from app.models.user_category import UserCategory  # noqa: F401
```

- [ ] **Step 2: Write failing tests**

```python
# backend/tests/test_category_service.py
import pytest
from app.services.category_service import CategoryService, _to_slug, _is_emoji

TG_USER = 999


# --- Unit: _to_slug ---

def test_to_slug_russian():
    assert _to_slug("Спорт") == "sport"

def test_to_slug_spaces_become_underscores():
    assert _to_slug("Бытовая химия") == "bytovaya_khimiya"

def test_to_slug_strips_special_chars():
    assert _to_slug("Café!") == "caf"

def test_to_slug_max_50():
    assert len(_to_slug("а" * 100)) <= 50


# --- Unit: _is_emoji ---

def test_is_emoji_true():
    assert _is_emoji("🏋") is True

def test_is_emoji_false_plain_text():
    assert _is_emoji("abc") is False

def test_is_emoji_bullet():
    # The bullet "•" used for "other" is not an emoji — this is acceptable
    assert _is_emoji("•") is False


# --- Service: ensure_seeded ---

def test_ensure_seeded_idempotent(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    svc.ensure_seeded(TG_USER)  # second call must not raise or duplicate
    groups = svc.list_categories(TG_USER)
    food_list = [c for c in groups["expense"] if c.slug == "food"]
    assert len(food_list) == 1


def test_ensure_seeded_creates_system_categories(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    groups = svc.list_categories(TG_USER)
    slugs = {c.slug for cats in groups.values() for c in cats}
    assert "food" in slugs
    assert "salary" in slugs
    assert "other" in slugs


# --- Service: add_custom ---

def test_add_custom_creates_category(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    cat = svc.add_custom(TG_USER, "Спорт", "🏋", "expense")
    assert cat.slug == "sport"
    assert cat.is_custom is True
    assert cat.type == "expense"


def test_add_custom_slug_collision_gets_suffix(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    svc.add_custom(TG_USER, "Спорт", "🏋", "expense")
    cat2 = svc.add_custom(TG_USER, "Спорт", "⚽", "expense")
    assert cat2.slug == "sport_2"


def test_add_custom_invalid_emoji_raises(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    with pytest.raises(ValueError, match="emoji"):
        svc.add_custom(TG_USER, "Спорт", "abc", "expense")


def test_add_custom_invalid_type_raises(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    with pytest.raises(ValueError, match="тип"):
        svc.add_custom(TG_USER, "Спорт", "🏋", "unknown")


# --- Service: rename ---

def test_rename_system_category(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    cat = svc.rename(TG_USER, "food", "Питание")
    assert cat is not None
    assert cat.name_ru == "Питание"
    assert cat.slug == "food"  # slug unchanged


def test_rename_nonexistent_returns_none(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    result = svc.rename(TG_USER, "nonexistent", "Что-то")
    assert result is None


# --- Service: change_emoji ---

def test_change_emoji_success(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    cat = svc.change_emoji(TG_USER, "food", "🥗")
    assert cat is not None
    assert cat.emoji == "🥗"


def test_change_emoji_invalid_raises(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    with pytest.raises(ValueError):
        svc.change_emoji(TG_USER, "food", "xyz")


# --- Service: count_transactions ---

def test_count_transactions_zero(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    assert svc.count_transactions(TG_USER, "food") == 0


# --- Service: delete_custom ---

def test_delete_custom_no_transactions(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    cat = svc.add_custom(TG_USER, "Спорт", "🏋", "expense")
    svc.delete_custom(TG_USER, cat.slug, "other")
    assert svc._repo.get_by_slug(TG_USER, cat.slug) is None


def test_delete_system_category_raises(db_session):
    svc = CategoryService(db_session)
    svc.ensure_seeded(TG_USER)
    with pytest.raises(ValueError):
        svc.delete_custom(TG_USER, "food", "other")
```

- [ ] **Step 3: Run tests — expect failures first**

```bash
cd backend && pytest tests/test_category_service.py -v 2>&1 | head -40
```
Expected: FAILED (ImportError or similar — model not registered)

- [ ] **Step 4: Run tests after implementation**

```bash
cd backend && pytest tests/test_category_service.py -v
```
Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_category_service.py
git commit -m "test(categories): add CategoryService tests"
```

---

## Phase 2 — Telegram UI

### Task 6: New keyboard functions

**Files:**
- Modify: `backend/app/telegram/keyboards.py`

- [ ] **Step 1: Add MENU_BTN_CATEGORIES constant and update main_menu_inline_keyboard**

In `keyboards.py`, after `MENU_BTN_HELP`:
```python
MENU_BTN_CATEGORIES = "🗂 Категории"
```

Update `main_menu_inline_keyboard()`:
```python
def main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("📊 Сводка", "nav:stats")],
        [_btn(MENU_BTN_PLANNED, "nav:planned"), _btn(MENU_BTN_RECURRING, "nav:recurring")],
        [_btn(MENU_BTN_BUDGETS, "nav:budgets"), _btn(MENU_BTN_CATEGORIES, "nav:categories")],
        [_btn(MENU_BTN_SETTINGS, "nav:settings"), _btn(MENU_BTN_HELP, "nav:help")],
    ])
```

- [ ] **Step 2: Add categories keyboard functions**

Add after `recurring_inline_keyboard`:

```python
def categories_nav_keyboard(categories_by_type: dict) -> InlineKeyboardMarkup:
    """Per-category row: emoji+name button (noop) + ✏️ + optional 🗑."""
    rows: list[list[InlineKeyboardButton]] = []
    for group_type in ("expense", "income", "both"):
        for cat in categories_by_type.get(group_type, []):
            row = [
                _btn(f"{cat.emoji} {cat.name_ru}", f"categories:noop:{cat.slug}"),
                _btn("✏️", f"categories:edit:{cat.slug}"),
            ]
            if cat.is_custom:
                row.append(_btn("🗑", f"categories:delete:{cat.slug}"))
            rows.append(row)
    rows.append([_btn("➕ Добавить", "categories:add"), _back_btn()])
    return InlineKeyboardMarkup(rows)


def category_edit_keyboard(slug: str, is_custom: bool) -> InlineKeyboardMarkup:
    rows = [
        [_btn("✏️ Изменить название", f"categories:rename:{slug}")],
        [_btn("🎨 Изменить emoji", f"categories:emoji:{slug}")],
    ]
    if is_custom:
        rows.append([_btn("🗑 Удалить", f"categories:delete:{slug}")])
    rows.append([_back_btn("nav:categories")])
    return InlineKeyboardMarkup(rows)


def category_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("💸 Расход", "categories:set_type:expense"),
            _btn("💰 Доход", "categories:set_type:income"),
            _btn("↔️ Оба", "categories:set_type:both"),
        ],
        [_back_btn("nav:categories")],
    ])


def category_reassign_keyboard(categories: list, deleting_slug: str) -> InlineKeyboardMarkup:
    """List of same-type categories to reassign transactions to before deletion."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for cat in categories:
        if cat.slug == deleting_slug:
            continue
        btn = _btn(
            f"{cat.emoji} {cat.name_ru}",
            f"categories:reassign:{deleting_slug}__{cat.slug}",
        )
        row.append(btn)
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([_btn("❌ Отмена", "nav:categories")])
    return InlineKeyboardMarkup(rows)


def category_delete_confirm_keyboard(slug: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("✅ Да, удалить", f"categories:confirm_delete:{slug}"),
            _btn("Отмена", "nav:categories"),
        ]
    ])
```

- [ ] **Step 3: Update test_telegram_formatter_style.py snapshot**

Open `backend/tests/test_telegram_formatter_style.py` and find any assertion that checks `main_menu_inline_keyboard()` layout (button count or text). Update it to reflect the new menu layout with `🗂 Категории`. Run:

```bash
cd backend && pytest tests/test_telegram_formatter_style.py -v
```
Expected: all PASSED

- [ ] **Step 4: Commit**

```bash
git add app/telegram/keyboards.py tests/test_telegram_formatter_style.py
git commit -m "feat(categories): add categories keyboard functions"
```

---

### Task 7: NavService — categories_screen

**Files:**
- Modify: `backend/app/services/nav_service.py`

- [ ] **Step 1: Add import and method**

Add to imports at top of `nav_service.py`:
```python
from app.repositories.user_category_repository import UserCategoryRepository
from app.services.category_service import CategoryService
from app.telegram.keyboards import (
    ...existing imports...,
    categories_nav_keyboard,
)
```

Add method to `NavService`:
```python
def categories_screen(self, telegram_user_id: int) -> NavScreen:
    svc = CategoryService(self.db)
    svc.ensure_seeded(telegram_user_id)
    groups = svc.list_categories(telegram_user_id)

    lines = ["🗂 *Категории*\n"]
    type_labels = {"expense": "Расходы", "income": "Доходы", "both": "Прочее"}
    for group_type in ("expense", "income", "both"):
        cats = groups.get(group_type, [])
        if not cats:
            continue
        lines.append(f"*{type_labels[group_type]}*")
        for cat in cats:
            custom_mark = " _(кастомная)_" if cat.is_custom else ""
            lines.append(f"{cat.emoji} {cat.name_ru}{custom_mark}")
        lines.append("")

    text = "\n".join(lines).strip()
    return NavScreen(text=text, keyboard=categories_nav_keyboard(groups))
```

- [ ] **Step 2: Commit**

```bash
git add app/services/nav_service.py
git commit -m "feat(categories): add categories_screen to NavService"
```

---

### Task 8: categories_callback_handler + text_message_handler

**Files:**
- Modify: `backend/app/telegram/runtime.py`

- [ ] **Step 1: Add nav:categories to nav_callback_handler**

Inside `nav_callback_handler`, in the `with SessionLocal() as db:` block, add alongside the existing `elif section == "budgets":` etc:

```python
elif section == "categories":
    screen = nav.categories_screen(user_id)
```

This follows the exact same pattern as `planned`, `recurring`, `budgets` — `screen` is set inside the `with` block, then `await _nav_send_or_edit(query, update, screen)` is called after it.

- [ ] **Step 2: Add categories_callback_handler function**

Add this new function near the other callback handlers (e.g. after `catfix_callback_handler`).
**Important:** `_btn` is a module-private helper in `keyboards.py` — do NOT use it here. Use `InlineKeyboardButton(text=..., callback_data=...)` directly for cancel buttons.

```python
async def categories_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    param = parts[2] if len(parts) > 2 else ""
    user_id = update.effective_user.id

    from app.services.category_service import CategoryService
    from app.services.nav_service import NavService
    from app.telegram.keyboards import (
        category_edit_keyboard,
        category_type_keyboard,
        category_reassign_keyboard,
        category_delete_confirm_keyboard,
        categories_nav_keyboard,
    )

    if action == "noop":
        return

    if action == "edit":
        slug = param
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            cat = svc._repo.get_by_slug(user_id, slug)
        if cat is None:
            await query.edit_message_text("❌ Категория не найдена.")
            return
        text = f"✏️ *{cat.emoji} {cat.name_ru}*\n\nЧто изменить?"
        await query.edit_message_text(
            text,
            reply_markup=category_edit_keyboard(slug, cat.is_custom),
            parse_mode="Markdown",
        )
        return

    if action == "rename":
        slug = param
        context.user_data["awaiting_category_rename"] = slug
        await query.edit_message_text(
            "✏️ Введи новое название категории:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(text="Отмена", callback_data=f"categories:edit:{slug}")
            ]]),
        )
        return

    if action == "emoji":
        slug = param
        context.user_data["awaiting_category_emoji"] = slug
        await query.edit_message_text(
            "🎨 Отправь новый emoji для категории:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(text="Отмена", callback_data=f"categories:edit:{slug}")
            ]]),
        )
        return

    if action == "add":
        context.user_data["awaiting_category_add"] = "name"
        context.user_data.pop("pending_category_add", None)
        await query.edit_message_text(
            "➕ Введи название новой категории:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(text="Отмена", callback_data="nav:categories")
            ]]),
        )
        return

    if action == "set_type":
        cat_type = param  # expense / income / both
        pending = context.user_data.get("pending_category_add", {})
        name_ru = pending.get("name_ru", "")
        emoji = pending.get("emoji", "")
        if not name_ru or not emoji:
            await query.edit_message_text("❌ Что-то пошло не так. Попробуй снова.")
            return
        context.user_data.pop("pending_category_add", None)
        context.user_data.pop("awaiting_category_add", None)
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            try:
                cat = svc.add_custom(user_id, name_ru, emoji, cat_type)
            except ValueError as e:
                await query.edit_message_text(f"❌ {e}")
                return
        await query.edit_message_text(f"✅ Категория «{cat.emoji} {cat.name_ru}» создана!")
        return

    if action == "delete":
        slug = param
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            cat = svc._repo.get_by_slug(user_id, slug)
            if cat is None or not cat.is_custom:
                await query.edit_message_text("❌ Нельзя удалить системную категорию.")
                return
            count = svc.count_transactions(user_id, slug)
            if count > 0:
                groups = svc.list_categories(user_id)
                # Flatten categories compatible with the deleted category's type
                compatible = [
                    c
                    for cats in groups.values()
                    for c in cats
                    if c.slug != slug and (c.type == cat.type or c.type == "both" or cat.type == "both")
                ]
                await query.edit_message_text(
                    f"⚠️ В категории «{cat.name_ru}» есть {count} транзакций.\n"
                    f"Куда перенести их перед удалением?",
                    reply_markup=category_reassign_keyboard(compatible, slug),
                )
            else:
                await query.edit_message_text(
                    f"Удалить категорию «{cat.emoji} {cat.name_ru}»? Это нельзя отменить.",
                    reply_markup=category_delete_confirm_keyboard(slug),
                )
        return

    if action == "confirm_delete":
        # Only reached when transaction count == 0, so no reassignment needed.
        # delete_custom still accepts reassign_to_slug but will UPDATE 0 rows — safe no-op.
        slug = param
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            try:
                svc.delete_custom(user_id, slug, reassign_to_slug="other")
            except ValueError as e:
                await query.edit_message_text(f"❌ {e}")
                return
        await query.edit_message_text("✅ Категория удалена.")
        return

    if action == "reassign":
        # param format: "from_slug__to_slug"
        if "__" not in param:
            await query.edit_message_text("❌ Неверный формат.")
            return
        from_slug, to_slug = param.split("__", 1)
        with SessionLocal() as db:
            _ensure_user(db, update)
            svc = CategoryService(db)
            svc.ensure_seeded(user_id)
            try:
                svc.delete_custom(user_id, from_slug, to_slug)
            except ValueError as e:
                await query.edit_message_text(f"❌ {e}")
                return
        await query.edit_message_text("✅ Транзакции перенесены, категория удалена.")
        return
```

- [ ] **Step 3: Add awaiting_* blocks to text_message_handler**

In `text_message_handler`, add three blocks **before** the main transaction parsing block (follow the pattern of `awaiting_recurring_amount`):

```python
# --- Category: rename ---
awaiting_rename = context.user_data.get("awaiting_category_rename") if context.user_data else None
if awaiting_rename:
    del context.user_data["awaiting_category_rename"]
    with SessionLocal() as db:
        _ensure_user(db, update)
        from app.services.category_service import CategoryService
        svc = CategoryService(db)
        svc.ensure_seeded(update.effective_user.id)
        cat = svc.rename(update.effective_user.id, awaiting_rename, text.strip())
    if cat:
        await update.effective_message.reply_text(
            f"✅ Переименовано: {cat.emoji} {cat.name_ru}"
        )
    else:
        await update.effective_message.reply_text("❌ Категория не найдена.")
    return

# --- Category: change emoji ---
awaiting_emoji = context.user_data.get("awaiting_category_emoji") if context.user_data else None
if awaiting_emoji:
    del context.user_data["awaiting_category_emoji"]
    with SessionLocal() as db:
        _ensure_user(db, update)
        from app.services.category_service import CategoryService
        svc = CategoryService(db)
        svc.ensure_seeded(update.effective_user.id)
        try:
            cat = svc.change_emoji(update.effective_user.id, awaiting_emoji, text.strip())
        except ValueError as e:
            await update.effective_message.reply_text(f"❌ {e} Попробуй ещё раз.")
            context.user_data["awaiting_category_emoji"] = awaiting_emoji
            return
    if cat:
        await update.effective_message.reply_text(f"✅ Emoji обновлён: {cat.emoji} {cat.name_ru}")
    else:
        await update.effective_message.reply_text("❌ Категория не найдена.")
    return

# --- Category: add (name or emoji step) ---
awaiting_add = context.user_data.get("awaiting_category_add") if context.user_data else None
if awaiting_add == "name":
    context.user_data["awaiting_category_add"] = "emoji"
    context.user_data["pending_category_add"] = {"name_ru": text.strip(), "emoji": ""}
    await update.effective_message.reply_text(
        f"Название: «{text.strip()}»\n\nТеперь отправь emoji для этой категории:"
    )
    return
if awaiting_add == "emoji":
    from app.services.category_service import _is_emoji
    emoji_input = text.strip()
    if not _is_emoji(emoji_input):
        await update.effective_message.reply_text(
            "❌ Не похоже на emoji. Попробуй ещё раз (например: 🏋 или ⚽):"
        )
        return
    pending = context.user_data.get("pending_category_add", {})
    pending["emoji"] = emoji_input
    context.user_data["pending_category_add"] = pending
    del context.user_data["awaiting_category_add"]
    from app.telegram.keyboards import category_type_keyboard
    await update.effective_message.reply_text(
        f"Emoji: {emoji_input}\n\nВыбери тип категории:",
        reply_markup=category_type_keyboard(),
    )
    return
```

- [ ] **Step 4: Register the handler in build_application**

In `build_application()`, add after `catfix_callback_handler`:
```python
application.add_handler(CallbackQueryHandler(categories_callback_handler, pattern=r"^categories:"))
```

- [ ] **Step 5: Commit**

```bash
git add app/telegram/runtime.py
git commit -m "feat(categories): add categories_callback_handler and text_message_handler state"
```

---

### Task 9: Final verification

- [ ] **Step 1: Run full test suite**

```bash
cd backend && pytest -v 2>&1 | tail -20
```
Expected: all existing tests pass, `test_category_service.py` all PASSED

- [ ] **Step 2: Manual smoke test (bot running)**

1. `/menu` → появилась кнопка «🗂 Категории»
2. Нажать «Категории» → список с ~20 системными категориями
3. Нажать ✏️ на «Еда» → меню редактирования (без кнопки 🗑)
4. «Изменить название» → ввести «Питание» → получить «✅ Переименовано: 🍕 Питание»
5. «➕ Добавить» → ввести «Спорт» → ввести «🏋» → выбрать «Расход» → «✅ Категория создана»
6. В списке появилась «🏋 Спорт» с кнопкой 🗑
7. Нажать 🗑 на «Спорт» (без транзакций) → подтверждение → «✅ Категория удалена»

- [ ] **Step 3: Final commit**

```bash
cd backend && git add -A
git commit -m "feat(categories): complete categories UI — view, add, edit, delete"
```
