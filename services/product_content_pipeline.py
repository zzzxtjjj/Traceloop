"""Separate dynamic prose, fixed specifications and independent review results."""

import hashlib
import html
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from services.product_factuality import ProductContentResult, evaluate_result, normalize
from services.specification_renderer import (
    FactStatus,
    ProductFactRepository,
    RenderedSpecifications,
    render_specifications,
)


class MarketingFactClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    field: str
    value: str | None
    market: Literal["US", "DE"]
    status: FactStatus
    source_ids: list[str] = Field(min_length=1)


class MarketingContentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    market: Literal["US", "DE"]
    language: Literal["en-US", "de-DE"]
    product_name: str = Field(min_length=1)
    marketing_copy: str = Field(min_length=1)
    claims: list[MarketingFactClaim]
    unknown_fields: list[str]
    conflicts: list[str]
    warnings: list[str]


class RenderedProductContent(BaseModel):
    product_id: str
    market: str
    language: str
    marketing_copy: str
    rendered_specifications: RenderedSpecifications
    final_assembled_content: str
    internal_warnings: list[str]
    conflicts: list[dict]
    unknown_fields: list[str]
    source_ids: list[str]
    required_fields_complete: bool
    review_required: bool = True
    publishable: bool = False
    validation_result: dict


def validate_final_content(
    repository: ProductFactRepository,
    specs: RenderedSpecifications,
    assembled: str,
    marketing: MarketingContentResult,
) -> dict:
    """Compare renderer output against retrieval, never against LLM claims alone."""
    facts = {fact.field_key: fact for fact in repository.get_facts(specs.product_id, specs.market)}
    source_catalog = repository.get_sources()
    errors = []
    from services.specification_renderer import LABELS, TEMPLATES

    if specs.template_id not in TEMPLATES or TEMPLATES[specs.template_id][0] != specs.market:
        return {"automatic_pass": False, "errors": ["invalid_market_template"]}
    if marketing.market != specs.market or marketing.language != specs.language:
        errors.append("marketing_market_or_language_mismatch")
    name = facts.get("product_name")
    if not name or marketing.product_name != name.value:
        errors.append("marketing_product_identity_mismatch")
    seen = set()
    for row in specs.specification_table:
        fact = facts.get(row.field_key)
        if row.field_key in seen:
            errors.append("duplicate_specification:" + row.field_key)
        seen.add(row.field_key)
        if not fact or fact.status not in {"confirmed", "confirmed_as_listed"}:
            errors.append("nonpublishable_specification:" + row.field_key)
            continue
        if (
            row.value != fact.value
            or row.unit != fact.unit
            or row.status != fact.status
            or row.fact_id != fact.fact_id
            or row.version != fact.version
        ):
            errors.append("specification_fact_mismatch:" + row.field_key)
        expected_value = fact.value or ""
        if specs.market == "DE":
            expected_value = re.sub(r"(?<=\d)\.(?=\d)", ",", expected_value)
        expected_unit = "Stunden" if specs.market == "DE" and fact.unit == "hours" else fact.unit
        expected_display = expected_value + (" " + expected_unit if expected_unit else "")
        expected_label = LABELS.get(row.field_key, ("", ""))[0 if specs.market == "US" else 1]
        if row.display_value != expected_display or row.label != expected_label:
            errors.append("specification_display_mismatch:" + row.field_key)
        if row.verified_at != fact.verified_at or row.evidence_ids != fact.evidence_ids:
            errors.append("specification_provenance_mismatch:" + row.field_key)
        if (
            not row.source_ids
            or set(row.source_ids) != set(fact.source_ids)
            or not set(row.source_ids) <= set(source_catalog)
        ):
            errors.append("specification_source_mismatch:" + row.field_key)
        if row.status == "confirmed_as_listed" and not row.attribution:
            errors.append("specification_attribution_missing:" + row.field_key)
        if row.label not in assembled or row.display_value not in assembled:
            errors.append("assembled_missing_field:" + row.field_key)
        expected_attribution = (
            ("Manufacturer listing" if specs.market == "US" else "Herstellerangabe")
            if fact.status == "confirmed_as_listed"
            else ""
        )
        expected_cells = [
            expected_label,
            expected_display + (f" ({expected_attribution})" if expected_attribution else ""),
            ", ".join(fact.source_ids),
        ]
        expected_line = (
            "| "
            + " | ".join(
                html.escape(cell).replace("|", "&#124;").replace("\n", " ")
                for cell in expected_cells
            )
            + " |"
        )
        if expected_line not in assembled:
            errors.append("assembled_specification_row_mismatch:" + row.field_key)
    required = TEMPLATES[specs.template_id][1]
    missing = [key for key in required if key not in seen]
    errors.extend("required_specification_missing:" + key for key in missing)
    for claim in marketing.claims:
        fact = facts.get(claim.field)
        if not fact or claim.market != specs.market:
            errors.append("marketing_claim_wrong_field_or_market:" + claim.field)
            continue
        expected = (fact.value + (" " + fact.unit if fact.unit else "")) if fact.value else None
        status_matches = claim.status == fact.status or (
            fact.status == "confirmed_as_listed" and claim.status == "confirmed"
        )
        if (
            normalize(claim.value) != normalize(expected)
            or not status_matches
            or not set(claim.source_ids) <= set(fact.source_ids)
        ):
            errors.append("marketing_claim_fact_mismatch:" + claim.field)
    # The final consumer-facing content is also checked for unsupported numbers and assurances.
    prose_flags = []
    # Independently inspect numerical assertions in consumer prose, not just reported claims.
    quantity_units = {"v": "V", "hz": "Hz", "w": "W", "kg": "kg", "cm": "cm"}
    for number, unit in re.findall(
        r"\b(\d+(?:[.,]\d+)?)\s*(V|Hz|W|kg|cm)\b", marketing.marketing_copy, re.I
    ):
        canonical_unit = quantity_units[unit.lower()]
        number = number.replace(",", ".")
        supported = any(
            fact.value
            and fact.status in {"confirmed", "confirmed_as_listed"}
            and re.search(r"(?<![\d.])" + re.escape(number) + r"(?![\d.])", fact.value)
            and (
                fact.unit == canonical_unit
                or (canonical_unit == "V" and fact.unit == "V AC")
                or re.search(r"\b" + re.escape(canonical_unit) + r"\b", fact.value)
            )
            for fact in facts.values()
        )
        if not supported:
            prose_flags.append(f"unsupported_numeric_quantity:{number}{canonical_unit}")
    if specs.market == "DE":
        for pattern in [
            r"DR-HSH006[A]?",
            r"\b(?:120|230)\s*(?:v|volt)",
            r"\b(?:50|60)\s*(?:hz|hertz)",
            r"220\s*[-–]\s*240",
            r"\b(?:1000|1300)\s*(?:w|watt)",
            r"41\s*[-–]\s*95",
        ]:
            if re.search(pattern, assembled, re.I):
                prose_flags.append("final_cross_market_or_unknown:" + pattern)
    # Negated/uncertain statements are preserved for manual review, not scored as assertions.
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", marketing.marketing_copy):
        hedged = re.search(
            r"not |no |nicht|kein|unbekannt|unklar|widerspr|unknown|unverified", sentence, re.I
        )
        question = sentence.rstrip().endswith("?")
        if not hedged and not question:
            for pattern in [
                r"CE[- ](?:certified|zertifiziert)",
                r"whisper[- ]quiet",
                r"flüsterleise",
                r"highly energy[- ]efficient",
                r"every room size",
                r"jede raumgröße",
                r"(?:remote control|fernbedienung).{0,40}(?:included|enthalten|inbegriffen)",
            ]:
                if re.search(pattern, sentence, re.I):
                    prose_flags.append("final_unsupported_marketing:" + pattern)
        if re.search(r"34\s*db", sentence, re.I) and not (
            re.search(r"DREO|manufacturer|Hersteller", sentence, re.I)
            and re.search(r"unknown|unbekannt|nicht bekannt|nicht dokumentiert", sentence, re.I)
        ):
            prose_flags.append("noise_missing_attribution_or_unknown_test_method")
    errors += prose_flags
    sentences = [
        {"text": sentence.strip(), "human_review_status": "pending", "source_ids": []}
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", marketing.marketing_copy)
        if sentence.strip()
    ]
    return {
        "automatic_pass": not errors,
        "errors": errors,
        "required_fields_present": len(required) - len(missing),
        "required_fields_total": len(required),
        "prose_flags": prose_flags,
        "unsupported_claim_count_detected": len(prose_flags),
        "unsupported_claim_count_final": None,
        "sentences": sentences,
        "human_review_status": "pending",
        "publishable": False,
        "limitation": "静态筛查不是自然语言语义证明，规格完整也不自动批准发布。",
    }


