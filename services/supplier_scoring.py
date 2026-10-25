from collections.abc import Iterable

from core.models import SupplierQuote
from core.schemas import QuoteRow, SupplierScore

DEFAULT_WEIGHTS = {"price": 35, "moq": 15, "lead_time": 30, "quality": 20}
RISK_KEYWORDS = {
    "认证缺失": 35,
    "未认证": 35,
    "样品未确认": 25,
    "交期不稳定": 25,
    "投诉": 20,
    "瑕疵": 15,
    "返工": 15,
    "missing certification": 35,
    "sample not confirmed": 25,
    "unstable": 20,
}


def validate_weights(weights: dict[str, int | float]) -> None:
    required = set(DEFAULT_WEIGHTS)
    if set(weights) != required:
        raise ValueError(f"权重字段必须为：{', '.join(sorted(required))}")
    if any(value < 0 or value > 100 for value in weights.values()):
        raise ValueError("每项权重必须位于 0–100。")
    if abs(sum(weights.values()) - 100) > 0.001:
        raise ValueError("四项权重之和必须为 100。")


def _lower_is_better(values: list[float]) -> list[float]:
    low, high = min(values), max(values)
    if high == low:
        return [100.0] * len(values)
    return [100 * (high - value) / (high - low) for value in values]


def _quality_score(note: str) -> tuple[float, list[str]]:
    normalized = note.casefold()
    hits = [keyword for keyword in RISK_KEYWORDS if keyword.casefold() in normalized]
    penalty = sum(RISK_KEYWORDS[keyword] for keyword in hits)
    return max(0.0, 100.0 - penalty), hits


def calculate_supplier_scores(
    quotes: Iterable[QuoteRow | SupplierQuote],
    weights: dict[str, int | float] | None = None,
) -> list[SupplierScore]:
    weights = weights or DEFAULT_WEIGHTS
    validate_weights(weights)
    quote_list = list(quotes)
    if not quote_list:
        return []

    currencies = {quote.currency.upper() for quote in quote_list}
    if len(currencies) > 1:
        raise ValueError("不同币种不能直接比较，请先统一币种。")

    price_scores = _lower_is_better([float(quote.unit_price) for quote in quote_list])
    moq_scores = _lower_is_better([float(quote.moq) for quote in quote_list])
    lead_scores = _lower_is_better([float(quote.lead_time_days) for quote in quote_list])
    results: list[SupplierScore] = []

    for index, quote in enumerate(quote_list):
        quality_score, risk_hits = _quality_score(quote.quality_note)
        total = (
            price_scores[index] * weights["price"]
            + moq_scores[index] * weights["moq"]
            + lead_scores[index] * weights["lead_time"]
            + quality_score * weights["quality"]
        ) / 100
        results.append(
            SupplierScore(
                supplier=quote.supplier,
                unit_price=float(quote.unit_price),
                currency=quote.currency,
                moq=int(quote.moq),
                lead_time_days=int(quote.lead_time_days),
                payment_terms=quote.payment_terms,
                quality_note=quote.quality_note,
                price_score=round(price_scores[index], 2),
                moq_score=round(moq_scores[index], 2),
                lead_time_score=round(lead_scores[index], 2),
                quality_score=round(quality_score, 2),
                total_score=round(total, 2),
                risk_hits=risk_hits,
            )
        )

    return sorted(results, key=lambda item: (-item.total_score, item.supplier.casefold()))

