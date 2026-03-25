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

    def toggle_hidden(self, telegram_user_id: int, slug: str) -> "UserCategory | None":
        """Toggle is_hidden on a category. Seeds built-ins first if not yet seeded."""
        cat = self._repo.get_by_slug(telegram_user_id, slug)
        if cat is None:
            self.ensure_seeded(telegram_user_id)
            cat = self._repo.get_by_slug(telegram_user_id, slug)
        if cat is None:
            return None
        updated = self._repo.update(cat.id, is_hidden=not cat.is_hidden)
        self.db.commit()
        return updated

    def get_visible_for_type(self, telegram_user_id: int, tx_type: str) -> "list[UserCategory]":
        """Return non-hidden categories matching tx_type or 'both'."""
        all_cats = self._repo.get_all(telegram_user_id)
        return [
            c for c in all_cats
            if not c.is_hidden and c.type in (tx_type, "both")
        ]

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
