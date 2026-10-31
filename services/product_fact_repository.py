"""File-baseline adapter for the approved test. Future DB adapter uses the same protocol."""

import hashlib
import json
from pathlib import Path

from services.specification_renderer import ProductFact

UNIT_SUFFIXES = {
    "voltage": ("V AC", "V"),
    "frequency": ("Hz",),
    "rated_power": ("W",),
    "temperature_range": ("°F", "°C"),
    "timer": ("hours",),
    "diameter": ("cm",),
    "weight": ("kg",),
}


class BaselineFactRepository:
    def __init__(self, facts: list[ProductFact], sources: dict[str, str]):
        self.facts = tuple(facts)
        self.sources = dict(sources)

    def get_facts(self, product_id: str, market: str):
        return [
            fact for fact in self.facts if fact.product_id == product_id and fact.market == market
        ]

    def get_sources(self):
        return dict(self.sources)


def load_dreo_baseline(fixture_path: Path, baseline_path: Path) -> BaselineFactRepository:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    if digest != fixture["baseline_sha256"]:
        raise ValueError("商品事实基线已变化，必须人工重新核对夹具。")
    product_id = "DREO-CERAMIC-HEATER-316"
    facts = []
    for market, fields in fixture["facts"].items():
        name_case = next(case for case in fixture["cases"] if case["market"] == market)
        fields = {
            "product_name": {
                "value": name_case["product_name"],
                "status": "confirmed",
                "source_ids": ["S02" if market == "US" else "S05"],
            },
            **fields,
        }
        for key, entry in fields.items():
            value, unit = entry["value"], None
            if value is not None:
                for suffix in UNIT_SUFFIXES.get(key, ()):
                    if value.endswith(" " + suffix):
                        value, unit = value[: -(len(suffix) + 1)], suffix
                        break
            status = entry["status"]
            if market == "DE" and status == "confirmed":
                status = "confirmed_as_listed"
            facts.append(
                ProductFact(
                    fact_id=f"{product_id}:{market}:{key}",
                    product_id=product_id,
                    market=market,
                    field_key=key,
                    value=value,
                    unit=unit,
                    status=status,
                    source_ids=entry["source_ids"],
                    verified_at="2026-10-31",
                    version=digest,
                    source_locations=entry.get("source_locations", []),
                )
            )
    return BaselineFactRepository(facts, fixture["sources"])
