"""Immutable Round 1 offline assembly, then at most six single-shot Round 2 calls."""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from core.config import settings  # noqa: E402
from core.models import AiRun, Base, Project  # noqa: E402
from scripts.verify_dreo_step2 import RecordingProvider, save_json  # noqa: E402
from services.ai_service import run_structured_model  # noqa: E402
from services.model_provider import OpenAICompatibleProvider  # noqa: E402
from services.model_readiness import check_model_readiness, validate_model_input_budget  # noqa: E402
from services.product_content_pipeline import (  # noqa: E402
    MarketingContentResult,
    assemble_product_content,
    evaluate_agent_output,
    import_round1_copy,
)
from services.product_fact_repository import load_dreo_baseline  # noqa: E402

DOCS = ROOT / "docs/product_validation"
ROUND1 = DOCS / "runs/20261031T034918214674Z"
FIXTURE = ROOT / "tests/fixtures/dreo_316_step2_cases.json"
PRODUCT = "DREO-CERAMIC-HEATER-316"
VERSION = "dreo_step2_marketing_v2"


def hashes(folder):
    return {
        str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def store_content(folder, marketing, case, repository):
    final = assemble_product_content(
        repository,
        product_id=PRODUCT,
        market=case["market"],
        template_id=f"heater_{case['market'].lower()}_v1",
        marketing=marketing,
    )
    agent = evaluate_agent_output(marketing, case, repository, PRODUCT)
    save_json(folder / "parsed_marketing_copy.json", marketing.model_dump())
    save_json(folder / "rendered_specifications.json", final.rendered_specifications.model_dump())
    save_json(folder / "final_content.json", final.model_dump())
    (folder / "final_assembled_content.md").write_text(
        final.final_assembled_content, encoding="utf-8"
    )
    validation = {"final_pipeline": final.validation_result, "raw_llm": agent}
    save_json(folder / "validation_result.json", validation)
    return validation


def report(folder, result):
    lines = [
        "# Step 2 Round 2：确定性规格与模型营销文案",
        "",
        f"当前状态：**{result['status']}**；人工审核：pending；禁止自动发布。",
        "",
        "事实精确检索 → 状态筛选 → DeepSeek动态文案 → 确定性市场规格表 → 独立核验 → 人工审核。",
        "Repository Protocol 与 Pydantic DTO 不新增数据库表；基线适配器按商品和市场精确过滤。",
        "来源S02–S05是归档来源编号，不冒充业务数据库Evidence主键；后续持久化接入留给乙方。",
        "德国网页参数保留 confirmed_as_listed；未知参数省略，冲突形成未持久化Finding草稿。",
        "",
        "## 修改文件",
        "",
        "- services/specification_renderer.py：通用渲染器、字段状态、单位、市场模板。",
        "- services/product_fact_repository.py：基线哈希校验与精确检索适配器。",
        "- services/product_content_pipeline.py：动态文案Schema、整合和独立核验。",
        "- prompts/dreo_step2_marketing_v2.txt：仅生成动态营销文案的约束。",
        "- scripts/verify_dreo_renderer_round2.py：离线优先、零重试的六项验证入口。",
        "- tests/test_specification_renderer.py：渲染、来源、隔离与内容篡改测试。",
        "",
        "## 指标与原始结果",
        "",
        "```json",
        json.dumps(
            {key: value for key, value in result.items() if key != "cases"},
            ensure_ascii=False,
            indent=2,
        ),
        "```",
        "",
        "第一轮T1原始文案依旧遗漏型号：Raw LLM Missing Fact Count=1（历史关键覆盖口径19/20）。",
        "这项历史结果未被改为通过。新规格表补上型号，只计入Final Pipeline Completeness。",
        "第二轮动态文案不承担固定规格完整性；raw_missing_fields仅供完整性提示，不算事实错误。",
        "静态筛查发现数不能证明无幻觉；最终无依据声明数保留null，待逐句人工审核。",
        "",
        "## 六项明细",
        "",
    ]
    for case in result["cases"]:
        relative = (folder / case["path"]).relative_to(DOCS).as_posix()
        lines += [
            f"### {case['phase']} {case['id']}",
            "",
            f"自动核验：{case.get('automatic_pass', False)}；错误：{case.get('error')}。",
            f"[原始输入]({relative}/input.json) · [模型原文]({relative}/raw_output.txt) · "
            f"[结果]({relative}/result.json) · [独立校验]({relative}/validation_result.json)",
            f"[最终内容]({relative}/final_assembled_content.md) · "
            f"[逐字段来源]({relative}/rendered_specifications.json)",
            "",
        ]
    lines += [
        "## 人工审核清单",
        "",
        "- [ ] T1英文自然，型号、电压、频率、三档功率、温控与定时正确。",
        "- [ ] T2德语自然；检查der Fernbedienung等冠词表达、德语小数与单位。",
        "- [ ] T3型号、频率、完整温控、每档功率均保持未知。",
        "- [ ] T4遥控器保留两段S05冲突原文，未确定Yes/No。",
        "- [ ] T5未将美国型号、电压、频率用于德国商品。",
        "- [ ] T6未声称未证实认证、静音、节能、适用面积或遥控器随箱。",
        "- [ ] 逐句核对claims以外的自然语言声明和来源，填写人工审核结论。",
        "- [ ] 确认内部风险没有变成消费者承诺后，才决定是否批准发布。",
        "",
        "英德语自动Schema检查不等于人工语言验收。详细测试命令和结果见同目录TEST_RESULTS.md。",
        "本轮未修改前端、业务数据库、Step1事实或第一轮记录，未提交推送，未进入Step3。",
        "",
    ]
    (DOCS / "STEP2_ROUND2_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    repository = load_dreo_baseline(FIXTURE, DOCS / "PRODUCT_FACTS.md")
    before = hashes(ROUND1)
    folder = DOCS / "round_2" / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True)
    save_json(folder / "round1_hashes_before.json", before)
    records = []
    for case in fixture["cases"]:
        dest = folder / "offline" / case["id"]
        dest.mkdir(parents=True)
        raw = (ROUND1 / case["id"] / "raw_output.txt").read_text(encoding="utf-8")
        (dest / "raw_output.txt").write_text(raw, encoding="utf-8")
        (dest / "input.json").write_bytes((ROUND1 / case["id"] / "input.json").read_bytes())
        validation = store_content(dest, import_round1_copy(raw), case, repository)
        record = {
            "phase": "offline",
            "id": case["id"],
            "path": f"offline/{case['id']}",
            "automatic_pass": validation["final_pipeline"]["automatic_pass"],
            "raw_original_omission_model": case["id"] == "T1",
            "validation": validation,
        }
        save_json(dest / "result.json", record)
        records.append(record)
        print(f"offline {case['id']}: {record['automatic_pass']}", flush=True)
    offline_pass = all(item["automatic_pass"] for item in records)
    status = "PARTIAL" if offline_pass else "FAILED"
    calls = 0
    if args.live and offline_pass:
        if not check_model_readiness(settings).configured:
            status = "LIVE_TEST_BLOCKED"
        else:
            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(engine)
            provider = RecordingProvider(OpenAICompatibleProvider.from_settings())
            template = (ROOT / f"prompts/{VERSION}.txt").read_text(encoding="utf-8")
            with Session(engine, expire_on_commit=False) as db:
                project = Project(
                    name="Renderer Round2 isolated",
                    product_name=fixture["product_family"],
                    access_code_hash="unused",
                    markets_json='["US","DE"]',
                )
                db.add(project)
                db.flush()
                for case in fixture["cases"]:
                    dest = folder / "live" / case["id"]
                    dest.mkdir(parents=True)
                    # Current market only; the adversarial case request is not a fact source.
                    facts = [
                        fact.model_dump() for fact in repository.get_facts(PRODUCT, case["market"])
                    ]
                    prompt = (
                        template + "\nRetrieved facts:\n" + json.dumps(facts, ensure_ascii=False)
                    )
                    prompt += "\nSources:\n" + json.dumps(
                        repository.get_sources(), ensure_ascii=False
                    )
                    prompt += "\nIndependent test request:\n" + json.dumps(case, ensure_ascii=False)
                    validate_model_input_budget(prompt=prompt, review_count=0)
                    save_json(
                        dest / "input.json",
                        {
                            "case": case,
                            "prompt": prompt,
                            "prompt_version": VERSION,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )
                    provider.raw = None
                    error = None
                    validation = None
                    try:
                        parsed = run_structured_model(
                            project_id=project.id,
                            run_type=f"round2_{case['id']}",
                            prompt_version=VERSION,
                            prompt=prompt,
                            evidence_ids=[],
                            output_model=MarketingContentResult,
                            provider=provider,
                            session=db,
                        )
                        validation = store_content(dest, parsed, case, repository)
                    except Exception as exc:
                        # Never serialize request headers, API keys or exception messages.
                        error = {
                            "type": type(exc).__name__,
                            "code": getattr(exc, "code", "LOCAL_ERROR"),
                        }
                    raw = (
                        provider.raw
                        if isinstance(provider.raw, str)
                        else json.dumps(provider.raw, ensure_ascii=False)
                    )
                    (dest / "raw_output.txt").write_text(raw, encoding="utf-8")
                    run = db.scalar(select(AiRun).where(AiRun.run_type == f"round2_{case['id']}"))
                    record = {
                        "phase": "live",
                        "id": case["id"],
                        "path": f"live/{case['id']}",
                        "model": provider.model_name,
                        "prompt_version": VERSION,
                        "error": error,
                        "schema_pass": provider.raw is not None and error is None,
                        "automatic_pass": bool(
                            validation
                            and validation["final_pipeline"]["automatic_pass"]
                            and not validation["raw_llm"]["errors"]
                        ),
                        "validation": validation,
                        "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
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
                        }
                        if run
                        else None,
                    }
                    save_json(dest / "result.json", record)
                    if validation is None:
                        save_json(
                            dest / "validation_result.json", {"error": error, "publishable": False}
                        )
                    records.append(record)
                    db.commit()
                    calls = provider.calls
                    print(
                        f"live {case['id']}: auto={record['automatic_pass']} error={error}",
                        flush=True,
                    )
                    if error and (provider.raw is None):
                        status = "LIVE_TEST_BLOCKED"
                        break
                else:
                    status = (
                        "PENDING_HUMAN_REVIEW"
                        if all(record["automatic_pass"] for record in records)
                        else "FAILED"
                    )
    live = [record for record in records if record["phase"] == "live"]
    validations = [record["validation"] for record in live if record["validation"]]
    after = hashes(ROUND1)
    assert before == after, "Round1 files changed"
    result = {
        "status": status,
        "model": settings.model_name,
        "provider_calls": calls,
        "retries": 0,
        "offline_pass": offline_pass,
        "round1_unchanged": before == after,
        "round1_files_verified": len(before),
        "baseline_sha256": fixture["baseline_sha256"],
        "business_database": "untouched; AiRun isolated in memory and exported",
        "raw_llm_missing_fact_count": sum(
            len(v["raw_llm"]["raw_missing_fields"]) for v in validations
        ),
        "raw_llm_missing_note": "Canonical string completeness warnings, not hallucination errors",
        "raw_llm_unsupported_claim_count_detected": sum(
            v["final_pipeline"]["unsupported_claim_count_detected"] for v in validations
        ),
        "final_unsupported_claim_count": None,
        "human_review": "pending",
        "publishable": False,
        "schema_pass": [sum(record["schema_pass"] for record in live), 6],
        "final_specification_coverage": [
            sum(v["final_pipeline"]["required_fields_present"] for v in validations),
            49,
        ],
        "unknown_handling_accuracy": [sum(v["raw_llm"]["unknown_correct"] for v in validations), 4],
        "conflict_handling_accuracy": [
            sum(v["raw_llm"]["conflict_correct"] for v in validations),
            2,
        ],
        "cross_market_contamination_count_detected": sum(
            sum(
                error.startswith("final_cross_market")
                for error in v["final_pipeline"]["prose_flags"]
            )
            for v in validations
        ),
        "us_template_pass": [sum(r["automatic_pass"] for r in live if r["id"] == "T1"), 1],
        "de_template_pass": [sum(r["automatic_pass"] for r in live if r["id"] != "T1"), 5],
        "cases": records,
    }
    save_json(folder / "summary.json", result)
    report(folder, result)
    print(f"{status}: {folder}", flush=True)
    return 0 if offline_pass and status != "FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
