from pathlib import Path

import pytest

from services.product_content_pipeline import (
    assemble_product_content,
    import_round1_copy,
    validate_final_content,
)
from services.product_fact_repository import BaselineFactRepository, load_dreo_baseline
from services.specification_renderer import ProductFact, render_specifications

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = "DREO-CERAMIC-HEATER-316"


@pytest.fixture
def repository():
    return load_dreo_baseline(
        ROOT / "tests/fixtures/dreo_316_step2_cases.json",
        ROOT / "docs/product_validation/PRODUCT_FACTS.md",
    )


def render(repo, market="US"):
    return render_specifications(
        repo, product_id=PRODUCT, market=market, template_id=f"heater_{market.lower()}_v1"
    )


def test_us_template_required_values_and_determinism(repository):
    result = render(repository)
    assert result == render(repository)
    assert result.required_fields_complete
    assert all(
        value in result.table_markdown
        for value in (
            "DR-HSH006",
            "120 V AC",
            "60 Hz",
            "1500 W",
            "1000 W",
            "1300 W",
            "41–95 °F",
            "0–12 hours",
        )
    )
    assert not result.publishable and result.review_required


def test_de_template_keeps_unknowns_and_conflict_internal(repository):
    result = render(repository, "DE")
    assert result.required_fields_complete
    assert "DR-HSH006" not in result.table_markdown
    assert "60 Hz" not in result.table_markdown
    assert "220 V" in result.table_markdown and "Herstellerangabe" in result.table_markdown
    assert "1,25 kg" in result.table_markdown and "15,3 cm" in result.table_markdown
    assert "model" in result.unknown_fields and "frequency" in result.unknown_fields
    assert result.conflicts[0]["field_key"] == "remote_included"
    assert "remote_included" not in result.table_markdown
    assert all(row.field_key != "noise" for row in result.specification_table)


@pytest.mark.parametrize("change", ["no_source", "unknown_source", "wrong_market", "bad_unit"])
def test_invalid_repository_data_is_rejected(repository, change):
    facts = list(repository.get_facts(PRODUCT, "US"))
    target = next(index for index, fact in enumerate(facts) if fact.field_key == "voltage")
    update = {
        "no_source": {"source_ids": []},
        "unknown_source": {"source_ids": ["invented"]},
        "wrong_market": {"market": "DE"},
        "bad_unit": {"unit": "kV"},
    }[change]
    facts[target] = facts[target].model_copy(update=update)

    class Unfiltered(BaselineFactRepository):
        def get_facts(self, product_id, market):
            return self.facts

    with pytest.raises(ValueError):
        render(Unfiltered(facts, repository.get_sources()))


def test_missing_required_fact_blocks_publication(repository):
    facts = [
        fact for fact in repository.facts if not (fact.market == "US" and fact.field_key == "model")
    ]
    result = render(BaselineFactRepository(facts, repository.get_sources()))
    assert not result.required_fields_complete and "model" in result.missing_required_fields
    assert not result.publishable


def test_duplicate_fact_does_not_duplicate_rows(repository):
    duplicate = repository.facts + (repository.facts[0],)
    result = render(BaselineFactRepository(list(duplicate), repository.get_sources()))
    assert len(result.specification_table) == len(
        {row.field_key for row in result.specification_table}
    )


def test_renderer_is_reusable_for_another_product():
    facts = [
        ProductFact(
            fact_id="k1",
            product_id="kettle",
            market="DE",
            field_key="product_name",
            value="Testkessel",
            unit=None,
            status="confirmed",
            source_ids=["K"],
            verified_at="2026-10-31",
            version="1",
        ),
        ProductFact(
            fact_id="k2",
            product_id="kettle",
            market="DE",
            field_key="model",
            value="K-1",
            unit=None,
            status="confirmed",
            source_ids=["K"],
            verified_at="2026-10-31",
            version="1",
        ),
    ]
    result = render_specifications(
        BaselineFactRepository(facts, {"K": "https://example.test"}),
        product_id="kettle",
        market="DE",
        template_id="generic_de_v1",
    )
    assert result.required_fields_complete and "DREO" not in result.table_markdown


def test_legacy_t1_keeps_raw_omission_and_adds_model_only_to_specs(repository):
    path = ROOT / "docs/product_validation/runs/20261031T034918214674Z/T1/raw_output.txt"
    raw = path.read_text(encoding="utf-8")
    parsed = import_round1_copy(raw)
    assert "DR-HSH006" not in parsed.marketing_copy
    final = assemble_product_content(
        repository, product_id=PRODUCT, market="US", template_id="heater_us_v1", marketing=parsed
    )
    assert "DR-HSH006" in final.final_assembled_content
    assert "DR-HSH006" not in final.marketing_copy
    assert final.validation_result["automatic_pass"]
    assert path.read_text(encoding="utf-8") == raw


