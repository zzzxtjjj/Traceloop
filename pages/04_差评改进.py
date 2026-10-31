import json
from pathlib import Path
from urllib.parse import urlsplit

import streamlit as st

from core.access_ui import render_role_boundary_notice, render_user_error
from core.config import settings
from core.db import init_db
from core.errors import TradeLoopError
from core.theme import apply_brand_theme, render_footer, render_page_header
from core.ui import render_sidebar
from services.finding_service import review_finding
from services.model_readiness import check_model_readiness
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
from services.traceability_service import FindingTrace, get_finding_trace

try:
    from services.review_ai_service import (
        analyze_review_batch_with_model,
        get_latest_review_ai_run,
    )
except ImportError:
    analyze_review_batch_with_model = None
    get_latest_review_ai_run = None

REVIEW_TEMPLATE = Path(__file__).resolve().parents[1] / "data" / "demo" / "reviews_before.csv"

AI_ERROR_MESSAGES = {
    "MODEL_NOT_CONFIGURED": "模型未配置，未发起外部调用。",
    "MODEL_TIMEOUT": "模型调用超时，本次 AI 分析未写入业务结论。",
    "MODEL_AUTH_ERROR": "模型鉴权失败，请检查 API Key。",
    "MODEL_RATE_LIMIT": "模型调用频率受限，请稍后重试。",
    "MODEL_PROVIDER_ERROR": "模型服务暂时不可用，请稍后重试。",
    "MODEL_BAD_RESPONSE": "模型服务返回了无法解析的响应。",
    "MODEL_BAD_JSON": "模型输出未通过结构校验，未写入半成品 Finding。",
    "MODEL_EVIDENCE_INVALID": "模型引用的评价 ID 或原文片段无效，未写入 Finding。",
    "MODEL_INPUT_LIMIT": "输入超过本次模型分析上限，未发起外部调用。",
    "MODEL_ANALYSIS_WRITE_FAILED": "模型结果写入失败，事务已回滚。",
}


def read_result_value(result, *names, default=None):
    for name in names:
        if isinstance(result, dict) and name in result:
            return result[name]
        if hasattr(result, name):
            return getattr(result, name)
    return default


def render_ai_run_summary(run) -> None:
    if run is None:
        st.caption("当前批次还没有 AI 运行记录。")
        return
    run_id = read_result_value(run, "ai_run_id", "id", default="-")
    model = read_result_value(run, "model", "model_name", default=settings.model_name or "未配置")
    prompt_version = read_result_value(run, "prompt_version", default="-")
    status = read_result_value(run, "status", default="unknown")
    error_code = read_result_value(run, "error_code", default=None)
    first, second, third, fourth = st.columns(4)
    first.metric("AiRun ID", run_id)
    second.metric("模型", model)
    third.metric("Prompt 版本", prompt_version)
    fourth.metric("运行状态", status)
    if error_code:
        error_message = AI_ERROR_MESSAGES.get(error_code, "模型调用失败。")
        st.error(f"error_code：{error_code} · {error_message}")


def render_model_configuration_status(readiness) -> None:
    """Show safe local configuration metadata without triggering a live request."""
    key_configured = "MODEL_API_KEY" not in readiness.missing_fields
    service_host = urlsplit(readiness.base_url).hostname or "未配置或无效"
    status = (
        "尚未真实联网验证"
        if readiness.configured
        else "配置不完整 · 尚未真实联网验证"
    )
    max_attempts = readiness.max_attempts
    first, second, third = st.columns(3)
    first.metric("API Key", "已配置" if key_configured else "未配置")
    second.metric("模型名", readiness.model_name or "未配置")
    third.metric("服务地址主机", service_host)
    fourth, fifth, sixth = st.columns(3)
    fourth.metric("请求超时", f"{readiness.timeout_seconds:g} 秒")
    fifth.metric(
        "单次输入上限",
        f"{readiness.max_input_chars:,} 字符 / {readiness.max_reviews_per_run} 条评价 / "
        f"最多 {max_attempts} 次请求",
    )
    sixth.metric("联网状态", status)
    if readiness.issues:
        st.warning("本地配置存在无效项，请运行离线检查命令并修正 .env。")

    with st.expander("模型 API 安全配置与检查命令"):
        st.caption(
            "只把真实密钥放在本机 .env 或部署 Secret 中，不要提交 Git 或放进截图。"
        )
        st.code(
            "MODEL_API_KEY=<YOUR_API_KEY>\n"
            "MODEL_NAME=<YOUR_MODEL_NAME>\n"
            "MODEL_BASE_URL=https://api.openai.com/v1\n"
            "MODEL_TIMEOUT_SECONDS=30\n"
            "MODEL_MAX_INPUT_CHARS=50000\n"
            "MODEL_MAX_REVIEWS_PER_RUN=200\n"
            "MODEL_MAX_ATTEMPTS=1",
            language="dotenv",
        )
        st.caption(
            "MODEL_MAX_ATTEMPTS 默认 1，不自动进行结构修复重试；"
            "只有用户显式设置为 2 时才允许一次结构修复。联网检查始终只请求 1 次。"
        )
        st.write("离线检查（不发起外部请求）：")
        st.code(r"python scripts\check_model_api.py", language="powershell")
        st.write("明确接受可能的请求与费用后，才由操作者在终端执行联网检查：")
        st.code(r"python scripts\check_model_api.py --live", language="powershell")
        st.caption("页面不提供在线测试按钮；以上地址仅为兼容格式示例，不代表已验证。")


