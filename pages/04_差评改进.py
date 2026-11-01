import json
from pathlib import Path
from urllib.parse import urlsplit

import streamlit as st

from core.access_ui import render_role_boundary_notice, render_user_error
from core.config import settings
from core.db import init_db, session_context
from core.errors import ProjectAccessDeniedError, TradeLoopError
from core.product_ui import select_product
from core.theme import apply_brand_theme, render_footer, render_page_header
from core.ui import render_sidebar
from services.app_preferences import runtime_config
from services.finding_service import review_finding
from services.model_readiness import check_model_readiness
from services.product_identity_service import assign_product
from services.review_service import (
    THEME_LABELS,
    analyze_review_batch,
    compare_review_batches,
    get_finding_evidence,
    import_reviews,
    list_batch_findings,
    list_review_batches,
    preview_review_csv,
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
    "MODEL_BAD_JSON": "模型输出未通过结构校验，未写入未通过验证的问题记录。",
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
    with st.expander("分析记录（详情）"):
        st.write(f"运行编号：{run_id}")
        st.write(f"使用模型：{model}")
        st.write(f"分析方案：{prompt_version}")
        st.write("结果：" + {"success": "分析成功", "failed": "分析失败"}.get(status, "处理中"))
    if error_code:
        error_message = AI_ERROR_MESSAGES.get(error_code, "模型调用失败。")
        with st.expander("查看失败原因"):
            st.error(error_message)


def render_model_configuration_status(readiness) -> None:
    """Show safe local configuration metadata without triggering a live request."""
    key_configured = "MODEL_API_KEY" not in readiness.missing_fields
    service_host = urlsplit(readiness.base_url).hostname or "未配置或无效"
    status = "尚未真实联网验证" if readiness.configured else "配置不完整 · 尚未真实联网验证"
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
        st.caption("只把真实密钥放在本机 .env 或部署 Secret 中，不要提交 Git 或放进截图。")
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
    st.markdown("**处理进度：从问题到改进结果**")
    st.caption(
        "Evidence Graph：评价原文 → Finding → 人工审核 → Task → Delivery → Recheck；"
        "状态只显示数据库中的真实关系。"
    )
    source_col, task_col, delivery_col, recheck_col = st.columns(4)
    source_col.metric("原始证据", trace.evidence_status)
    task_col.metric("改进任务", trace.task_status)
    delivery_col.metric("交付验收", trace.delivery_status)
    recheck_col.metric("后续复检", trace.recheck_status)

    if trace.evidence:
        st.success(f"找到 {len(trace.evidence)} 条原始评价依据")
    else:
        st.warning("没有找到原始评价依据，请补充后再确认。")

    if trace.task is None:
        st.warning("还没有改进任务。请先审核这个问题，再创建任务。")
    else:
        task = trace.task
        st.write(
            f"任务 #{task.id} · {task.title} · 责任岗位：{task.owner_role} · "
            f"状态：{task.status} · {'已发布' if task.confirmed else '草稿'}"
        )
        if not task.submissions:
            st.info("等待提交材料：执行人还没有提交交付物。")
        for submission in task.submissions:
            with st.expander(
                f"交付 #{submission.id} · {submission.review_status} · "
                f"证据 #{submission.evidence_id}"
            ):
                st.write(submission.content)
                st.code(submission.evidence_excerpt, language=None)
                st.caption(f"提交岗位：{submission.submitted_by_role}")
                if submission.review_status == "pending_review":
                    st.info("等待人工验收：请由有验收权限的其他人员检查材料。")
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
        st.info("等待后续评价：导入新一批评价后，再检查问题是否减少。")
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
    st.caption("同一主题、同一统计口径、不同批次；复检结果用于观察变化，不自动证明措施造成变化。")
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
st.set_page_config(page_title="客户反馈与质量改进 · TradeLoop", page_icon="〰️", layout="wide")
apply_brand_theme(require_auth=True)
render_page_header(
    "QUALITY INSIGHTS · 客户声音",
    "客户评价与改进",
    "从评价原文出发，区分统计、原因假设与人工结论，再连接改进任务和后续复检。",
)
st.info(
    "操作顺序：① 导入评价 → ② 选择规则或 AI 分析 → ③ 核对原文并审核问题 → "
    "④ 发布改进任务 → ⑤ 用新评价检查变化。"
)
st.caption(
    "这里上传的是客户反馈文件，例如评价编号、评价原文、评分和批次信息；本页面依据只代表客户反馈，不代表商品规格事实。"
)
project_id, role = render_sidebar()
if project_id is None:
    st.warning("请先进入一个项目。")
    st.stop()
render_role_boundary_notice(role)
token = st.session_state.get("auth_token", "")
product_id = select_product(project_id, token, owner=role == "项目负责人")


with st.expander("1 · 导入评价 CSV", expanded=not list_review_batches(project_id)):
    st.caption(
        "系统会自动识别常见列名；批次号缺失时自动生成。日期、SKU、市场和评价正文缺失时不会伪造。"
    )
    st.download_button(
        "下载评价 CSV 示例",
        data=REVIEW_TEMPLATE.read_bytes(),
        file_name="review_import_example.csv",
        mime="text/csv",
    )
    uploaded = st.file_uploader("评价文件", type=["csv"], key="review_csv")
    batch_name = st.text_input("批次名称", placeholder="例如：包装改进前 · 2026-10")
    preview = preview_review_csv(uploaded) if uploaded is not None else None
    confirmed = False
    if preview is not None:
        st.write("系统字段映射：", preview.column_mapping)
        if preview.missing_columns:
            st.info(
                "以下字段未在文件中识别到，系统会保留为空/未知，不会自行补全："
                + "、".join(preview.missing_columns)
            )
        if preview.errors:
            st.warning("；".join(f"{item.field}: {item.message}" for item in preview.errors[:8]))
        st.caption(f"可导入记录：{len(preview.rows)} · 无效记录：{len(preview.errors)}")
        confirmed = st.checkbox(
            "我已确认字段映射和数据来源，允许导入", disabled=not preview.is_valid
        )
    if st.button("校验并导入", type="primary", disabled=uploaded is None or not confirmed):
        try:
            result = import_reviews(
                project_id=project_id,
                source=uploaded,
                batch_name=batch_name,
                product_id=product_id,
                session_token=token,
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
model_readiness = check_model_readiness(runtime_config(settings))
model_configured = model_readiness.configured
st.caption("页面不提供在线测试按钮；模型请求只在用户主动点击分析时发起。")
if model_configured:
    st.caption("AI 已配置。点击分析会使用当前服务；更换服务请前往“设置”。")
else:
    st.warning("模型配置不完整或无效。真实 AI 分析不可用；不会自动改用规则结果。")

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
            st.success(f"规则分类已生成 {len(summaries)} 个主题统计；重复运行不会覆盖人工审核。")
    elif not model_configured:
        st.error("模型未配置，未发起 AI 请求，也未生成 AI 分析结果。请在“设置”中配置模型服务。")
    elif analyze_review_batch_with_model is None:
        st.error("真实 AI 分析接口未就绪。评价批次已保留，没有生成替代结果。")
    else:
        try:
            result = analyze_review_batch_with_model(
                project_id=project_id,
                batch_id=selected_batch_id,
            )
        except TradeLoopError as exc:
            code = getattr(exc, "code", "TRADELOOP_ERROR")
            render_user_error(exc, fallback=AI_ERROR_MESSAGES.get(code, "模型调用失败。"))
            st.info("本次真实 AI 请求失败；没有生成规则替代结果，原评价批次仍然保留。")
        except ValueError as exc:
            render_user_error(exc, fallback="AI 结果校验失败，未写入关键业务状态。")
            st.info("评价批次已保留；无效结构不会写入关键业务状态。")
        else:
            finding_ids = read_result_value(result, "finding_ids", default=[])
            status = read_result_value(result, "status", default="success")
            st.success(f"真实 AI 分类完成：状态 {status}，生成 {len(finding_ids)} 个待审核问题。")
            render_ai_run_summary(result)

st.markdown("**最近一次分析状态**")
st.caption("页面只展示最近一次结果；技术信息按需展开，避免信息过载。")
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
    st.markdown("### 3 · 查看问题、核对原文并审核")
    for finding in findings:
        if product_id and role == "项目负责人":
            if st.button(f"确认问题 #{finding.id} 属于当前产品", key=f"bind_finding_{finding.id}"):
                try:
                    assign_product(
                        project_id=project_id,
                        session_token=token,
                        product_id=product_id,
                        kind="finding",
                        entity_id=finding.id,
                    )
                    st.success("产品关联已确认；这不代表问题已获人工验收。")
                except (TradeLoopError, ValueError) as exc:
                    render_user_error(exc)
        theme = finding.finding_type.rsplit(":", maxsplit=1)[-1]
        label = THEME_LABELS.get(theme, theme)
        classification_label = "真实 AI" if finding.model_run_id else "规则分类"
        review_label = {
            "pending_review": "待你确认",
            "accepted": "已确认",
            "revised": "已修改确认",
            "rejected": "已忽略",
        }.get(finding.review_status, "待处理")
        with st.expander(
            f"{label} · {classification_label} · {finding.review_status}",
            expanded=True,
        ):
            st.write(finding.statement)
            st.caption(
                f"分析范围：{finding.sample_size or 0} 条评价 · "
                f"来源：{classification_label} · {review_label}"
            )
            if finding.model_run_id:
                st.warning("这是 AI 提出的待确认问题，不构成供应商、物流或员工责任认定。")
            else:
                st.caption("该问题来自可复现规则分类，不代表 AI 判断。")

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
                        render_user_error(exc, fallback="问题确认失败，请检查审核信息。")
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
                        render_user_error(exc, fallback="问题修改失败，请检查审核内容。")
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
                        render_user_error(exc, fallback="问题驳回失败，请填写审核理由。")
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
                        with session_context() as db:
                            from services.auth_service import require_session_member

                            _, member = require_session_member(token, project_id, session=db)
                            if member.role != "owner":
                                raise ProjectAccessDeniedError("只有负责人可以发布改进任务。")
                            task = create_task_from_finding(
                                project_id=project_id,
                                finding_id=finding.id,
                                session=db,
                            )
                            if task.status == "draft":
                                task = confirm_task(
                                    project_id=project_id,
                                    task_id=task.id,
                                    confirmer_role=role,
                                    session=db,
                                )
                            improvement = create_improvement_record(
                                project_id=project_id,
                                finding_id=finding.id,
                                task_id=task.id,
                                baseline_batch_id=selected_batch_id,
                                session=db,
                            )
                            if product_id:
                                assign_product(
                                    project_id=project_id,
                                    session_token=token,
                                    product_id=product_id,
                                    kind="improvement",
                                    entity_id=improvement.id,
                                    session=db,
                                )
                    except (TradeLoopError, ValueError) as exc:
                        render_user_error(exc, fallback="改进任务无法发布，请检查验收标准。")
                    else:
                        st.success(f"任务 #{task.id} 已发布，并建立改进基线。")
else:
    st.warning("当前批次尚未分析。")

if len(batches) >= 2:
    st.markdown("### 4 · 比较改进前后的评价")
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
