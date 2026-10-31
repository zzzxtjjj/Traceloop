"""Step 2 only: six bounded factuality calls, raw evidence and independent checks."""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from core.config import settings  # noqa: E402
from core.errors import TradeLoopError  # noqa: E402
from core.models import AiRun, Base, Project  # noqa: E402
from services.ai_service import run_structured_model  # noqa: E402
from services.model_provider import OpenAICompatibleProvider  # noqa: E402
from services.model_readiness import check_model_readiness, validate_model_input_budget  # noqa: E402
from services.product_factuality import (  # noqa: E402
    ProductContentResult,
    aggregate_results,
    evaluate_result,
)

PROMPT_VERSION = "dreo_step2_factuality_v1"
DOCS = ROOT / "docs" / "product_validation"
FIXTURE = ROOT / "tests" / "fixtures" / "dreo_316_step2_cases.json"


class RecordingProvider:
    """Record provider content without logging headers, keys or session configuration."""

    max_attempts = 1

    def __init__(self, provider):
        self.provider = provider
        self.model_name = provider.model_name
        self.raw = None
        self.calls = 0

    def generate(self, **kwargs):
        self.calls += 1
        self.raw = self.provider.generate(**kwargs)
        return self.raw


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Authorize up to six paid primary calls"
    )
    args = parser.parse_args()
    if not args.live:
        print("离线预检模式：未请求模型。真实六项测试需手动添加 --live。")
        return 0
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    baseline = (DOCS / "PRODUCT_FACTS.md").read_bytes()
    baseline_hash = hashlib.sha256(baseline).hexdigest()
    if baseline_hash != fixture["baseline_sha256"]:
        print("事实基线哈希不符，已停止，未请求模型。")
        return 1
    readiness = check_model_readiness(settings)
    if not readiness.configured:
        print("BLOCKED：配置不完整，未请求模型；请只在本机填写密钥。")
        return 1
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    folder = DOCS / "runs" / stamp
    folder.mkdir(parents=True, exist_ok=False)
    template = (ROOT / "prompts" / f"{PROMPT_VERSION}.txt").read_text(encoding="utf-8")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    records = []
    # Existing model client and AiRun service, no repair calls and no network retries.
    provider = RecordingProvider(OpenAICompatibleProvider.from_settings())
    with Session(engine, expire_on_commit=False) as db:
        project = Project(
            name="DREO Step2 isolated validation",
            product_name=fixture["product_family"],
            access_code_hash="unused",
            markets_json='["US","DE"]',
        )
        db.add(project)
        db.flush()
        for case in fixture["cases"]:
            provider.raw = None
            prompt = template + "\nPRODUCT_FACTS.md:\n" + baseline.decode("utf-8")
            prompt += "\nNormalized facts and source IDs:\n" + json.dumps(
                {"facts": fixture["facts"], "sources": fixture["sources"]}, ensure_ascii=False
            )
            prompt += "\nCurrent independent test:\n" + json.dumps(case, ensure_ascii=False)
            validate_model_input_budget(prompt=prompt, review_count=0)
            case_folder = folder / case["id"]
            case_folder.mkdir()
            save_json(
                case_folder / "input.json",
                {
                    "case": case,
                    "prompt": prompt,
                    "prompt_version": PROMPT_VERSION,
                    "baseline_sha256": baseline_hash,
                },
            )
            started = datetime.now(UTC).isoformat()
            error = None
            try:
                run_structured_model(
                    project_id=project.id,
                    run_type=f"step2_{case['id']}",
                    prompt_version=PROMPT_VERSION,
                    prompt=prompt,
                    evidence_ids=[],
                    output_model=ProductContentResult,
                    provider=provider,
                    session=db,
                )
            except TradeLoopError as exc:
                error = {"code": exc.code, "type": type(exc).__name__}
            except Exception as exc:
                error = {"code": "UNEXPECTED_LOCAL_ERROR", "type": type(exc).__name__}
            raw_text = (
                provider.raw
                if isinstance(provider.raw, str)
                else json.dumps(provider.raw, ensure_ascii=False)
            )
            (case_folder / "raw_output.txt").write_text(raw_text, encoding="utf-8")
            evaluation = evaluate_result(provider.raw, case, fixture)
            if error:
                evaluation["errors"].append(error["code"])
                evaluation["automated_pass"] = False
            run = db.scalar(select(AiRun).where(AiRun.run_type == f"step2_{case['id']}"))
            record = {
                "id": case["id"],
                "market": case["market"],
                "request": case["request"],
                "started_at_utc": started,
                "model": provider.model_name,
                "prompt_version": PROMPT_VERSION,
                "error": error,
                "raw_sha256": hashlib.sha256(raw_text.encode()).hexdigest(),
                "ai_run": {
                    key: getattr(run, key)
                    for key in (
                        "id",
                        "model",
                        "prompt_version",
                        "input_hash",
                        "status",
                        "latency_ms",
                        "error_code",
                    )
                },
                "evaluation": evaluation,
            }
            save_json(case_folder / "result.json", record)
            records.append(record)
            db.commit()
            print(
                f"{case['id']}: schema={evaluation['schema_pass']} "
                f"auto={evaluation['automated_pass']} errors={len(evaluation['errors'])}",
                flush=True,
            )
    summary = aggregate_results([record["evaluation"] for record in records])
    if any(not record["evaluation"]["automated_pass"] for record in records):
        summary["final_status"] = "FAILED"
    result = {
        "git_head": head,
        "worktree": "dirty; existing changes preserved",
        "model": provider.model_name,
        "live": True,
        "provider_calls": provider.calls,
        "network_retries": 0,
        "baseline_sha256": baseline_hash,
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "database": "isolated in-memory; AiRun exported; business DB untouched",
        "summary": summary,
        "cases": records,
    }
    save_json(folder / "summary.json", result)
    lines = [
        "# Step 2 DeepSeek 商品事实幻觉检测报告",
        "",
        f"执行时间：{stamp}；模型：{provider.model_name}；真实请求：{provider.calls}次；重试：0。",
        "",
        f"Git HEAD：`{head}`，包含已有未提交修改，未切换或重置分支。",
        f"事实基线SHA-256：`{baseline_hash}`。原始事实文件未修改。",
        "Step 1 通过依据为本次用户执行指令；归档文档中的旧待验收状态保留。",
        "",
        "## 结果概览",
        "",
        f"当前状态：**{summary['final_status']}**。",
        "本报告不是Step 3；未进行反馈修订、评价导入、前端修改或业务数据库迁移。",
        "结构合法不代表文案无幻觉；未审核句子的最终无依据事实数仍为待定。",
        "",
        "```json",
        json.dumps(summary, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 六项输入和实际结果",
        "",
    ]
    for record in records:
        case_id = record["id"]
        relative = f"runs/{stamp}/{case_id}"
        lines += [
            f"### {case_id}",
            "",
            record["request"],
            "",
            f"- [完整输入]({relative}/input.json)",
            f"- [原始模型输出]({relative}/raw_output.txt)",
            f"- [结构化输出、逐句待审与自动错误]({relative}/result.json)",
            f"- 自动错误：`{json.dumps(record['evaluation']['errors'], ensure_ascii=False)}`",
            "- 人工审核：pending。需逐句匹配来源，检查否定语义、语言、功能和营销限定。",
            "",
        ]
    lines += [
        "## 自动测试与人工验收",
        "",
        "实际pytest/Ruff命令与结果在本轮执行后补记；本脚本不冒充已运行自动测试。",
        "逐句审核入口为每个result.json的evaluation.sentences；source_ids初始为空，须人工填写。",
        "只有人工确认所有关键规格、无依据事实为0、未知和冲突保留、无跨市场混用后才能建议通过。",
        "当前不得进入Step 3。",
        "",
    ]
    (DOCS / "STEP2_DEEPSEEK_FACTUALITY_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Evidence: {folder}")
    print(f"Step2: {summary['final_status']}; human review pending; STOP before Step3.")
    return 0 if all(x["evaluation"]["automated_pass"] for x in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
