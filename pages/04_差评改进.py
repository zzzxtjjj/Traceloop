import json
from pathlib import Path

import streamlit as st

from core.db import init_db
from core.errors import TradeLoopError
from core.theme import apply_brand_theme, render_footer, render_page_header
from core.ui import render_sidebar
from services.finding_service import review_finding
from services.review_service import (
    THEME_LABELS,
    analyze_review_batch,
    compare_review_batches,
    get_finding_evidence,
    import_reviews,
    list_batch_findings,
    list_review_batches,
)
from services.task_service import (
    confirm_task,
    create_improvement_record,
    create_task_from_finding,
)

REVIEW_TEMPLATE = Path(__file__).resolve().parents[1] / "data" / "demo" / "reviews_before.csv"

init_db()
st.set_page_config(page_title="差评改进 · TradeLoop", page_icon="〰️", layout="wide")
apply_brand_theme()
render_page_header(
    "QUALITY INSIGHTS · 客户声音",
    "差评证据链与改进复检",
    "从评价原文出发，区分统计、原因假设与人工结论，再连接改进任务和后续复检。",
)
project_id, role = render_sidebar()
if project_id is None:
    st.warning("请先进入一个项目。")
    st.stop()

st.info(
    "当前版本默认使用可复现的关键词规则分类，不会把它冒充为 AI。"
    "评价占比也不等同于商品实际故障率。"
)

with st.expander("1 · 导入评价 CSV", expanded=not list_review_batches(project_id)):
    st.caption(
        "必需列：review_id、batch、rating、date、sku、market、review_text；"
        "可选列：order_id、production_batch、supplier。"
    )
    st.download_button(
        "下载评价 CSV 示例",
        data=REVIEW_TEMPLATE.read_bytes(),
        file_name="review_import_example.csv",
        mime="text/csv",
    )
    uploaded = st.file_uploader("评价文件", type=["csv"], key="review_csv")
    batch_name = st.text_input("批次名称", placeholder="例如：包装改进前 · 2026-10")
    if st.button("校验并导入", type="primary", disabled=uploaded is None):
        try:
            result = import_reviews(
                project_id=project_id,
                source=uploaded,
                batch_name=batch_name,
            )
        except (TradeLoopError, ValueError) as exc:
            st.error(str(exc))
        else:
            if result.duplicate_file:
                st.warning("该文件已导入，本次没有重复写入评价。")
            else:
                st.success(
                    f"导入 {result.inserted_count} 条；跳过重复评价 {result.duplicate_count} 条。"
                )
            st.rerun()

batches = list_review_batches(project_id)
if not batches:
    st.warning("尚无评价批次。请先导入 CSV。")
    render_footer()
    st.stop()

batch_labels = {
    batch.id: f"{batch.name} · {batch.market} · n={batch.sample_size}" for batch in batches
}
selected_batch_id = st.selectbox(
    "2 · 选择分析批次",
    options=list(batch_labels),
    format_func=lambda item: batch_labels[item],
)

if st.button("运行/查看确定性主题分析", type="primary"):
    try:
        summaries = analyze_review_batch(project_id=project_id, batch_id=selected_batch_id)
    except (TradeLoopError, ValueError) as exc:
        st.error(str(exc))
    else:
        st.success(f"已生成 {len(summaries)} 个主题统计；重复运行不会覆盖人工审核。")

