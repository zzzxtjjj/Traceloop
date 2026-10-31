"""Deterministic adapters for caller-supplied, licensed public review samples."""

import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from urllib.parse import urlsplit


def convert_amazon_jsonl(
    raw: bytes,
    *,
    source_url: str,
    license_reference: str,
    market: str,
    batch: str,
    limit: int = 50,
) -> tuple[bytes, dict]:
    """Target market is an explicit test setting, not inferred buyer geography."""
    if market not in {"US", "DE"} or not batch.strip():
        raise ValueError("请选择 US/DE 测试市场并填写批次名称。")
    if not 1 <= limit <= 200 or len(raw) > 10_000_000:
        raise ValueError("仅支持最多200条、10MB以内的样本文件。")
    if urlsplit(source_url).scheme != "https" or not license_reference.strip():
        raise ValueError("请提供原始 HTTPS 来源和已核对的许可引用。")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("文件必须为 UTF-8 JSONL。") from exc
    rows = []
    seen = set()
    errors = []
    duplicates = 0
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            review = item["text"]
            asin = item.get("parent_asin") or item.get("asin")
            rating = float(item["rating"])
            timestamp = item["timestamp"]
            if (
                not isinstance(review, str)
                or len(review.strip()) < 2
                or len(review.strip()) > 5000
                or not isinstance(asin, str)
                or not asin.strip()
                or not rating.is_integer()
                or not 1 <= rating <= 5
                or isinstance(timestamp, bool)
                or not isinstance(timestamp, (int, float))
            ):
                raise ValueError("invalid record")
            day = datetime.fromtimestamp(timestamp / 1000, tz=UTC).date().isoformat()
            identity = json.dumps([asin, timestamp, review.strip(), rating], ensure_ascii=False)
            identifier = "AMZ-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
            if identifier in seen:
                duplicates += 1
                continue
            seen.add(identifier)
            rows.append(
                {
                    "review_id": identifier,
                    "batch": batch.strip(),
                    "rating": int(rating),
                    "date": day,
                    "sku": "AMAZON:" + asin.strip(),
                    "market": market,
                    "review_text": review.strip(),
                    "order_id": "",
                    "production_batch": "",
                    "supplier": "",
                }
            )
        except (ValueError, TypeError, KeyError, OverflowError, OSError):
            errors.append(number)
        if len(rows) >= limit:
            break
    if errors:
        raise ValueError("公开评价字段无效，JSONL 行号：" + ",".join(map(str, errors[:20])))
    if not rows:
        raise ValueError("没有可转换的评价记录。")
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    converted = out.getvalue().encode("utf-8-sig")
    manifest = {
        "adapter": "amazon_reviews_jsonl_v1",
        "source_url": source_url,
        "license_reference": license_reference.strip(),
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "output_sha256": hashlib.sha256(converted).hexdigest(),
        "sample_count": len(rows),
        "duplicate_count": duplicates,
        "sampling": "first valid unique records, not a representative random sample",
        "target_market": market,
        "market_is_test_configuration": True,
        "removed_fields": ["user_id", "reviewer_name", "images"],
        "unknown_links": ["order_id", "production_batch", "supplier"],
        "limitation": "源商品ID不等于内部SKU；评分不是问题主题标签。许可由操作者核对。",
    }
    return converted, manifest


def classification_metrics(expected: dict[str, list[str]], predicted: dict[str, list[str]]) -> dict:
    """Exact-set and micro scores; unmatched IDs never silently disappear."""
    if not expected or any(not key for key in expected):
        raise ValueError("需要包含评价ID的人工标注测试集。")
    if set(expected) != set(predicted):
        raise ValueError("预测与人工标注的评价ID不一致，不能计算完整测试集指标。")
    for labels in [*expected.values(), *predicted.values()]:
        if not isinstance(labels, list) or any(
            not isinstance(label, str) or not label.strip() for label in labels
        ):
            raise ValueError("主题标签必须是有效字符串列表。")
    tp = fp = fn = exact = 0
    for key, truth in expected.items():
        actual, target = set(predicted[key]), set(truth)
        tp += len(actual & target)
        fp += len(actual - target)
        fn += len(target - actual)
        exact += actual == target
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {
        "sample_size": len(expected),
        "exact_match": exact / len(expected),
        "micro_precision": precision,
        "micro_recall": recall,
        "micro_f1": f1,
        "true_positive_labels": tp,
        "false_positive_labels": fp,
        "false_negative_labels": fn,
        "limitation": "仅评价当前人工标注样本；不代表真实故障率或改进因果。",
    }
