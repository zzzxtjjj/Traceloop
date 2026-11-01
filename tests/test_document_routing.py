from services.document_routing_service import route_text


def test_routing_matches_existing_philips_inputs():
    product = route_text(
        filename="Philips_NA120_Public_Product_Brief.docx",
        text="Product brief specification for NA120 air fryer manual and product facts",
    )
    quote = route_text(
        filename="Supplier_Listing_Comparison.xlsx",
        text="supplier quotation currency MOQ quotation price lead time",
    )
    reviews = route_text(
        filename="philips_na120_reviews.csv",
        text="review_id rating review_text customer review",
    )
    assert product.primary_department == "运营"
    assert quote.primary_department == "采购"
    assert reviews.primary_department == "品控"


def test_unknown_document_requires_manual_sorting():
    result = route_text(filename="upload.bin", text="unrelated content")
    assert result.primary_department is None
    assert result.document_type == "Unknown / Mixed Document"
    assert result.uncertainty == "low"
