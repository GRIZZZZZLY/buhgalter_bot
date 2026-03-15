from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TransactionItem(BaseModel):
    id: UUID
    telegram_user_id: int
    type: Literal["income", "expense"]
    amount: str
    category: str
    description: str | None = None
    source: Literal["text", "voice"]
    raw_input: str
    confidence: float
    created_at: str
    updated_at: str


class TransactionListResponse(BaseModel):
    items: list[TransactionItem]
    limit: int
    offset: int
    period: str


class TransactionUpdateRequest(BaseModel):
    type: Literal["income", "expense"] | None = None
    amount: str | None = Field(default=None, pattern=r"^\d+(\.\d{1,2})?$")
    category: str | None = None
    description: str | None = Field(default=None, max_length=255)