def test_validator_detects_tampered_spec_value_and_missing_assembled_row(repository):
    raw = (
        ROOT / "docs/product_validation/runs/20261031T034918214674Z/T1/raw_output.txt"
    ).read_text(encoding="utf-8")
    parsed = import_round1_copy(raw)
    final = assemble_product_content(
        repository, product_id=PRODUCT, market="US", template_id="heater_us_v1", marketing=parsed
    )
    specs = final.rendered_specifications.model_copy(deep=True)
    next(row for row in specs.specification_table if row.field_key == "voltage").value = "230"
    validation = validate_final_content(repository, specs, parsed.marketing_copy, parsed)
    assert "specification_fact_mismatch:voltage" in validation["errors"]
    assert "assembled_missing_field:model" in validation["errors"]


def test_market_template_mismatch_is_rejected(repository):
    with pytest.raises(ValueError):
        render_specifications(
            repository, product_id=PRODUCT, market="DE", template_id="heater_us_v1"
        )


def test_validator_rejects_display_only_tampering(repository):
    raw = (
        ROOT / "docs/product_validation/runs/20261031T034918214674Z/T1/raw_output.txt"
    ).read_text(encoding="utf-8")
    parsed = import_round1_copy(raw)
    final = assemble_product_content(
        repository, product_id=PRODUCT, market="US", template_id="heater_us_v1", marketing=parsed
    )
    final.rendered_specifications.specification_table[1].display_value = "INVENTED-MODEL"
    result = validate_final_content(
        repository,
        final.rendered_specifications,
        final.final_assembled_content + " INVENTED-MODEL",
        parsed,
    )
    assert "specification_display_mismatch:model" in result["errors"]


@pytest.mark.parametrize(
    "text,should_flag",
    [
        ("Ist die Fernbedienung im Produktpaket enthalten?", False),
        ("Die Fernbedienung ist im Produktpaket enthalten.", True),
        ("CE-zertifiziert und flüsterleise.", True),
        ("Mit 230 V und 60 Hz.", True),
        ("Mit 55 Hz.", True),
        ("Mit 800 W.", True),
    ],
)
def test_marketing_question_is_not_a_promise_but_assertions_are_checked(
    repository, text, should_flag
):
    raw = (
        ROOT / "docs/product_validation/runs/20261031T034918214674Z/T4/raw_output.txt"
    ).read_text(encoding="utf-8")
    parsed = import_round1_copy(raw).model_copy(update={"marketing_copy": text})
    final = assemble_product_content(
        repository, product_id=PRODUCT, market="DE", template_id="heater_de_v1", marketing=parsed
    )
    assert bool(final.validation_result["prose_flags"]) == should_flag


@pytest.mark.parametrize("status,field", [("unknown", "model"), ("conflicting", "remote_included")])
def test_unknown_and_conflict_cannot_hide_a_definite_value(repository, status, field):
    facts = [
        fact.model_copy(update={"value": "made-up"})
        if fact.market == "DE" and fact.field_key == field
        else fact
        for fact in repository.facts
    ]
    with pytest.raises(ValueError):
        render(BaselineFactRepository(facts, repository.get_sources()), "DE")


def test_all_six_legacy_results_assemble_without_network(repository, monkeypatch):
    import socket

    def deny(*args, **kwargs):
        raise AssertionError("Renderer must not use network")

    monkeypatch.setattr(socket, "create_connection", deny)
    for case_id in range(1, 7):
        raw = (
            ROOT / f"docs/product_validation/runs/20261031T034918214674Z/T{case_id}/raw_output.txt"
        ).read_text(encoding="utf-8")
        parsed = import_round1_copy(raw)
        final = assemble_product_content(
            repository,
            product_id=PRODUCT,
            market=parsed.market,
            template_id=f"heater_{parsed.market.lower()}_v1",
            marketing=parsed,
        )
        assert final.validation_result["automatic_pass"]


def test_assembled_source_line_is_independently_checked(repository):
    raw = (
        ROOT / "docs/product_validation/runs/20261031T034918214674Z/T1/raw_output.txt"
    ).read_text(encoding="utf-8")
    parsed = import_round1_copy(raw)
    final = assemble_product_content(
        repository, product_id=PRODUCT, market="US", template_id="heater_us_v1", marketing=parsed
    )
    tampered = final.final_assembled_content.replace("| S03, S04 |", "| INVENTED |")
    result = validate_final_content(repository, final.rendered_specifications, tampered, parsed)
    assert "assembled_specification_row_mismatch:model" in result["errors"]
