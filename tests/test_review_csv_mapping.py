from services.review_service import preview_review_csv


def test_review_csv_maps_common_names_and_generates_batch():
    raw = (
        b"review_id,score,review_date,product_model,country,comment\n"
        b"R1,2,2026-01-02,NA120/00,DE,The basket broke\n"
    )
    preview = preview_review_csv(raw)
    assert preview.is_valid
    assert preview.rows[0].batch.startswith("import-")
    assert preview.rows[0].date.isoformat() == "2026-01-02"
    assert preview.rows[0].sku == "NA120/00"
    assert preview.rows[0].market == "DE"
    assert preview.column_mapping["batch"] == "(自动生成)"


def test_review_csv_keeps_missing_truthful_fields_unknown_but_importable():
    raw = b"id,rating,comment\nR1,2,The basket broke\n"
    preview = preview_review_csv(raw)
    assert preview.is_valid
    assert not preview.errors
    assert set(preview.missing_columns) >= {"date", "sku", "market"}
    assert preview.rows[0].date is None
    assert preview.rows[0].sku is None
    assert preview.rows[0].market is None


def test_review_csv_normalizes_header_spacing_and_case():
    raw = (
        b" Review ID , Rating , Published At , Product SKU , Marketplace , Review Text \n"
        b"R1,5,2026-02-01,A-1,US,Works well\n"
    )
    preview = preview_review_csv(raw)
    assert preview.is_valid
    assert preview.rows[0].market == "US"


def test_review_csv_allows_mixed_markets_without_inventing_one():
    raw = (
        b"review_id,rating,date,sku,market,review_text\n"
        b"R1,2,2026-02-01,A-1,US,Issue\n"
        b"R2,3,2026-02-02,A-1,DE,Okay\n"
    )
    preview = preview_review_csv(raw)
    assert preview.is_valid
    assert {row.market for row in preview.rows} == {"US", "DE"}


def test_public_philips_source_note_is_not_accepted_as_a_customer_review():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "acceptance"
        / "public_benchmark"
        / "philips_na120"
        / "03_customer_feedback"
        / "philips_na120_reviews.csv"
    )
    preview = preview_review_csv(source)
    assert len(preview.rows) == 1
    assert not preview.is_valid
    assert any(
        error.field == "review_text" and "不是客户评价正文" in error.message
        for error in preview.errors
    )
    assert preview.readiness["operations"].get("text_analysis") is not True


def test_valid_review_without_date_keeps_date_unknown():
    raw = b"review_id,sku,rating,review_text\nR1,A-1,2,The product arrived damaged\n"
    preview = preview_review_csv(raw)
    assert preview.is_valid
    assert preview.rows[0].date is None
