"""Generic field registry and deterministic data-quality assessment.

This layer never invents values. It proposes mappings and leaves ambiguous or
unknown columns available to the caller as custom fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FieldDefinition:
    field_key: str
    display_name: str
    business_domain: str
    data_type: str
    aliases: tuple[str, ...] = ()
    supported_operations: tuple[str, ...] = ()


FIELD_REGISTRY: tuple[FieldDefinition, ...] = (
    FieldDefinition(
        "review_id", "评价编号", "customer_feedback", "string", ("id", "reviewid", "review number")
    ),
    FieldDefinition(
        "review_text",
        "评价正文",
        "customer_feedback",
        "string",
        (
            "review",
            "comment",
            "content",
            "feedback",
            "text",
            "评价",
            "评价内容",
            "评论",
            "评论内容",
        ),
        ("text_analysis",),
    ),
    FieldDefinition(
        "review_date",
        "评价日期",
        "customer_feedback",
        "date",
        ("date", "published_at", "created_at", "日期", "评价日期"),
        ("time_trend",),
    ),
    FieldDefinition(
        "sku",
        "SKU",
        "customer_feedback",
        "string",
        ("product_sku", "product_model", "商品编码", "产品型号"),
    ),
    FieldDefinition(
        "market",
        "市场",
        "customer_feedback",
        "string",
        ("country", "marketplace", "region", "市场", "国家", "地区"),
        ("market_comparison",),
    ),
    FieldDefinition(
        "rating",
        "评分",
        "customer_feedback",
        "integer",
        ("score", "stars", "star_rating", "评分", "星级"),
        ("rating_statistics",),
    ),
    FieldDefinition(
        "batch",
        "导入批次",
        "customer_feedback",
        "string",
        ("batch_id", "import_batch", "批次", "批次号"),
    ),
    FieldDefinition(
        "supplier",
        "供应商",
        "supplier_quotation",
        "string",
        ("supplier_name", "supplier name", "vendor", "seller", "供应商", "供应商名称"),
    ),
    FieldDefinition(
        "unit_price",
        "报价",
        "supplier_quotation",
        "decimal",
        (
            "quotation_price",
            "price",
            "unit cost",
            "unit price",
            "unit price range",
            "listed price",
            "价格",
            "报价",
            "单价",
        ),
    ),
    FieldDefinition(
        "currency",
        "币种",
        "supplier_quotation",
        "currency",
        ("currency_code", "ccy", "币种", "货币"),
    ),
    FieldDefinition(
        "moq",
        "最小起订量",
        "supplier_quotation",
        "integer",
        ("minimum_order_quantity", "min order", "起订量", "最小起订量"),
    ),
    FieldDefinition(
        "lead_time_days",
        "交期天数",
        "supplier_quotation",
        "integer",
        ("lead_time", "lead time", "delivery_days", "production_lead_time", "交期", "交货期"),
    ),
    FieldDefinition(
        "payment_terms",
        "付款条件",
        "supplier_quotation",
        "string",
        ("payment", "payment_term", "付款条件"),
    ),
    FieldDefinition(
        "quality_note",
        "质量备注",
        "supplier_quotation",
        "string",
        ("quality", "remarks", "note", "质量备注"),
    ),
    FieldDefinition(
        "product_name",
        "产品名称",
        "supplier_quotation",
        "string",
        ("product", "product name", "商品名称", "产品"),
    ),
    FieldDefinition(
        "product_sku",
        "产品型号",
        "supplier_quotation",
        "string",
        ("model", "product model", "sku", "product sku", "型号", "产品型号"),
    ),
    FieldDefinition(
        "incoterms",
        "贸易条款",
        "supplier_quotation",
        "string",
        ("incoterm", "terms of delivery", "贸易条款"),
    ),
    FieldDefinition(
        "shipping_cost",
        "运费",
        "supplier_quotation",
        "decimal",
        ("freight", "shipping", "freight cost", "运费"),
    ),
    FieldDefinition(
        "quote_date",
        "报价日期",
        "supplier_quotation",
        "date",
        ("quotation date", "quoted at", "报价日期"),
    ),
)


def normalize_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().casefold())


def _definitions(domain: str | None = None) -> list[FieldDefinition]:
    return [item for item in FIELD_REGISTRY if domain is None or item.business_domain == domain]


def suggest_column_mapping(columns: list[str], *, domain: str) -> dict[str, dict[str, Any]]:
    """Return deterministic suggestions; unknown columns are never discarded."""
    aliases: dict[str, tuple[str, str]] = {}
    for definition in _definitions(domain):
        for alias in (definition.field_key, *definition.aliases):
            aliases[normalize_field_name(alias)] = (
                definition.field_key,
                "direct" if alias == definition.field_key else "alias",
            )
    result: dict[str, dict[str, Any]] = {}
    for original in columns:
        match = aliases.get(normalize_field_name(original))
        if match:
            canonical, method = match
            result[original] = {
                "canonical_field": canonical,
                "confidence": 1.0 if method == "direct" else 0.9,
                "mapping_method": method,
                "mapping_status": "suggested",
                "user_confirmed": False,
            }
        else:
            result[original] = {
                "canonical_field": None,
                "confidence": 0.0,
                "mapping_method": "unknown",
                "mapping_status": "custom_field",
                "user_confirmed": False,
            }
    return result


def assess_readiness(*, domain: str, mapped_fields: set[str], row_count: int) -> dict[str, Any]:
    """Assess readiness per operation instead of rejecting an entire file."""
    if row_count <= 0:
        return {"import_status": "PARTIAL", "operations": {}, "reason": "no_data_rows"}
    requirements = {
        "customer_feedback": {
            "text_analysis": {"review_text"},
            "time_trend": {"review_date"},
            "market_comparison": {"market"},
            "rating_statistics": {"rating"},
        },
        "supplier_quotation": {
            "price_comparison": {"supplier", "unit_price", "currency"},
            "lead_time_comparison": {"supplier", "lead_time_days"},
        },
    }[domain]
    operations = {name: required <= mapped_fields for name, required in requirements.items()}
    return {
        "import_status": "IMPORTABLE",
        "operations": operations,
        "ready_operations": [name for name, ready in operations.items() if ready],
    }
