from io import BytesIO
from pathlib import Path

from services.imports import preview_quote_csv

DEMO_FILE = Path(__file__).resolve().parents[1] / "data" / "demo" / "supplier_quotes.csv"


def test_valid_demo_csv() -> None:
    preview = preview_quote_csv(DEMO_FILE)
    assert preview.is_valid
    assert len(preview.rows) == 3
    assert preview.rows[0].currency == "USD"


def test_missing_column_is_rejected() -> None:
    content = b"supplier,unit_price,currency\nA,4.5,USD\n"
    source = BytesIO(content)
    source.name = "missing.csv"
    preview = preview_quote_csv(source)
    assert not preview.is_valid
    assert any(error.field == "moq" for error in preview.errors)


def test_mixed_currency_is_rejected() -> None:
    content = (
        b"supplier,unit_price,currency,moq,lead_time_days,payment_terms,quality_note\n"
        b"A,4.5,USD,100,10,deposit,ok\n"
        b"B,4.2,EUR,100,10,deposit,ok\n"
    )
    source = BytesIO(content)
    source.name = "mixed.csv"
    preview = preview_quote_csv(source)
    assert not preview.is_valid
    assert any(error.field == "currency" for error in preview.errors)

