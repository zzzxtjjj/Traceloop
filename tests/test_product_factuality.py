import json
from pathlib import Path

import pytest

from services.product_factuality import aggregate_results, evaluate_result

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "dreo_316_step2_cases.json").read_text(encoding="utf-8")
)


def valid_output(case_id):
    case = next(case for case in FIXTURE["cases"] if case["id"] == case_id)
    facts = FIXTURE["facts"][case["market"]]
    claims = [
        {
            "field": field,
            "market": case["market"],
            **{key: facts[field][key] for key in ("value", "status", "source_ids")},
        }
        for field in case["required_fields"]
    ]
    copy = (
        "DREO Ceramic Heater 316 DR-HSH006. 120 V AC, 60 Hz, 1500 W. "
        "H1 1000 W; H2 1300 W; H3 1500 W. 41–95 °F; 0–12 hours. "
        "PTC ceramic, Power Heat, ECO, Fan Only. Child lock, tip-over and overheat protection. "
        "24-hour auto-off is optional, not enabled by default."
    )
    if case["market"] == "DE":
        copy = (
            "Heizlüfter 316: 220 V, 1500 W, PTC-Keramik, drei Heizstufen. "
            "12 Stunden Timer, Durchmesser 15,3 cm, Gewicht 1,25 kg."
        )
    return case, {
        "market": case["market"],
        "language": case["language"],
        "product_name": case["product_name"],
        "generated_copy": copy,
        "claims": claims,
        "unknown_fields": [claim["field"] for claim in claims if claim["status"] == "unknown"],
        "conflicts": [
            "remote_included: S05 specification: IoT model without remote control; "
            "S05 package list: 1 x Fernbedienung. 精确SKU需人工核验。"
        ]
        if "remote_included" in case["required_fields"]
        else [],
        "warnings": ["拒绝未经确认的参数和宣传。"],
    }


@pytest.mark.parametrize("case_id", ["T1", "T2", "T3", "T4", "T5", "T6"])
def test_expected_cases_pass_rules_but_still_require_human_review(case_id):
    case, output = valid_output(case_id)
    result = evaluate_result(output, case, FIXTURE)
    assert result["automated_pass"], result["errors"]
    assert result["human_review_status"] == "pending"
    assert all(sentence["review_status"] == "pending" for sentence in result["sentences"])


@pytest.mark.parametrize("key,value", [("claims", []), ("market", "FR"), ("warnings", "bad")])
def test_invalid_structure_is_not_success(key, value):
    case, output = valid_output("T2")
    output[key] = value
    result = evaluate_result(output, case, FIXTURE)
    assert not result["schema_pass"]


def test_bad_json_is_recorded():
    case, _ = valid_output("T1")
    assert not evaluate_result("not json", case, FIXTURE)["schema_pass"]


def test_unknown_and_sources_cannot_be_invented():
    case, output = valid_output("T3")
    output["claims"][0].update(value="DR-HSH006", status="confirmed", source_ids=["S99"])
    result = evaluate_result(output, case, FIXTURE)
    assert not result["automated_pass"]
    assert "invalid_source:model" in result["errors"]
    assert "fact_mismatch:model" in result["errors"]


def test_valid_claims_do_not_hide_pollution_in_final_copy():
    case, output = valid_output("T2")
    output["generated_copy"] += " 230 V, 60 Hz, DR-HSH006."
    result = evaluate_result(output, case, FIXTURE)
    assert result["critical_correct"] == result["critical_total"]
    assert not result["automated_pass"]
    assert any("copy_cross_market" in item for item in result["errors"])


def test_remote_conflict_needs_both_source_locations():
    case, output = valid_output("T4")
    output["conflicts"] = ["S05 remote_included unknown"]
    assert not evaluate_result(output, case, FIXTURE)["automated_pass"]
    case, output = valid_output("T4")
    output["generated_copy"] = "Eine Fernbedienung ist enthalten."
    assert not evaluate_result(output, case, FIXTURE)["automated_pass"]


def test_noise_is_not_an_independent_measurement():
    case, output = valid_output("T6")
    output["generated_copy"] += " Geräuschpegel: 34 dB."
    assert not evaluate_result(output, case, FIXTURE)["automated_pass"]
    output["generated_copy"] = "Laut Hersteller DREO 34 dB; die Testbedingungen sind unbekannt."
    assert evaluate_result(output, case, FIXTURE)["automated_pass"]


def test_marketing_and_duplicate_claims_are_detected():
    case, output = valid_output("T6")
    output["generated_copy"] += " CE certified. Whisper-quiet."
    output["claims"].append(output["claims"][0])
    result = evaluate_result(output, case, FIXTURE)
    assert "duplicate_field:certification" in result["errors"]
    assert any("copy_unsupported_marketing" in item for item in result["errors"])


def test_metrics_never_claim_unreviewed_semantic_zero():
    results = [
        evaluate_result(output, case, FIXTURE)
        for case, output in (valid_output(f"T{index}") for index in range(1, 7))
    ]
    summary = aggregate_results(results)
    assert summary["schema_pass_rate"] == 1
    assert summary["critical_fact_accuracy"]["rate"] == 1
    assert summary["unsupported_claim_count_detected"] == 0
    assert summary["unsupported_claim_count_final"] is None
    assert summary["final_status"] == "PARTIAL"


def test_remote_question_is_not_a_positive_inclusion_claim():
    case, output = valid_output("T4")
    output["generated_copy"] = "Ist die Fernbedienung enthalten? Die Quelle ist widersprüchlich."
    output["conflicts"] = ["S05: IoT model without remote control", "S05: 1 x Fernbedienung"]
    assert evaluate_result(output, case, FIXTURE)["automated_pass"]


def test_correct_model_claim_does_not_make_missing_model_in_copy_pass():
    case, output = valid_output("T1")
    output["generated_copy"] = output["generated_copy"].replace("DR-HSH006", "")
    result = evaluate_result(output, case, FIXTURE)
    assert result["critical_correct"] == result["critical_total"]
    assert not result["copy_required_checks"]["model"]
    assert "copy_missing_required:model" in result["errors"]
