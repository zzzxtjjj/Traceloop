import json

import streamlit as st

from core.db import init_db
from core.errors import TradeLoopError
from core.theme import apply_brand_theme, render_footer, render_page_header
from core.ui import render_sidebar
from services.task_service import (
    build_daily_risk_review,
    list_daily_reports,
    list_task_submissions,
    list_tasks,
    review_task_submission,
    submit_daily_report,
    submit_task_delivery,
    update_task_status,
)

init_db()
st.set_page_config(page_title="任务与日报 · TradeLoop", page_icon="🧭", layout="wide")
apply_brand_theme()
render_page_header(
    "PROJECT ROUTE · 协作航线",
    "任务、交付与日报复盘",
    "任务必须先发布，交付必须附证据，完成状态必须经过人工验收。",
)
project_id, role = render_sidebar()
if project_id is None:
    st.warning("请先进入一个项目。")
    st.stop()

st.write(f"当前演示身份：**{role}**")
tasks = list_tasks(project_id)
task_by_id = {task.id: task for task in tasks}

task_tab, report_tab, review_tab = st.tabs(["任务执行", "提交日报", "风险复盘"])

with task_tab:
    if not tasks:
        st.info("暂无任务。可先在“差评改进”页审核发现并发布改进任务。")
    for task in tasks:
        with st.expander(f"#{task.id} · {task.title} · {task.status}"):
            left, middle, right = st.columns(3)
            left.metric("责任岗位", task.owner_role)
            middle.metric("状态", task.status)
            right.metric("已发布", "是" if task.confirmed else "否")
            st.write("验收标准：")
            for criterion in json.loads(task.acceptance_criteria_json):
                st.write(f"- {criterion}")
            if task.dependency:
                st.caption("前置条件：" + task.dependency)

            can_work = role in {task.owner_role, "项目负责人"}
            if task.confirmed and task.status in {"todo", "doing", "blocked"}:
                status = st.selectbox(
                    "执行状态",
                    options=["todo", "doing", "blocked"],
                    index=["todo", "doing", "blocked"].index(task.status),
                    key=f"task_status_{task.id}",
                    disabled=not can_work,
                )
                if st.button("更新状态", key=f"update_task_{task.id}", disabled=not can_work):
                    try:
                        update_task_status(
                            project_id=project_id,
                            task_id=task.id,
                            status=status,
                            actor_role=role,
                        )
                    except TradeLoopError as exc:
                        st.error(str(exc))
                    else:
                        st.rerun()

                delivery = st.text_area(
                    "交付说明",
                    key=f"delivery_{task.id}",
                    disabled=not can_work,
                )
                delivery_evidence = st.text_area(
                    "验收材料/可核查引用",
                    key=f"delivery_evidence_{task.id}",
                    placeholder="例如测试编号、文件位置、订单号或原始记录摘要。",
                    disabled=not can_work,
                )
                if st.button(
                    "提交人工验收",
                    type="primary",
                    key=f"submit_delivery_{task.id}",
                    disabled=not can_work,
                ):
                    try:
                        submit_task_delivery(
                            project_id=project_id,
                            task_id=task.id,
                            submitted_by_role=role,
                            content=delivery,
                            evidence_excerpt=delivery_evidence,
                        )
                    except (TradeLoopError, ValueError) as exc:
                        st.error(str(exc))
                    else:
                        st.success("交付已提交；任务仍未完成，等待人工验收。")
                        st.rerun()

    submissions = list_task_submissions(project_id)
    pending = [item for item in submissions if item.review_status == "pending_review"]
    if pending:
        st.markdown("### 待验收交付")
        for submission in pending:
            task = task_by_id.get(submission.task_id)
            with st.expander(f"交付 #{submission.id} · {task.title if task else '未知任务'}"):
                st.write(submission.content)
                st.caption(f"交付证据 #{submission.evidence_id}")
                note = st.text_area("验收备注", key=f"submission_note_{submission.id}")
                accept_col, reject_col = st.columns(2)
                can_review = role == "项目负责人"
                if accept_col.button(
                    "验收通过",
                    key=f"submission_accept_{submission.id}",
                    disabled=not can_review,
                ):
                    review_task_submission(
                        project_id=project_id,
                        submission_id=submission.id,
                        decision="accepted",
                        reviewer=role,
                        note=note,
                    )
                    st.rerun()
                if reject_col.button(
                    "驳回补充",
                    key=f"submission_reject_{submission.id}",
                    disabled=not can_review,
                ):
                    try:
                        review_task_submission(
                            project_id=project_id,
                            submission_id=submission.id,
                            decision="rejected",
                            reviewer=role,
                            note=note,
                        )
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.rerun()

with report_tab:
    role_tasks = [
        task
        for task in tasks
        if task.confirmed and role in {task.owner_role, "项目负责人"}
    ]
    options = [None] + [task.id for task in role_tasks]
    report_task_id = st.selectbox(
        "关联任务（建议选择）",
        options=options,
        format_func=lambda item: (
            "未关联任务" if item is None else f"#{item} · {task_by_id[item].title}"
        ),
    )
    completed = st.text_area("今日完成")
    report_evidence = st.text_area("引用或记录位置", placeholder="日报文字不是任务验收材料。")
    blocker = st.text_area("阻塞事项")
    next_plan = st.text_area("下一步计划")
    if st.button("提交日报", type="primary"):
        try:
            submit_daily_report(
                project_id=project_id,
                role=role,
                task_id=report_task_id,
                completed=completed,
                evidence_text=report_evidence,
                blocker=blocker,
                next_plan=next_plan,
            )
        except (TradeLoopError, ValueError) as exc:
            st.error(str(exc))
        else:
            st.success("日报已记录；系统不会仅凭日报把任务判为完成。")
            st.rerun()

    reports = list_daily_reports(project_id)
    if reports:
        st.markdown("### 最近日报")
        for report in reports[:10]:
            st.write(
                f"#{report.id} · {report.role} · 任务 {report.task_id or '-'} · "
                f"{report.completed or report.blocker}"
            )

with review_tab:
    risks = build_daily_risk_review(project_id)
    if not risks:
        st.success("目前没有基于任务状态和日报记录生成的确定性提醒。")
    for risk in risks:
        if risk.severity == "red":
            st.error(risk.message)
        elif risk.severity == "yellow":
            st.warning(risk.message)
        else:
            st.info(risk.message)
        st.caption(
            f"任务 #{risk.task_id or '-'} · 日报 #{risk.report_id or '-'} · "
            f"证据 #{risk.evidence_id or '-'}"
        )
    st.caption("缺少日报只表示资料缺失，不代表员工未工作或表现不佳。")

render_footer()

