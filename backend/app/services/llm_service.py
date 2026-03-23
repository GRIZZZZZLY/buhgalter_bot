"""LLM-powered transaction parser and financial advisor via OpenRouter."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Literal

from openai import APIError, OpenAI
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.parser import ParseResult
from app.services.config_loader import load_yaml

if TYPE_CHECKING:
    from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------


class LLMUnavailableError(Exception):
    """Raised when OpenRouter is unreachable or returns unusable output."""


@dataclass
class LLMParsedItem:
    parsed: ParseResult
    override_date: date | None  # None = today


@dataclass
class LLMTransactionResult:
    intent: Literal["transaction"]
    items: list[LLMParsedItem]


@dataclass
class LLMAdvisorResult:
    intent: Literal["advisor"]
    answer: str


LLMResult = LLMTransactionResult | LLMAdvisorResult


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class LLMService:
    def __init__(self, db: Session) -> None:
        self.db = db
        settings = get_settings()
        self._client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
        )
        self._model = settings.llm_model
        self._categories_config = load_yaml("categories.yaml")
        self._valid_slugs: set[str] = {
            cat["slug"] for cat in self._categories_config["ru"]["categories"]
        }

    def process(self, text: str, telegram_user_id: int) -> LLMResult:
        """Parse a user message into a transaction or an advisor answer."""
        transactions = TransactionRepository(self.db).list_for_user(
            telegram_user_id, limit=50, offset=0, period="month"
        )
        system_prompt = self._build_system_prompt(transactions)

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
        except APIError as exc:
            logger.error("OpenRouter API error: %s", exc)
            raise LLMUnavailableError(str(exc)) from exc

        raw = response.choices[0].message.content or ""
        return self._parse_response(raw, text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_response(self, raw: str, original_text: str) -> LLMResult:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error("LLM returned invalid JSON: %r", raw)
            raise LLMUnavailableError("invalid JSON from LLM") from exc

        intent = data.get("intent")

        if intent == "advisor":
            answer = (data.get("answer") or "").strip()
            if not answer:
                raise LLMUnavailableError("empty advisor answer")
            return LLMAdvisorResult(intent="advisor", answer=answer)

        if intent == "transaction":
            raw_items = data.get("items") or []
            if not raw_items:
                raise LLMUnavailableError("empty transaction items list")
            items = [self._parse_item(item, original_text) for item in raw_items]
            return LLMTransactionResult(intent="transaction", items=items)

        raise LLMUnavailableError(f"unknown intent: {intent!r}")

    def _parse_item(self, item: dict, original_text: str) -> LLMParsedItem:
        try:
            amount = Decimal(str(item["amount"]))
        except (KeyError, InvalidOperation) as exc:
            raise LLMUnavailableError(f"invalid amount: {item.get('amount')!r}") from exc

        tx_type = item.get("type", "expense")
        if tx_type not in ("income", "expense"):
            tx_type = "expense"

        category = item.get("category") or "other"
        if category not in self._valid_slugs:
            category = "other"

        override_date: date | None = None
        raw_date = item.get("date")
        if raw_date:
            try:
                override_date = date.fromisoformat(raw_date)
            except ValueError:
                override_date = None

        parsed = ParseResult(
            matched=True,
            confidence=0.95,
            confidence_label="high",
            transaction_type=tx_type,
            amount=amount,
            category=category,
            description=item.get("description"),
            pattern="llm",
            raw_input=original_text,
        )
        return LLMParsedItem(parsed=parsed, override_date=override_date)

    def _build_system_prompt(self, transactions: list) -> str:
        categories = self._categories_config["ru"]["categories"]
        category_lines = "\n".join(
            f"- {cat['slug']}: {', '.join(str(s) for s in cat['synonyms'][:5])}"
            for cat in categories
        )
        tx_lines = "\n".join(
            f"{tx.created_at.strftime('%d.%m')}: {tx.type.value} {tx.amount} {tx.category}"
            for tx in transactions
        ) or "нет транзакций"
        today = datetime.now().strftime("%Y-%m-%d")

        return (
            f"Ты финансовый ассистент для личного бюджета. Сегодня {today}.\n\n"
            f"КАТЕГОРИИ (используй только эти slug):\n{category_lines}\n\n"
            f"ИСТОРИЯ ТРАНЗАКЦИЙ ЗА МЕСЯЦ:\n{tx_lines}\n\n"
            "Верни JSON строго одного из двух форматов:\n"
            '1. Транзакция: {"intent":"transaction","items":[{"type":"expense"|"income",'
            '"amount":число,"category":"slug из списка","description":"строка или null","date":"YYYY-MM-DD или null"}]}\n'
            '2. Вопрос: {"intent":"advisor","answer":"ответ на русском языке"}\n\n'
            "Правила: только валидный JSON без markdown-обёртки; "
            "category ТОЛЬКО из списка выше; date=null если речь идёт о сегодня; "
            "если сумма не указана — это advisor, не transaction."
        )
