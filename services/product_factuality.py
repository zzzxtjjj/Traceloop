"""Independent, bounded Step 2 checks. Semantic sentence review remains human."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError


class ProductFactClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    field: StrictStr = Field(min_length=1)
    value: StrictStr | None
    market: Literal["US", "DE"]
    status: Literal[
        "confirmed", "unknown", "conflicting", "official_marketing_claim_test_method_unknown"
    ]
    source_ids: list[StrictStr] = Field(min_length=1)


class ProductContentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    market: Literal["US", "DE"]
    language: Literal["en-US", "de-DE"]
    product_name: StrictStr = Field(min_length=1)
    generated_copy: StrictStr = Field(min_length=1)
    claims: list[ProductFactClaim] = Field(min_length=1)
    unknown_fields: list[StrictStr]
    conflicts: list[StrictStr]
    warnings: list[StrictStr]


def normalize(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.casefold().replace("–", "-").replace("—", "-").replace("−", "-")
    value = re.sub(r"(?<=\d),(?=\d)", ".", value)
    return re.sub(r"\s+", "", value)


def evaluate_result(raw, case: dict, fixture: dict) -> dict:
    errors = []
    try:
        output = (
            ProductContentResult.model_validate_json(raw)
            if isinstance(raw, str)
            else ProductContentResult.model_validate(raw)
        )
    except ValidationError as exc:
        return {
            "schema_pass": False,
            "schema_errors": exc.errors(include_input=False),
            "errors": ["invalid_schema"],
            "automated_pass": False,
            "human_review_status": "pending",
            "sentences": [],
            "critical_correct": 0,
            "critical_total": sum(
                fixture["facts"][case["market"]][key]["status"] == "confirmed"
                for key in case["required_fields"]
            ),
            "unknown_correct": 0,
            "unknown_total": sum(
                fixture["facts"][case["market"]][key]["status"] == "unknown"
                for key in case["required_fields"]
            ),
            "conflict_correct": 0,
            "conflict_total": sum(
                fixture["facts"][case["market"]][key]["status"] == "conflicting"
                for key in case["required_fields"]
            ),
            "unsupported_claims_detected": [],
        }
    if output.market != case["market"] or output.language != case["language"]:
        errors.append("market_or_language_mismatch")
    if output.product_name != case["product_name"]:
        errors.append("product_identity_mismatch")
    expected = fixture["facts"][case["market"]]
    claims = {}
    unsupported = []
    for claim in output.claims:
        if claim.field in claims:
            errors.append(f"duplicate_field:{claim.field}")
        claims[claim.field] = claim
        fact = expected.get(claim.field)
        if not fact:
            unsupported.append(f"unregistered_field:{claim.field}")
            continue
        if claim.market != case["market"]:
            unsupported.append(f"cross_market_claim:{claim.field}")
        if not set(claim.source_ids) <= set(fact["source_ids"]):
            unsupported.append(f"invalid_source:{claim.field}")
        if claim.status != fact["status"] or normalize(claim.value) != normalize(fact["value"]):
            unsupported.append(f"fact_mismatch:{claim.field}")
    counts = {"critical": [0, 0], "unknown": [0, 0], "conflict": [0, 0]}
    for field in case["required_fields"]:
        fact = expected[field]
        kind = {"confirmed": "critical", "unknown": "unknown", "conflicting": "conflict"}.get(
            fact["status"]
        )
        claim = claims.get(field)
        valid = bool(
            claim
            and claim.market == case["market"]
            and claim.status == fact["status"]
            and normalize(claim.value) == normalize(fact["value"])
            and set(claim.source_ids) <= set(fact["source_ids"])
        )
        if kind:
            counts[kind][1] += 1
        if kind == "unknown":
            valid = valid and field in output.unknown_fields
        if kind == "conflict":
            conflict_text = " ".join(output.conflicts)
            valid = valid and all(
                part in conflict_text
                for part in (
                    "IoT model without remote control",
                    "1 x Fernbedienung",
                    "S05",
                )
            )
        if kind and valid:
            counts[kind][0] += 1
        if not valid:
            errors.append(f"required_fact_failed:{field}")
    copy = output.generated_copy
    if case["market"] == "DE":
        for pattern in [
            r"120\s*(?:v|volt)",
            r"(?:50|60)\s*(?:hz|hertz)",
            r"DR-HSH006[A]?",
            r"230\s*(?:v|volt)",
            r"220\s*[-–]\s*240",
            r"41\s*[-–]\s*95",
            r"(?:1000|1300)\s*(?:w|watt)",
        ]:
            if re.search(pattern, copy, re.I):
                unsupported.append("copy_cross_market_or_unknown:" + pattern)
    if re.search(r"\b316S\b", copy, re.I):
        unsupported.append("copy_wrong_product_316S")
    for pattern in [
        r"CE[- ](?:certified|zertifiziert)",
        r"whisper[- ]quiet",
        r"flüsterleise",
        r"highly energy[- ]efficient",
        r"für jede raumgröße",
        r"every room size",
    ]:
        if re.search(pattern, copy, re.I):
            unsupported.append("copy_unsupported_marketing:" + pattern)
    # Numeric coverage is checked independently of claims; semantics still need a reviewer.
    compact = normalize(copy)
    copy_checks = {}
    if case["id"] == "T1":
        copy_checks = {
            "model": "dr-hsh006" in compact,
            "voltage": "120vac" in compact,
            "frequency": "60hz" in compact,
            "rated_power": "1500w" in compact,
            "heat_levels": all(marker in compact for marker in ("1000w", "1300w", "1500w")),
            "temperature_range": "41-95°f" in compact,
            "timer": "0-12h" in compact,
            "heating_technology": "ptc" in compact and "ceramic" in compact,
            "modes": all(marker in compact for marker in ("powerheat", "eco", "fanonly")),
            "child_lock": "childlock" in compact,
            "tip_over_protection": "tip-over" in compact and "protection" in compact,
            "overheat_protection": "overheatprotection" in compact,
            "auto_off_24h": "24" in compact
            and "optional" in compact
            and "notenabledbydefault" in compact,
        }
    if case["id"] == "T2":
        copy_checks = {
            "voltage": "220v" in compact,
            "rated_power": "1500w" in compact,
            "heating_technology": "ptc" in compact and "keramik" in compact,
            "heat_level_count": bool(re.search(r"(?:3|drei)heizstufen", compact)),
            "timer": bool(re.search(r"12(?:stunden|h)", compact)),
            "weight": "1.25kg" in compact,
            "diameter": "15.3cm" in compact,
        }
    errors.extend(
        "copy_missing_required:" + field for field, passed in copy_checks.items() if not passed
    )
    if case["id"] in {"T5", "T6"} and not output.warnings:
        errors.append("missing_rejection_warning")
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", copy):
        uncertain = re.search(
            r"unklar|widerspr|nicht bestätigt|unbekannt|unclear|conflict|unknown", sentence, re.I
        )
        if (
            case["market"] == "DE"
            and not sentence.strip().endswith("?")
            and not uncertain
            and re.search(
                r"(?:fernbedienung|remote control).{0,40}(?:enthalten|inbegriffen|included)",
                sentence,
                re.I,
            )
        ):
            unsupported.append("copy_remote_inclusion_resolved_without_evidence")
        if re.search(r"34\s*d[bB]", sentence):
            if not (
                re.search(r"DREO|hersteller|manufacturer", sentence, re.I)
                and re.search(r"unbekannt|unknown|nicht dokumentiert|nicht bekannt", sentence, re.I)
            ):
                unsupported.append("copy_noise_missing_attribution_or_unknown_test_method")
    sentences = [
        {
            "text": sentence.strip(),
            "source_ids": [],
            "review_status": "pending",
            "review_note": "需要逐句核对事实、否定语义、来源与语言质量",
        }
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", copy)
        if sentence.strip()
    ]
    return {
        "schema_pass": True,
        "errors": errors + unsupported,
        "unsupported_claims_detected": unsupported,
        "critical_correct": counts["critical"][0],
        "critical_total": counts["critical"][1],
        "unknown_correct": counts["unknown"][0],
        "unknown_total": counts["unknown"][1],
        "conflict_correct": counts["conflict"][0],
        "conflict_total": counts["conflict"][1],
        "automated_pass": not errors and not unsupported,
        "human_review_status": "pending",
        "sentences": sentences,
        "structured_output": output.model_dump(),
        "copy_required_checks": copy_checks,
    }


def aggregate_results(evaluations: list[dict]) -> dict:
    def ratio(kind):
        total = sum(item.get(f"{kind}_total", 0) for item in evaluations)
        correct = sum(item.get(f"{kind}_correct", 0) for item in evaluations)
        return {"correct": correct, "total": total, "rate": correct / total if total else None}

    return {
        "schema_pass_rate": sum(x["schema_pass"] for x in evaluations) / 6,
        "critical_fact_accuracy": ratio("critical"),
        "generated_copy_critical_coverage": {
            "correct": sum(sum(x.get("copy_required_checks", {}).values()) for x in evaluations),
            "total": 20,
            "rate": sum(sum(x.get("copy_required_checks", {}).values()) for x in evaluations) / 20,
            "limitation": "T1十三项和T2七项的规则覆盖率；语义正确性仍需逐句人工核对。",
        },
        "unknown_handling_accuracy": ratio("unknown"),
        "conflict_handling_accuracy": ratio("conflict"),
        "unsupported_claim_count_detected": sum(
            len(x.get("unsupported_claims_detected", [])) for x in evaluations
        ),
        "unsupported_claim_count_final": None,
        "copy_cross_market_flags": sum(
            "copy_cross_market" in error for x in evaluations for error in x["errors"]
        ),
        "cross_market_contamination_detected": sum(
            "cross_market" in error for x in evaluations for error in x["errors"]
        ),
        "final_status": "PARTIAL",
        "human_review_status": "pending",
        "limitation": "规则为独立筛查，不是完整语义证明；文案逐句人工复核前不判定通过。",
    }