def render_closed_loop_trace(trace: FindingTrace) -> None:
    st.markdown("**Evidence Graph / 闭环追踪**")
    st.caption(
        "Evidence → Finding → 人工审核 → Task → Delivery → Recheck；状态只显示数据库中的真实关系。"
    )
    source_col, task_col, delivery_col, recheck_col = st.columns(4)
    source_col.metric("原始证据", trace.evidence_status)
    task_col.metric("改进任务", trace.task_status)
    delivery_col.metric("交付验收", trace.delivery_status)
    recheck_col.metric("后续复检", trace.recheck_status)

    if trace.evidence:
        st.success(f"原始评价证据 available · {len(trace.evidence)} 条")
    else:
        st.warning("原始评价证据 missing · 未找到可验证的原文关联。")

    if trace.task is None:
        st.warning("改进任务 missing · 当前 Finding 尚未关联任务。")
    else:
        task = trace.task
        st.write(
            f"任务 #{task.id} · {task.title} · 责任岗位：{task.owner_role} · "
            f"状态：{task.status} · {'已发布' if task.confirmed else '草稿'}"
        )
        if not task.submissions:
            st.info("交付验收 missing · 当前任务尚未提交交付材料。")
        for submission in task.submissions:
            with st.expander(
                f"交付 #{submission.id} · {submission.review_status} · "
                f"证据 #{submission.evidence_id}"
            ):
                st.write(submission.content)
                st.code(submission.evidence_excerpt, language=None)
                st.caption(f"提交岗位：{submission.submitted_by_role}")
                if submission.review_status == "pending_review":
                    st.info("验收 pending · 等待其他有权角色人工验收。")
                else:
                    st.write(f"审核人：{submission.reviewed_by or '未记录'}")
                    st.write(f"审核意见：{submission.review_note or '未填写'}")

    if trace.improvement is None:
        st.warning("改进记录 missing · 尚未建立基线与后续复检关系。")
        return

    improvement = trace.improvement
    st.write(
        f"改进记录 #{improvement.id} · {improvement.status} · "
        f"主题：{THEME_LABELS.get(improvement.theme, improvement.theme)}"
    )
    st.write(
        f"基线批次 #{improvement.baseline.id} · {improvement.baseline.name} · "
        f"{improvement.baseline_count}/{improvement.baseline.sample_size} "
        f"({improvement.baseline_share:.1%})"
    )
    if improvement.followup is None:
        st.info("后续复检 pending · 尚未关联可比较的后续评价批次。")
    else:
        followup_count = improvement.followup_count or 0
        followup_share = improvement.followup_share or 0.0
        st.write(
            f"复检批次 #{improvement.followup.id} · {improvement.followup.name} · "
            f"{followup_count}/{improvement.followup.sample_size} ({followup_share:.1%})"
        )
        if improvement.share_delta is not None:
            st.caption(f"占比变化：{improvement.share_delta:+.1%}")
    st.warning(improvement.limitation_note)


def render_decision_passport(*, finding, evidence, ai_run=None, trace=None) -> None:
    """Render an auditable summary without creating new business state."""
    st.markdown("**AI Decision Passport / AI 决策护照**")
    model_run_id = getattr(finding, "model_run_id", None)
    mode = "规则降级" if not model_run_id else "模型结果"
    missing = json.loads(getattr(finding, "missing_info_json", "[]"))
    actions = json.loads(getattr(finding, "suggested_actions_json", "[]"))
    passport = {
        "结论 ID": f"Finding #{finding.id}",
        "结论模式": mode,
        "模型运行": f"AiRun #{model_run_id}" if model_run_id else "-",
        "证据引用": ", ".join(f"#{item.id}" for item in evidence) or "missing",
        "未知或缺失信息": "；".join(missing) if missing else "未记录",
        "人工审核": getattr(finding, "review_status", "unknown"),
        "下一步行动": "；".join(actions) if actions else "需要人工审核",
    }
    if ai_run is not None and model_run_id:
        passport["模型"] = read_result_value(
            ai_run, "model", "model_name", default="configured model"
        )
        passport["Prompt 版本"] = read_result_value(ai_run, "prompt_version", default="-")
        passport["运行状态"] = read_result_value(ai_run, "status", default="unknown")
    st.dataframe(
        [{"字段": key, "值": value} for key, value in passport.items()],
        hide_index=True,
        use_container_width=True,
    )
    if trace is not None:
        st.caption(
            "Evidence Graph 状态："
            f"evidence={trace.evidence_status} · task={trace.task_status} · "
            f"delivery={trace.delivery_status} · recheck={trace.recheck_status}"
        )


