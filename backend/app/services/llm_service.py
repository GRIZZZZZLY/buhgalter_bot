"""LLM-powered transaction parser and financial advisor via OpenRouter."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from openai import APIError, OpenAI
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.schemas.parser import ParseResult
from app.services.config_loader import load_yaml

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
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.groq_api_key,
            timeout=60.0,
        )
        self._model = settings.llm_model
        self._categories_config = load_yaml("categories.yaml")
        self._valid_slugs: set[str] = {
            cat["slug"] for cat in self._categories_config["ru"]["categories"]
        }

    def process(self, text: str, telegram_user_id: int) -> LLMResult:
        """Parse a user message into a transaction or an advisor answer."""
        system_prompt = self._build_system_prompt()

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

    def extract_planned(self, text: str, user_categories: list[dict]) -> dict | None:
        """Extract planned expense fields from free-form text.

        Args:
            text: user message (already transcribed if voice)
            user_categories: list of {"slug": str, "name_ru": str}

        Returns:
            dict with keys title, amount, category_slug, planned_date_iso — or None on error.
        """
        category_lines = "\n".join(
            f"- {c['slug']}: {c['name_ru']}" for c in user_categories
        ) or "- other: Прочее"
        today = date.today().isoformat()
        system = (
            f"Ты ассистент для извлечения данных. Сегодня {today}.\n"
            "Извлеки параметры запланированного расхода из текста.\n"
            'Верни JSON: {"title": str, "amount": float, "category_slug": str, "planned_date_iso": str | null}\n'
            f"Категории пользователя (используй только эти slug):\n{category_lines}\n"
            'planned_date_iso: дата ISO "YYYY-MM-DD", null если не упомянута.\n'
            'Если категория не ясна — "other".'
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
            logger.error("extract_planned error: %s", exc)
            return None

    def extract_recurring(self, text: str, user_categories: list[dict]) -> dict | None:
        """Extract recurring transaction fields from free-form text.

        Args:
            text: user message (already transcribed if voice)
            user_categories: list of {"slug": str, "name_ru": str}

        Returns:
            dict with keys title, amount, transaction_type, category_slug, frequency, day_value
            — or None on error.
        """
        category_lines = "\n".join(
            f"- {c['slug']}: {c['name_ru']}" for c in user_categories
        ) or "- other: Прочее"
        system = (
            "Ты ассистент для извлечения данных.\n"
            "Извлеки параметры регулярного платежа из текста.\n"
            'Верни JSON: {"title": str, "amount": float, '
            '"transaction_type": "expense"|"income", "category_slug": str, '
            '"frequency": "monthly"|"weekly"|"daily"|"interval_days", "day_value": int}\n'
            f"Категории пользователя (используй только эти slug):\n{category_lines}\n"
            "monthly: day_value = день месяца (1-28).\n"
            "weekly: day_value = день недели (0=пн...6=вс).\n"
            "interval_days: day_value = количество дней.\n"
            "daily: day_value = 1.\n"
            'Если тип (расход/доход) не ясен — "expense". Если категория не ясна — "other".'
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
            logger.error("extract_recurring error: %s", exc)
            return None

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

    def _build_system_prompt(self) -> str:
        categories = self._categories_config["ru"]["categories"]
        category_lines = "\n".join(
            f"- {cat['slug']}: {', '.join(str(s) for s in cat['synonyms'][:3])}"
            for cat in categories
        )
        today = datetime.now().strftime("%Y-%m-%d")

        return (
            f"Ты финансовый ассистент для личного бюджета. Сегодня {today}.\n\n"
            f"КАТЕГОРИИ (используй только эти slug):\n{category_lines}\n\n"
            "Верни JSON строго одного из двух форматов:\n"
            '1. Транзакция: {"intent":"transaction","items":[{"type":"expense"|"income",'
            '"amount":число,"category":"slug из списка","description":"строка или null","date":"YYYY-MM-DD или null"}]}\n'
            '2. Вопрос: {"intent":"advisor","answer":"ответ на русском языке"}\n\n'
            "Правила: только валидный JSON без markdown-обёртки; "
            "category ТОЛЬКО из списка выше; date=null если речь идёт о сегодня; "
            "если сумма не указана — это advisor, не transaction."
        )
