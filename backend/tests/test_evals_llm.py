"""
Eval tests for LLMService._parse_response() golden cases.
Loads backend/tests/evals/llm_parse_cases.yaml and runs each case parametrized.
Purpose: catch prompt/model regressions — verifies that JSON → LLMResult parsing
stays stable when prompts or models change. Tests _parse_response directly to avoid
live API calls while still covering the full parsing logic.
"""
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.llm_service import LLMService, LLMTransactionResult, LLMAdvisorResult

_CASES_FILE = Path(__file__).parent / "evals" / "llm_parse_cases.yaml"

_engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_engine)


def _make_service() -> LLMService:
    return LLMService(_Session())


def _load_cases():
    data = yaml.safe_load(_CASES_FILE.read_text(encoding="utf-8"))
    return [(c["id"], c["input"], c["mock_response"].strip(), c["expected"]) for c in data["cases"]]


@pytest.mark.parametrize(
    "case_id,text,mock_json,expected",
    _load_cases(),
    ids=[c[0] for c in _load_cases()],
)
def test_llm_parse_response_golden_case(case_id: str, text: str, mock_json: str, expected: dict) -> None:
    service = _make_service()
    result = service._parse_response(mock_json, text)

    assert result is not None, f"[{case_id}] _parse_response returned None"

    # Check intent
    if "intent" in expected:
        assert result.intent == expected["intent"], (
            f"[{case_id}] intent: got {result.intent!r}, expected {expected['intent']!r}"
        )

    if expected.get("intent") == "transaction":
        assert isinstance(result, LLMTransactionResult), f"[{case_id}] expected LLMTransactionResult"

        if "items_count" in expected:
            assert len(result.items) == expected["items_count"], (
                f"[{case_id}] items_count: got {len(result.items)}, expected {expected['items_count']}"
            )

        if "first_item" in expected and result.items:
            item_exp = expected["first_item"]
            parsed = result.items[0].parsed

            if "transaction_type" in item_exp:
                assert parsed.transaction_type == item_exp["transaction_type"], (
                    f"[{case_id}] first_item.transaction_type: got {parsed.transaction_type!r}, "
                    f"expected {item_exp['transaction_type']!r}"
                )

            if "category" in item_exp:
                assert parsed.category == item_exp["category"], (
                    f"[{case_id}] first_item.category: got {parsed.category!r}, "
                    f"expected {item_exp['category']!r}"
                )

            if "amount" in item_exp:
                from decimal import Decimal
                assert parsed.amount == Decimal(str(item_exp["amount"])), (
                    f"[{case_id}] first_item.amount: got {parsed.amount}, expected {item_exp['amount']}"
                )

    elif expected.get("intent") == "advisor":
        assert isinstance(result, LLMAdvisorResult), f"[{case_id}] expected LLMAdvisorResult"
        assert result.answer, f"[{case_id}] advisor answer is empty"