def render_improvement_replay(
    *, comparison, baseline_label: str, followup_label: str, theme_label: str
) -> None:
    """Show the measured feedback-to-recheck chain without implying causality."""
    st.markdown("**Improvement Replay / 改进复盘**")
    st.caption(
        "同一主题、同一统计口径、不同批次；复检结果用于观察变化，不自动证明措施造成变化。"
    )
    steps = [
        ("01", "首批反馈", f"{baseline_label} · n={comparison.baseline_sample_size}"),
        ("02", "人工确认", f"主题：{theme_label} · 形成待办行动"),
        ("03", "执行与验收", "任务、交付证据和人工验收留在闭环中"),
        ("04", "后续复检", f"{followup_label} · n={comparison.followup_sample_size}"),
    ]
    cols = st.columns(4)
    for column, (number, title, detail) in zip(cols, steps, strict=True):
        column.markdown(f"**{number} · {title}**")
        column.caption(detail)
    first, second, delta = st.columns(3)
    first.metric(
        "基线主题占比",
        f"{comparison.baseline_count}/{comparison.baseline_sample_size}",
        f"{comparison.baseline_share:.1%}",
    )
    second.metric(
        "复检主题占比",
        f"{comparison.followup_count}/{comparison.followup_sample_size}",
        f"{comparison.followup_share:.1%}",
    )
    delta.metric("占比变化", f"{comparison.share_delta:+.1%}")
    st.info(comparison.conclusion)
    st.warning(f"限制：{comparison.limitation_note}")

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
render_role_boundary_notice(role)

