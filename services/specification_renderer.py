"""Deterministic, market-scoped specifications. No model or database writes."""

import html
from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

FactStatus = Literal[
    "confirmed",
    "confirmed_as_listed",
    "unknown",
    "conflicting",
    "official_marketing_claim_test_method_unknown",
]


class ProductFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    fact_id: str
    product_id: str
    market: Literal["US", "DE"]
    field_key: str
    value: str | None
    unit: str | None
    status: FactStatus
    source_ids: list[str]
    verified_at: str | None
    version: str | None
    evidence_ids: list[str] = Field(default_factory=list)
    source_locations: list[str] = Field(default_factory=list)


class ProductFactRepository(Protocol):
    def get_facts(self, product_id: str, market: str) -> Sequence[ProductFact]: ...
    def get_sources(self) -> dict[str, str]: ...


class SpecificationRow(BaseModel):
    field_key: str
    label: str
    value: str
    unit: str | None
    display_value: str
    status: FactStatus
    source_ids: list[str]
    fact_id: str
    version: str
    verified_at: str
    evidence_ids: list[str]
    attribution: str


class RenderedSpecifications(BaseModel):
    product_id: str
    market: str
    language: str
    template_id: str
    specification_table: list[SpecificationRow]
    internal_warnings: list[str]
    conflicts: list[dict]
    unknown_fields: list[str]
    missing_required_fields: list[str]
    source_ids: list[str]
    required_fields_complete: bool
    review_required: bool = True
    publishable: bool = False
    table_markdown: str


LABELS = {
    "product_name": ("Product Name", "Produktname"),
    "model": ("Model", "Modell"),
    "voltage": ("Input Voltage", "Eingangsspannung"),
    "frequency": ("Frequency", "Frequenz"),
    "rated_power": ("Rated Power", "Nennleistung"),
    "heating_technology": ("Heating Technology", "Heiztechnologie"),
    "heat_levels": ("Heating Levels", "Heizstufen"),
    "heat_level_count": ("Heating Levels", "Heizstufen"),
    "temperature_range": ("Temperature Range", "Temperaturbereich"),
    "timer": ("Timer", "Timer"),
    "diameter": ("Diameter", "Durchmesser"),
    "weight": ("Net Weight", "Gewicht"),
    "capacity": ("Capacity", "Fassungsvermögen"),
    "material": ("Material", "Material"),
}
UNITS = {
    "voltage": {"V", "V AC"},
    "frequency": {"Hz"},
    "rated_power": {"W"},
    "temperature_range": {"°F", "°C"},
    "timer": {"hours"},
    "diameter": {"cm"},
    "weight": {"kg"},
    "capacity": {"L", "ml"},
}
TEMPLATES = {
    "heater_us_v1": (
        "US",
        [
            "product_name",
            "model",
            "voltage",
            "frequency",
            "rated_power",
            "heating_technology",
            "heat_levels",
            "temperature_range",
            "timer",
        ],
    ),
    "heater_de_v1": (
        "DE",
        [
            "product_name",
            "voltage",
            "rated_power",
            "heating_technology",
            "heat_level_count",
            "timer",
            "diameter",
            "weight",
        ],
    ),
    "generic_us_v1": ("US", ["product_name", "model"]),
    "generic_de_v1": ("DE", ["product_name", "model"]),
}


def _cell(text: str) -> str:
    return html.escape(text).replace("|", "&#124;").replace("\n", " ")


def render_specifications(
    repository: ProductFactRepository,
    *,
    product_id: str,
    market: str,
    template_id: str,
) -> RenderedSpecifications:
    if template_id not in TEMPLATES or TEMPLATES[template_id][0] != market:
        raise ValueError("模板与目标市场不匹配。")
    required = TEMPLATES[template_id][1]
    sources = repository.get_sources()
    facts = {}
    warnings, conflicts, unknowns = [], [], []
    for fact in repository.get_facts(product_id, market):
        if fact.product_id != product_id or fact.market != market:
            raise ValueError("检索结果包含其他商品或市场，不允许渲染。")
        if not fact.source_ids or not set(fact.source_ids) <= set(sources):
            raise ValueError("事实来源缺失或未登记。")
        if not fact.version or not fact.verified_at:
            raise ValueError("事实来源版本或核验时间缺失。")
        previous = facts.get(fact.field_key)
        if previous and previous != fact:
            raise ValueError("同字段存在不一致事实，需要先登记冲突。")
        facts[fact.field_key] = fact
    if not facts:
        raise ValueError("没有当前商品和市场的事实。")
    rows = []
    order = required + [key for key in LABELS if key not in required]
    for key, fact in facts.items():
        if fact.status == "unknown":
            if fact.value is not None:
                raise ValueError("unknown事实不能包含确定值。")
            unknowns.append(key)
        elif fact.status == "conflicting":
            if fact.value is not None:
                raise ValueError("conflicting事实不得擅自确定值。")
            conflicts.append(
                {
                    "finding_type": "specification_conflict",
                    "review_status": "pending_review",
                    "fact_id": fact.fact_id,
                    "field_key": key,
                    "source_ids": fact.source_ids,
                    "source_locations": fact.source_locations,
                    "persisted": False,
                }
            )
        elif fact.status == "official_marketing_claim_test_method_unknown":
            warnings.append(f"{key}：制造商页面声明，测试方法未核实；默认不进入固定规格表。")
    for key in order:
        fact = facts.get(key)
        if not fact or fact.status not in {"confirmed", "confirmed_as_listed"}:
            continue
        if fact.value is None or not fact.value.strip():
            raise ValueError("已确认事实不能为空。")
        if key in UNITS and fact.unit not in UNITS[key]:
            raise ValueError(f"{key}的单位无效。")
        value = fact.value
        unit = fact.unit
        if market == "DE":
            import re

            value = re.sub(r"(?<=\d)\.(?=\d)", ",", value)
        display_unit = "Stunden" if market == "DE" and unit == "hours" else unit
        display = value + (" " + display_unit if display_unit else "")
        attribution = ""
        if fact.status == "confirmed_as_listed":
            attribution = "Manufacturer listing" if market == "US" else "Herstellerangabe"
        rows.append(
            SpecificationRow(
                field_key=key,
                label=LABELS[key][0 if market == "US" else 1],
                value=fact.value,
                unit=unit,
                display_value=display,
                status=fact.status,
                source_ids=fact.source_ids,
                fact_id=fact.fact_id,
                version=fact.version,
                verified_at=fact.verified_at,
                evidence_ids=fact.evidence_ids,
                attribution=attribution,
            )
        )
    present = {row.field_key for row in rows}
    missing = [key for key in required if key not in present]
    headings = ("Field", "Value", "Source") if market == "US" else ("Merkmal", "Wert", "Quelle")
    table = ["| " + " | ".join(headings) + " |", "|---|---|---|"]
    table.extend(
        "| "
        + " | ".join(
            _cell(value)
            for value in (
                row.label,
                row.display_value + (f" ({row.attribution})" if row.attribution else ""),
                ", ".join(row.source_ids),
            )
        )
        + " |"
        for row in rows
    )
    return RenderedSpecifications(
        product_id=product_id,
        market=market,
        language="en-US" if market == "US" else "de-DE",
        template_id=template_id,
        specification_table=rows,
        internal_warnings=warnings,
        conflicts=conflicts,
        unknown_fields=sorted(unknowns),
        missing_required_fields=missing,
        source_ids=sorted({source for row in rows for source in row.source_ids}),
        required_fields_complete=not missing,
        table_markdown="\n".join(table),
    )
