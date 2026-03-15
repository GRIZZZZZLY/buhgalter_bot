from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user_category_mapping import UserCategoryMapping


class UserCategoryMappingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def find(self, telegram_user_id: int, merchant_text: str) -> UserCategoryMapping | None:
        """Find a mapping for a specific merchant text (case-insensitive via pre-normalized input)."""
        stmt = select(UserCategoryMapping).where(
            UserCategoryMapping.telegram_user_id == telegram_user_id,
            UserCategoryMapping.merchant_text == merchant_text,
        )
        return self.db.scalar(stmt)

    def upsert(self, telegram_user_id: int, merchant_text: str, category: str) -> UserCategoryMapping:
        """Create or update a merchant->category mapping, incrementing usage_count."""
        mapping = self.find(telegram_user_id, merchant_text)
        if mapping is None:
            mapping = UserCategoryMapping(
                telegram_user_id=telegram_user_id,
                merchant_text=merchant_text,
                category=category,
                usage_count=1,
            )
            self.db.add(mapping)
        else:
            mapping.category = category
            mapping.usage_count += 1
        self.db.flush()
        return mapping

    def get_top_categories(self, telegram_user_id: int, limit: int = 3) -> list[str]:
        """Return the user's most-used categories, ordered by total usage."""
        stmt = (
            select(UserCategoryMapping.category)
            .where(UserCategoryMapping.telegram_user_id == telegram_user_id)
            .group_by(UserCategoryMapping.category)
            .order_by(func.sum(UserCategoryMapping.usage_count).desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def is_confident(self, mapping: UserCategoryMapping, threshold: int = 3) -> bool:
        """Return True if the mapping has been used enough times to auto-apply."""
        return mapping.usage_count >= threshold
