"""
Eval tests for ParserService golden cases.
Loads backend/tests/evals/parser_cases.yaml and runs each case as a parametrized test.
Purpose: catch regressions when YAML patterns or parser logic changes.
"""
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from app.services.parser_service import ParserService

_CASES_FILE = Path(__file__).parent / "evals" / "parser_cases.yaml"


def _load_cases():
    data = yaml.safe_load(_CASES_FILE.read_text(encoding="utf-8"))
    return [(c["id"], c["input"], c["expected"]) for c in data["cases"]]


@pytest.mark.parametrize("case_id,text,expected", _load_cases(), ids=[c[0] for c in _load_cases()])
def test_parser_golden_case(case_id: str, text: str, expected: dict) -> None:
    parser = ParserService()
    result = parser.parse(text)

    assert result.matched, f"[{case_id}] Parser did not match: {text!r}"

    if "transaction_type" in expected:
        assert result.transaction_type == expected["transaction_type"], (
            f"[{case_id}] transaction_type: got {result.transaction_type!r}, "
            f"expected {expected['transaction_type']!r}"
        )

    if "category" in expected:
        assert result.category == expected["category"], (
            f"[{case_id}] category: got {result.category!r}, "
            f"expected {expected['category']!r}"
        )

    if "amount" in expected:
        assert result.amount == Decimal(str(expected["amount"])), (
            f"[{case_id}] amount: got {result.amount}, expected {expected['amount']}"
        )

    if "confidence_label" in expected:
        assert result.confidence_label == expected["confidence_label"], (
            f"[{case_id}] confidence_label: got {result.confidence_label!r}, "
            f"expected {expected['confidence_label']!r}"
        )
