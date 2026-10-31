import csv
import io
import json

import pytest

from services.evaluation_data import classification_metrics, convert_amazon_jsonl


def convert(items, **kwargs):
    return convert_amazon_jsonl(
        "\n".join(json.dumps(x) for x in items).encode(),
        source_url="https://example.test/original",
        license_reference="verified by operator",
        market="US",
        batch="public evaluation",
        **kwargs,
    )


def test_public_adapter_retains_ids_without_invented_links_or_personal_fields():
    record = {
        "text": "Box arrived crushed",
        "rating": 2.0,
        "timestamp": 1704067200000,
        "parent_asin": "A1",
        "user_id": "private-user",
        "images": ["private-image"],
    }
    raw, meta = convert([record, record])
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert len(rows) == 1 and meta["duplicate_count"] == 1
    assert rows[0]["date"] == "2024-01-01"
    assert rows[0]["supplier"] == rows[0]["production_batch"] == rows[0]["order_id"] == ""
    assert "private-user" not in raw.decode("utf-8-sig")
    assert convert([record])[0] == raw
    assert meta["market_is_test_configuration"]


@pytest.mark.parametrize("bad", [{}, {"text": "ok", "rating": 6}, {"text": "x"}])
def test_bad_public_records_do_not_silently_disappear(bad):
    with pytest.raises(ValueError, match="行号"):
        convert([bad])


def test_metrics_compare_same_sample_with_different_label_counts():
    result = classification_metrics(
        {"a": ["packaging"], "b": ["delivery"]}, {"a": ["packaging", "delivery"], "b": ["delivery"]}
    )
    assert result["sample_size"] == 2 and result["micro_recall"] == 1
    assert result["micro_precision"] == pytest.approx(2 / 3)
    assert result["exact_match"] == 0.5
    with pytest.raises(ValueError, match="不一致"):
        classification_metrics({"a": ["packaging"]}, {})
