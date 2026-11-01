import pytest
from pydantic import ValidationError

from services.document_ai_schemas import (
    DocumentAnalysisOutput,
    DocumentClassification,
    DynamicAttribute,
    EvidenceQuote,
)


def _analysis(**kwargs):
    base = dict(
        summary=[], important_facts=[], requirement_signals=[], conflicts=[],
        missing_information=[], risks=[], classification=DocumentClassification(
            document_type="business document", business_scenarios=["review"], entities=["product"]
        ), dynamic_attributes=[],
    )
    base.update(kwargs)
    return DocumentAnalysisOutput(**base)


@pytest.mark.parametrize("kind,field,value,unit", [
    ("air_fryer", "basket_volume", "4.2", "L"),
    ("air_purifier", "CADR", "320", "m3/h"),
    ("industrial_machine", "working_range", "1200 x 800", "mm"),
    ("textile", "fiber_composition", "100% cotton", None),
    ("furniture", "load_capacity", "120", "kg"),
])
def test_dynamic_attributes_accept_unseen_industry_fields(kind, field, value, unit):
    attr = DynamicAttribute(
        field_name=field, display_name=field, value=value, unit=unit,
        evidence=[EvidenceQuote(evidence_id=1, quote=value)],
    )
    result = _analysis(
        classification={"document_type": kind, "business_scenarios": [], "entities": []},
        dynamic_attributes=[attr],
    )
    assert result.dynamic_attributes[0].field_name == field


@pytest.mark.parametrize(
    "document_type", ["supplier quotation", "purchase contract", "quality inspection report"]
)
def test_non_product_documents_are_classifiable(document_type):
    result = _analysis(
        classification={
            "document_type": document_type,
            "business_scenarios": ["trade"],
            "entities": ["supplier"],
        }
    )
    assert result.classification.document_type == document_type
    assert result.dynamic_attributes == []


def test_missing_attribute_is_not_guessed():
    attr = DynamicAttribute(field_name="power", display_name="Power", value=None)
    assert attr.value is None
    assert _analysis(dynamic_attributes=[attr]).dynamic_attributes[0].review_status == (
        "needs_review"
    )


def test_unknown_attribute_cannot_contain_value():
    with pytest.raises(ValidationError):
        DynamicAttribute(
            field_name="unknown",
            display_name="Unknown",
            value="100",
            epistemic_status="unknown",
        )


def test_conflicting_values_are_preserved_as_separate_attributes():
    attrs = [
        DynamicAttribute(
            field_name="capacity",
            display_name="Capacity",
            value="4 L",
            evidence=[EvidenceQuote(evidence_id=1, quote="4 L")],
        ),
        DynamicAttribute(
            field_name="capacity",
            display_name="Capacity",
            value="4.2 L",
            evidence=[EvidenceQuote(evidence_id=2, quote="4.2 L")],
        ),
    ]
    result = _analysis(
        dynamic_attributes=attrs,
        conflicts=[
            {
                "description": "Capacity differs",
                "evidence": [
                    {"evidence_id": 1, "quote": "4 L"},
                    {"evidence_id": 2, "quote": "4.2 L"},
                ],
            }
        ],
    )
    assert [a.value for a in result.dynamic_attributes] == ["4 L", "4.2 L"]
