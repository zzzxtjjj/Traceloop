import pytest

from core.schemas import QuoteRow
from services.supplier_scoring import calculate_supplier_scores, validate_weights


def make_quote(supplier: str, price: float, moq: int, lead: int, note: str = "") -> QuoteRow:
    return QuoteRow(
        supplier=supplier,
        unit_price=price,
        currency="USD",
        moq=moq,
        lead_time_days=lead,
        payment_terms="30% deposit",
        quality_note=note,
    )


def test_score_is_deterministic_and_sorted() -> None:
    quotes = [
        make_quote("A", 5.0, 500, 20),
        make_quote("B", 4.0, 700, 30, "样品未确认"),
        make_quote("C", 5.5, 300, 10),
    ]
    first = calculate_supplier_scores(quotes)
    second = calculate_supplier_scores(quotes)
    assert first == second
    assert [item.total_score for item in first] == sorted(
        [item.total_score for item in first], reverse=True
    )


def test_equal_values_do_not_create_fake_difference() -> None:
    quotes = [make_quote("A", 5.0, 500, 20), make_quote("B", 5.0, 500, 20)]
    scores = calculate_supplier_scores(quotes)
    assert scores[0].total_score == scores[1].total_score == 100


def test_risk_keyword_reduces_quality_score() -> None:
    scores = calculate_supplier_scores(
        [make_quote("A", 5.0, 500, 20), make_quote("B", 5.0, 500, 20, "样品未确认")]
    )
    by_name = {item.supplier: item for item in scores}
    assert by_name["B"].quality_score < by_name["A"].quality_score
    assert "样品未确认" in by_name["B"].risk_hits


def test_weights_must_sum_to_100() -> None:
    with pytest.raises(ValueError, match="100"):
        validate_weights({"price": 40, "moq": 20, "lead_time": 30, "quality": 20})

