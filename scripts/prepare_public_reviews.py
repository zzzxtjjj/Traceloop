"""Convert a local public Amazon JSONL sample without calling model APIs."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.evaluation_data import convert_amazon_jsonl  # noqa: E402
from services.review_service import preview_review_csv  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--license-reference", required=True)
    parser.add_argument("--market", choices=["US", "DE"], required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    if not args.source.is_file() or args.source.stat().st_size > 10_000_000:
        parser.error("请选择不超过10MB的本地JSONL样本文件。")
    try:
        csv_bytes, manifest = convert_amazon_jsonl(
            args.source.read_bytes(),
            source_url=args.source_url,
            license_reference=args.license_reference,
            market=args.market,
            batch=args.batch,
            limit=args.limit,
        )
        preview = preview_review_csv(csv_bytes)
        if not preview.is_valid:
            raise ValueError("转换结果不符合评价导入模板，请检查来源数据。")
    except ValueError as exc:
        parser.error(str(exc))
    folder = ROOT / "data" / "evaluation" / manifest["output_sha256"][:16]
    if folder.exists():
        parser.error("该转换结果目录已存在，未覆盖历史记录。")
    folder.mkdir(parents=True)
    (folder / "reviews.csv").write_bytes(csv_bytes)
    (folder / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已转换 {manifest['sample_count']} 条，结果：{folder}")
    print("本命令未调用模型。测试市场为操作者设置，不代表原评价买家所在国家。")


if __name__ == "__main__":
    main()
