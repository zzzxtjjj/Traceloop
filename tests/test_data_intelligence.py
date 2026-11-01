from services.data_intelligence import assess_readiness, suggest_column_mapping


def test_unknown_columns_are_preserved_as_custom_fields():
    mapping = suggest_column_mapping(
        ["Review Text", "国家", "Internal Flag"], domain="customer_feedback"
    )
    assert mapping["Review Text"]["canonical_field"] == "review_text"
    assert mapping["Internal Flag"]["mapping_status"] == "custom_field"


def test_readiness_is_task_specific():
    readiness = assess_readiness(
        domain="customer_feedback", mapped_fields={"review_text"}, row_count=2
    )
    assert readiness["import_status"] == "IMPORTABLE"
    assert readiness["operations"]["text_analysis"] is True
    assert readiness["operations"]["market_comparison"] is False
    assert readiness["operations"]["time_trend"] is False


def test_supplier_quote_readiness_requires_currency_for_price_comparison():
    readiness = assess_readiness(
        domain="supplier_quotation",
        mapped_fields={"supplier", "unit_price"},
        row_count=1,
    )
    assert readiness["operations"]["price_comparison"] is False
