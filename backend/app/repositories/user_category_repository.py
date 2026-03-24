# backend/app/repositories/user_category_repository.py
from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.user_category import UserCategory

# System category seed data: slug -> (name_ru, emoji, type)
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
