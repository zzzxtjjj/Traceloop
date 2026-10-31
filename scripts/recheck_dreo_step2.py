"""Re-evaluate immutable Step 2 outputs locally, with no model requests."""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.product_factuality import aggregate_results, evaluate_result  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    docs = ROOT / "docs" / "product_validation"
    folder = args.run.resolve()
    if not folder.is_relative_to((docs / "runs").resolve()):
        parser.error("只允许重新检查当前项目保存的Step2运行。")
    original = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    fixture_path = ROOT / "tests" / "fixtures" / "dreo_316_step2_cases.json"
    if hashlib.sha256(fixture_path.read_bytes()).hexdigest() != original["fixture_sha256"]:
        parser.error("夹具已变化，不能将新期望用于原结果。")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    results = []
    for case, old in zip(fixture["cases"], original["cases"], strict=True):
        raw = (folder / case["id"] / "raw_output.txt").read_text(encoding="utf-8")
        if hashlib.sha256(raw.encode()).hexdigest() != old["raw_sha256"]:
            parser.error("原始输出哈希不符，停止。")
        try:
            value = json.loads(raw)
        except ValueError:
            value = raw
        evaluation = evaluate_result(value, case, fixture)
        if old["error"]:
            evaluation["errors"].append(old["error"]["code"])
            evaluation["automated_pass"] = False
        record = {**old, "evaluation": evaluation, "evaluator_version": "dreo_step2_rules_v2"}
        (folder / case["id"] / "result.reevaluated.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        results.append(record)
    summary = aggregate_results([record["evaluation"] for record in results])
    if any(not record["evaluation"]["automated_pass"] for record in results):
        summary["final_status"] = "FAILED"
    data = {
        **original,
        "summary": summary,
        "cases": results,
        "evaluation_note": "原始输出不变；修正T4格式/疑问句误报，增加正文关键事实覆盖。",
    }
    (folder / "summary.reevaluated.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.copy2(ROOT / "services" / "product_factuality.py", folder / "evaluator_v2.py.snapshot")
    target = docs / "STEP2_DEEPSEEK_FACTUALITY_REPORT.md"
    initial = folder / "report.initial.md"
    if target.exists() and not initial.exists():
        shutil.copy2(target, initial)
    lines = [
        "# Step 2：DREO 316真实DeepSeek商品事实检查",
        "",
        f"模型：`{data['model']}`。真实主请求：{data['provider_calls']}次，重试0次。",
        f"运行：`{folder.name}`；Git HEAD：`{data['git_head']}`，已有未提交修改保留。",
        "仅使用用户提供PRODUCT_FACTS.md作为事实基线，US/DE分开；未重新抓取规格或评价。",
        f"基线SHA-256：`{data['baseline_sha256']}`。三份D盘原文件已原样归档。",
        "Step1通过依据为本次用户指令；旧文档待验收文字未改写。",
        "",
        f"## 当前结论：{summary['final_status']}",
        "",
        "T1正文遗漏US型号，不能建议Step2通过。其余五项通过已定义的自动检查，仍待人工逐句确认。",
        "结构化claims的关键事实准确率与正文覆盖率分开，不能用前者代替正文正确性。",
        "自动检测0个无依据声明不证明语义上的总数为0，最终总数尚待人工审核。",
        "",
        "```json",
        json.dumps(summary, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 原始结果与检查器修正",
        "",
        "第一次检查将T4的德语疑问句误标为包含遥控器承诺，且错误要求conflicts重复字段名。",
        "修正后只用原始六份输出重新计算，没有增加模型请求。初始result.json/summary.json、",
        "原始raw_output.txt和input.json均保留；修订结果另存*.reevaluated.json。",
        "T1正文缺型号属于实际缺项，未删除或改写模型输出来通过检查。",
        "",
        "## 六项测试与文案逐句待审",
        "",
    ]
    for record in results:
        evaluation = record["evaluation"]
        prefix = f"runs/{folder.name}/{record['id']}"
        label = "自动检查通过" if evaluation["automated_pass"] else "自动检查未通过"
        lines += [
            f"### {record['id']} · {label}",
            "",
            "**测试输入：** " + record["request"],
            "",
            f"- [完整输入]({prefix}/input.json)",
            f"- [不可改写的原始输出]({prefix}/raw_output.txt)",
            f"- [复核结果与结构化数据]({prefix}/result.reevaluated.json)",
            f"- 耗时：{record['ai_run']['latency_ms']}ms；结构校验：{evaluation['schema_pass']}。",
            "- 错误：" + ("、".join(evaluation["errors"]) or "已定义规则未发现错误"),
            "",
            "**最终文案：**",
            "",
            "```text",
            evaluation.get("structured_output", {}).get(
                "generated_copy", "结构不合法，查看原始输出"
            ),
            "```",
            "",
            "**逐句审核（用户未确认前保持待审）：**",
            "",
        ]
        for index, sentence in enumerate(evaluation["sentences"], 1):
            lines.append(f"- [ ] S{index}：{sentence['text']} —— 请填写对应来源ID与审核意见。")
        lines += [""]
    lines += [
        "## 自动化验证",
        "",
        "在最终测试后追加实际pytest/Ruff命令和结果；不能据本脚本运行推断测试已通过。",
        "",
        "## 限制与停止条件",
        "",
        "- 六项小样本只测试本事实基线和本次Prompt，不证明普遍无幻觉或正式合规。",
        "- claims数值、来源ID和部分正文标记为确定性检查；语义、否定、功能和语言仍需人工。",
        "- T1缺型号需修复后另行获得补测授权，本轮六次主调用预算已用完，不擅自重跑。",
        "- T2存在德语表达待润色（如des Fernbedienung）；不改原输出掩盖问题。",
        "- 未改前端/表结构/业务数据库，未做两轮反馈、评价导入、群聊或文件管理。",
        "- 人工验收未完成；不得进入Step3。",
        "",
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
