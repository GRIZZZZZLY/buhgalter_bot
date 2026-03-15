from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


ConfidenceLabel = Literal["high", "medium", "low", "fallback"]
TransactionTypeName = Literal["income", "expense"]


@dataclass(slots=True)
class ParseResult:
    matched: bool
    confidence: float
    confidence_label: ConfidenceLabel
    transaction_type: TransactionTypeName | None
    amount: Decimal | None
    category: str | None
    description: str | None
    pattern: str | None
    raw_input: str


@dataclass(slots=True)
class MultiParseResult:
    items: list[ParseResult]
    raw_input: str

    @property
    def has_items(self) -> bool:
        return bool(self.items)
