"""Calls LLM to suggest improvements to categories.yaml."""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from typing import Literal
from openai import APIError, OpenAI
from sqlalchemy.orm import Session
from app.core.settings import get_settings
from app.repositories.transaction_repository import TransactionRepository
from app.services.config_loader import load_yaml
from app.services.llm_service import LLMUnavailableError

logger = logging.getLogger(__name__)


@dataclass
class AddSynonymSuggestion:
    type: Literal["add_synonym"]
    category_slug: str
    synonym: str


@dataclass
class NewCategorySuggestion:
    type: Literal["new_category"]
    slug: str
    tx_type: str
    synonyms: list[str]


Suggestion = AddSynonymSuggestion | NewCategorySuggestion


class CategorySuggestionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        settings = get_settings()
        self._client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=settings.groq_api_key, timeout=60.0)
        self._model = settings.llm_model
        self._categories_config = load_yaml("categories.yaml")

    def get_suggestions(self, telegram_user_id: int) -> list[Suggestion]:
        transactions = TransactionRepository(self.db).list_for_user(telegram_user_id, limit=200, offset=0, period="month")
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._build_prompt(transactions)},
                    {"role": "user", "content": "Проанализируй транзакции и предложи улучшения."},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
        except APIError as exc:
            logger.error("LLM error in CategorySuggestionService: %s", exc)
            raise LLMUnavailableError(str(exc)) from exc
        return self._parse(response.choices[0].message.content or "")

    def _build_prompt(self, transactions: list) -> str:
        categories = self._categories_config["ru"]["categories"]
        cat_lines = "\n".join(f"- {c['slug']}: {', '.join(str(s) for s in c['synonyms'][:5])}" for c in categories)
        tx_lines = "\n".join(f"{tx.created_at.strftime('%d.%m')}: {tx.category} | {tx.description or ''}" for tx in transactions) or "нет транзакций"
        return (
            f"Текущие категории:\n{cat_lines}\n\nТранзакции:\n{tx_lines}\n\n"
            "Найди слова в описаниях, которых нет в синонимах, и транзакции с категорией 'other'.\n"
            'Верни JSON: {"suggestions": [{"type":"add_synonym","category_slug":"food","synonym":"бургер кинг"} | '
            '{"type":"new_category","slug":"sport","transaction_type":"expense","synonyms":["gym","фитнес"]}]}\n'
            "Не более 10 предложений."
        )

    def _parse(self, raw: str) -> list[Suggestion]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMUnavailableError("invalid JSON from LLM") from exc
        results: list[Suggestion] = []
        for item in data.get("suggestions") or []:
            t = item.get("type")
            if t == "add_synonym":
                slug, syn = item.get("category_slug", ""), item.get("synonym", "")
                if slug and syn:
                    results.append(AddSynonymSuggestion(type="add_synonym", category_slug=slug, synonym=syn))
            elif t == "new_category":
                slug = item.get("slug", "")
                syns = item.get("synonyms") or []
                if slug and syns:
                    results.append(NewCategorySuggestion(type="new_category", slug=slug, tx_type=item.get("transaction_type", "expense"), synonyms=syns))
        return results