def evaluate_agent_output(
    marketing: MarketingContentResult,
    case: dict,
    repository: ProductFactRepository,
    product_id: str,
) -> dict:
    facts = {fact.field_key: fact for fact in repository.get_facts(product_id, case["market"])}
    claims = {claim.field: claim for claim in marketing.claims}
    errors = []
    if len(claims) != len(marketing.claims):
        errors.append("duplicate_claim_fields")
    unknown_correct = unknown_total = conflict_correct = conflict_total = 0
    if case["id"] == "T3":
        for key in ("model", "frequency", "temperature_range", "heat_level_wattages"):
            claim = claims.get(key)
            unknown_total += 1
            good = bool(
                claim
                and claim.status == "unknown"
                and claim.value is None
                and key in marketing.unknown_fields
            )
            unknown_correct += int(good)
            if not good:
                errors.append("unknown_handling_failed:" + key)
    if case["id"] in {"T4", "T6"}:
        conflict_total = 1
        claim = claims.get("remote_included")
        conflict_text = " ".join(marketing.conflicts)
        good = bool(
            claim
            and claim.status == "conflicting"
            and claim.value is None
            and all(
                part in conflict_text
                for part in ("IoT model without remote control", "1 x Fernbedienung", "S05")
            )
        )
        conflict_correct = int(good)
        if not good:
            errors.append("conflict_handling_failed:remote_included")
    if case["id"] in {"T5", "T6"} and not marketing.warnings:
        errors.append("missing_rejection_warning")
    # Fixed specs are intentionally not required in dynamic prose.
    raw_missing = []
    for field, fact in facts.items():
        if fact.status in {"confirmed", "confirmed_as_listed"} and fact.value:
            display = fact.value + (" " + fact.unit if fact.unit else "")
            if normalize(display) not in normalize(marketing.marketing_copy):
                raw_missing.append(field)
    return {
        "errors": errors,
        "unknown_correct": unknown_correct,
        "unknown_total": unknown_total,
        "conflict_correct": conflict_correct,
        "conflict_total": conflict_total,
        "raw_missing_fields": raw_missing,
        "raw_missing_note": "动态文案未出现的固定事实仅为完整性提示，不记为LLM事实错误。",
    }