findings = list_batch_findings(project_id, selected_batch_id)
if findings:
    st.markdown("### 3 · 发现、证据与人工审核")
    for finding in findings:
        theme = finding.finding_type.rsplit(":", maxsplit=1)[-1]
        label = THEME_LABELS.get(theme, theme)
        with st.expander(f"{label} · {finding.review_status}"):
            st.write(finding.statement)
            left, middle, right = st.columns(3)
            left.metric("样本量", finding.sample_size or 0)
            middle.metric("风险状态", finding.epistemic_status)
            right.metric("人工审核", finding.review_status)

            missing = json.loads(finding.missing_info_json)
            alternatives = json.loads(finding.alternative_explanations_json)
            actions = json.loads(finding.suggested_actions_json)
            if missing:
                st.warning("缺失信息：" + "；".join(missing))
            st.caption("可能的替代解释：" + "；".join(alternatives))
            st.caption("建议行动：" + "；".join(actions))

            evidence = get_finding_evidence(project_id, finding.id)
            st.markdown("**支持证据**")
            for item in evidence:
                locator = json.loads(item.locator_json)
                st.code(
                    f"评价 {locator.get('review_id', '-')} / CSV 第 "
                    f"{locator.get('csv_row', '-')} 行\n{item.excerpt}",
                    language=None,
                )

            if finding.review_status == "pending_review":
                note = st.text_area(
                    "审核备注",
                    key=f"finding_note_{finding.id}",
                    placeholder="说明核对了什么；驳回或修改时必须填写。",
                )
                revised = st.text_area(
                    "修改后的结论（仅选择“修改并接受”时必填）",
                    key=f"finding_revised_{finding.id}",
                )
                accept_col, revise_col, reject_col = st.columns(3)
                if accept_col.button("接受", key=f"accept_{finding.id}"):
                    review_finding(
                        project_id=project_id,
                        finding_id=finding.id,
                        decision="accepted",
                        reviewer=role,
                        note=note,
                    )
                    st.rerun()
                if revise_col.button("修改并接受", key=f"revise_{finding.id}"):
                    try:
                        review_finding(
                            project_id=project_id,
                            finding_id=finding.id,
                            decision="revised",
                            reviewer=role,
                            note=note,
                            revised_statement=revised,
                        )
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.rerun()
                if reject_col.button("驳回", key=f"reject_{finding.id}"):
                    try:
                        review_finding(
                            project_id=project_id,
                            finding_id=finding.id,
                            decision="rejected",
                            reviewer=role,
                            note=note,
                        )
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.rerun()
            elif finding.review_status in {"accepted", "revised"}:
                st.success(f"已由 {finding.reviewed_by} 完成人工审核。")
                if st.button("生成改进任务草稿", key=f"task_{finding.id}"):
                    task = create_task_from_finding(
                        project_id=project_id,
                        finding_id=finding.id,
                    )
                    st.success(f"任务草稿 #{task.id} 已创建，尚未发布。")
                if st.button("确认并发布改进任务", key=f"confirm_task_{finding.id}"):
                    try:
                        task = create_task_from_finding(
                            project_id=project_id,
                            finding_id=finding.id,
                        )
                        if task.status == "draft":
                            task = confirm_task(
                                project_id=project_id,
                                task_id=task.id,
                                confirmer_role=role,
                            )
                        create_improvement_record(
                            project_id=project_id,
                            finding_id=finding.id,
                            task_id=task.id,
                            baseline_batch_id=selected_batch_id,
                        )
                    except (TradeLoopError, ValueError) as exc:
                        st.error(str(exc))
                    else:
                        st.success(f"任务 #{task.id} 已发布，并建立改进基线。")
else:
    st.warning("当前批次尚未分析。")

if len(batches) >= 2:
    st.markdown("### 4 · 同口径复检")
    baseline_id = st.selectbox(
        "基线批次",
        options=list(batch_labels),
        format_func=lambda item: batch_labels[item],
        key="baseline_batch",
    )
    followup_id = st.selectbox(
        "后续批次",
        options=list(batch_labels),
        format_func=lambda item: batch_labels[item],
        key="followup_batch",
    )
    theme = st.selectbox(
        "问题主题",
        options=list(THEME_LABELS),
        format_func=lambda item: THEME_LABELS[item],
    )
    if st.button("比较两批评价"):
        if baseline_id == followup_id:
            st.error("请选择两个不同批次。")
        else:
            try:
                comparison = compare_review_batches(
                    project_id=project_id,
                    baseline_batch_id=baseline_id,
                    followup_batch_id=followup_id,
                    theme=theme,
                )
            except (TradeLoopError, ValueError) as exc:
                st.error(str(exc))
            else:
                first, second, delta = st.columns(3)
                first.metric(
                    "基线",
                    f"{comparison.baseline_count}/{comparison.baseline_sample_size}",
                    f"{comparison.baseline_share:.1%}",
                )
                second.metric(
                    "复检",
                    f"{comparison.followup_count}/{comparison.followup_sample_size}",
                    f"{comparison.followup_share:.1%}",
                )
                delta.metric("占比变化", f"{comparison.share_delta:+.1%}")
                st.write(comparison.conclusion)
                st.warning(comparison.limitation_note)

render_footer()