st.info(
    "可选择可复现的关键词规则分类，或在模型已配置时运行真实 AI 分类。"
    "无论使用哪种方式，评价占比都不等同于商品实际故障率，原因假设也不代表责任认定。"
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
            render_user_error(exc, fallback="评价文件校验失败，请检查字段和数据格式。")
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

analysis_mode = st.radio(
    "分类方式",
    options=["规则分类", "真实 AI 分类"],
    horizontal=True,
    help="规则分类可复现；AI 分类必须通过结构校验和人工审核。",
)
model_readiness = check_model_readiness(settings)
render_model_configuration_status(model_readiness)
model_configured = model_readiness.configured
if model_configured:
    st.success(f"模型本地配置已就绪：{model_readiness.model_name}；尚未真实联网验证。")
else:
    st.warning(
        "模型配置不完整或无效。请先运行离线检查；选择真实 AI 时将明确降级为规则分类。"
    )

if st.button("运行所选分类", type="primary"):
    if analysis_mode == "规则分类":
        try:
            summaries = analyze_review_batch(
                project_id=project_id,
                batch_id=selected_batch_id,
            )
        except (TradeLoopError, ValueError) as exc:
            render_user_error(exc, fallback="规则分类失败，请检查评价批次。")
        else:
            st.success(
                f"规则分类已生成 {len(summaries)} 个主题统计；重复运行不会覆盖人工审核。"
            )
    elif not model_configured:
        try:
            summaries = analyze_review_batch(
                project_id=project_id,
                batch_id=selected_batch_id,
            )
        except (TradeLoopError, ValueError) as exc:
            render_user_error(exc, fallback="规则分类失败，请检查评价批次。")
        else:
            st.warning(
                f"真实 AI 未配置，已降级为可复现规则分类并生成 {len(summaries)} 个主题统计。"
            )
    elif analyze_review_batch_with_model is None:
        st.error("真实 AI 分析接口尚未就绪，评价批次已保留，未写入 AI Finding。")
        try:
            summaries = analyze_review_batch(
                project_id=project_id,
                batch_id=selected_batch_id,
            )
        except (TradeLoopError, ValueError) as exc:
            render_user_error(exc, fallback="规则分类失败，请检查评价批次。")
        else:
            st.warning(f"已降级为规则分类并生成 {len(summaries)} 个主题统计。")
    else:
        try:
            result = analyze_review_batch_with_model(
                project_id=project_id,
                batch_id=selected_batch_id,
            )
        except TradeLoopError as exc:
            code = getattr(exc, "code", "TRADELOOP_ERROR")
            render_user_error(exc, fallback=AI_ERROR_MESSAGES.get(code, "模型调用失败。"))
            st.info("评价批次已保留；失败的模型输出不会写入半成品 Finding。")
            try:
                summaries = analyze_review_batch(
                    project_id=project_id,
                    batch_id=selected_batch_id,
                )
            except (TradeLoopError, ValueError) as fallback_exc:
                render_user_error(
                    fallback_exc,
                    fallback="规则降级也未完成，请检查评价批次。",
                )
            else:
                st.warning(f"已降级为规则分类并生成 {len(summaries)} 个主题统计。")
        except ValueError as exc:
            render_user_error(exc, fallback="AI 结果校验失败，未写入关键业务状态。")
            st.info("评价批次已保留；无效结构不会写入关键业务状态。")
        else:
            finding_ids = read_result_value(result, "finding_ids", default=[])
            status = read_result_value(result, "status", default="success")
            st.success(
                f"真实 AI 分类完成：状态 {status}，"
                f"生成 {len(finding_ids)} 个待审核 Finding。"
            )
            render_ai_run_summary(result)

st.markdown("**最近一次 AI 运行**")
if get_latest_review_ai_run is None:
    st.caption("AI 运行查询接口尚未就绪。规则分类仍可正常使用。")
else:
    try:
        latest_ai_run = get_latest_review_ai_run(
            project_id=project_id,
            batch_id=selected_batch_id,
        )
    except TradeLoopError as exc:
        render_user_error(exc, fallback="读取 AI 运行状态失败。")
    else:
        render_ai_run_summary(latest_ai_run)

findings = list_batch_findings(project_id, selected_batch_id)
if findings:
    st.markdown("### 3 · 发现、证据与人工审核")
    for finding in findings:
        theme = finding.finding_type.rsplit(":", maxsplit=1)[-1]
        label = THEME_LABELS.get(theme, theme)
        classification_label = "真实 AI" if finding.model_run_id else "规则分类"
        with st.expander(
            f"{label} · {classification_label} · {finding.review_status}",
            expanded=True,
        ):
            st.write(finding.statement)
            left, middle, right = st.columns(3)
            left.metric("样本量", finding.sample_size or 0)
            middle.metric("风险状态", finding.epistemic_status)
            right.metric("人工审核", finding.review_status)
            if finding.model_run_id:
                st.warning(
                    f"该 Finding 来自 AiRun #{finding.model_run_id}。模型内容是待审核的原因假设，"
                    "不构成供应商、物流或员工责任认定。"
                )
            else:
                st.caption("该 Finding 来自可复现规则分类，不代表 AI 判断。")

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

            trace = None
            if finding.review_status in {"accepted", "revised", "rejected"}:
                try:
                    trace = get_finding_trace(
                        project_id=project_id,
                        finding_id=finding.id,
                    )
                except TradeLoopError as exc:
                    render_user_error(exc, fallback="闭环追踪读取失败。")
                else:
                    render_closed_loop_trace(trace)

            render_decision_passport(
                finding=finding,
                evidence=evidence,
                ai_run=latest_ai_run,
                trace=trace,
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
                    try:
                        review_finding(
                            project_id=project_id,
                            finding_id=finding.id,
                            decision="accepted",
                            reviewer=role,
                            note=note,
                        )
                    except (TradeLoopError, ValueError) as exc:
                        render_user_error(exc, fallback="Finding 接受失败，请检查审核信息。")
                    else:
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
                    except (TradeLoopError, ValueError) as exc:
                        render_user_error(exc, fallback="Finding 修改失败，请检查审核内容。")
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
                    except (TradeLoopError, ValueError) as exc:
                        render_user_error(exc, fallback="Finding 驳回失败，请填写审核理由。")
                    else:
                        st.rerun()
            elif finding.review_status in {"accepted", "revised"}:
                st.success(f"已由 {finding.reviewed_by} 完成人工审核。")
                if st.button("生成改进任务草稿", key=f"task_{finding.id}"):
                    try:
                        task = create_task_from_finding(
                            project_id=project_id,
                            finding_id=finding.id,
                        )
                    except (TradeLoopError, ValueError) as exc:
                        render_user_error(exc, fallback="改进任务草稿创建失败。")
                    else:
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
                        render_user_error(exc, fallback="改进任务无法发布，请检查验收标准。")
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
                render_user_error(exc, fallback="复检失败，请检查批次和主题。")
            else:
                render_improvement_replay(
                    comparison=comparison,
                    baseline_label=batch_labels[baseline_id],
                    followup_label=batch_labels[followup_id],
                    theme_label=THEME_LABELS.get(theme, theme),
                )

render_footer()