def assemble_product_content(
    repository: ProductFactRepository,
    *,
    product_id: str,
    market: str,
    template_id: str,
    marketing: MarketingContentResult,
) -> RenderedProductContent:
    specs = render_specifications(
        repository, product_id=product_id, market=market, template_id=template_id
    )
    title = "Technical Specifications" if market == "US" else "Technische Daten"
    assembled = marketing.marketing_copy + "\n\n## " + title + "\n\n" + specs.table_markdown
    validation = validate_final_content(repository, specs, assembled, marketing)
    return RenderedProductContent(
        product_id=product_id,
        market=market,
        language=specs.language,
        marketing_copy=marketing.marketing_copy,
        rendered_specifications=specs,
        final_assembled_content=assembled,
        internal_warnings=specs.internal_warnings + marketing.warnings,
        conflicts=specs.conflicts,
        unknown_fields=specs.unknown_fields,
        source_ids=sorted(
            set(specs.source_ids)
            | {source for claim in marketing.claims for source in claim.source_ids}
        ),
        required_fields_complete=specs.required_fields_complete,
        validation_result=validation,
    )


def import_round1_copy(raw: str) -> MarketingContentResult:
    parsed = ProductContentResult.model_validate_json(raw)
    return MarketingContentResult(
        market=parsed.market,
        language=parsed.language,
        product_name=parsed.product_name,
        marketing_copy=parsed.generated_copy,
        claims=[MarketingFactClaim(**claim.model_dump()) for claim in parsed.claims],
        unknown_fields=parsed.unknown_fields,
        conflicts=parsed.conflicts,
        warnings=parsed.warnings,
    )


def evaluate_legacy_raw(raw, case, fixture):
    return evaluate_result(raw, case, fixture)


def content_hash(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
