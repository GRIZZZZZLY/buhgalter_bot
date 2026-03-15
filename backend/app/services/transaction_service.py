from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.transaction_repository import TransactionRepository
from app.schemas.parser import ParseResult
from app.schemas.summary import CategoryTotal, SummaryMetrics
from app.schemas.transaction import TransactionItem, TransactionUpdateRequest


class TransactionService:
    def __init__(self, db: Session) -> None:
        self.repository = TransactionRepository(db)

    def build_create_payload(self, telegram_user_id: int, source: str, parsed: ParseResult) -> dict:
        if parsed.amount is None or parsed.transaction_type is None or parsed.category is None:
            raise ValueError("Parsed result is incomplete for persistence")
        return {
            "telegram_user_id": telegram_user_id,
            "type": parsed.transaction_type,
            "amount": Decimal(parsed.amount),
            "category": parsed.category,
            "description": parsed.description,
            "source": source,
            "raw_input": parsed.raw_input,
            "confidence": parsed.confidence,
        }

    def create_from_parse(self, telegram_user_id: int, source: str, parsed: ParseResult) -> TransactionItem:
        payload = self.build_create_payload(telegram_user_id, source, parsed)
        transaction = self.repository.create(payload)
        return self._to_item(transaction)

    def list_transactions(self, telegram_user_id: int, limit: int, offset: int, period: str) -> list[TransactionItem]:
        return [
            self._to_item(item)
            for item in self.repository.list_for_user(telegram_user_id, limit=limit, offset=offset, period=period)
        ]

    def list_recent_for_delete(self, telegram_user_id: int, limit: int = 5) -> list[dict[str, str]]:
        items = self.list_transactions(telegram_user_id=telegram_user_id, limit=limit, offset=0, period="all")
        result: list[dict[str, str]] = []
        for item in items:
            result.append(
                {
                    "id": str(item.id),
                    "amount": item.amount,
                    "category": item.category,
                    "type": item.type,
                    "created_at": item.created_at,
                }
            )
        return result

    def get_summary(self, telegram_user_id: int, period: str) -> SummaryMetrics:
        summary = self.repository.get_summary(telegram_user_id, period)
        return SummaryMetrics(
            balance=self._format_decimal(summary["balance"]),
            income_total=self._format_decimal(summary["income_total"]),
            expense_total=self._format_decimal(summary["expense_total"]),
            top_expense_categories=[
                CategoryTotal(category=item["category"], amount=self._format_decimal(item["amount"]))
                for item in summary["top_expense_categories"]
            ],
        )

    def update_transaction(
        self,
        telegram_user_id: int,
        transaction_id: UUID,
        payload: TransactionUpdateRequest,
    ) -> TransactionItem | None:
        update_payload = payload.model_dump(exclude_unset=True)
        transaction = self.repository.update(telegram_user_id, transaction_id, update_payload)
        if transaction is None:
            return None
        return self._to_item(transaction)

    def delete_transaction(self, telegram_user_id: int, transaction_id: UUID) -> bool:
        return self.repository.delete(telegram_user_id, transaction_id)

    def delete_all_for_user(self, telegram_user_id: int) -> int:
        return self.repository.delete_all_for_user(telegram_user_id)

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        return f"{Decimal(value):.2f}"

    @classmethod
    def _to_item(cls, transaction) -> TransactionItem:
        return TransactionItem(
            id=transaction.id,
            telegram_user_id=transaction.telegram_user_id,
            type=transaction.type.value,
            amount=cls._format_decimal(transaction.amount),
            category=transaction.category,
            description=transaction.description,
            source=transaction.source.value,
            raw_input=transaction.raw_input,
            confidence=transaction.confidence,
            created_at=transaction.created_at.isoformat(),
            updated_at=transaction.updated_at.isoformat(),
        )
