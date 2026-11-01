import json
from datetime import date

import streamlit as st

from core.access_ui import render_role_boundary_notice, render_user_error
from core.auth_ui import get_authenticated_user
from core.db import init_db
from core.errors import TradeLoopError
from core.theme import apply_brand_theme, render_footer, render_page_header
from core.ui import render_sidebar
from services.membership_service import list_project_members, list_users
from services.task_service import (
    create_manual_task,
    list_daily_reports,
    list_task_submissions,
    list_tasks,
    review_task_submission_as_user,
    submit_daily_report_as_user,
    submit_task_delivery_as_user,
    update_task_status_as_user,
)

init_db()
st.set_page_config(page_title="任务管理与日报 · TradeLoop", page_icon="🧭", layout="wide")
apply_brand_theme(require_auth=True)
render_page_header(
    "PROJECT ROUTE · 协作航线",
    "任务、交付与日报复盘",
    "任务必须先发布，交付必须附证据，完成状态必须经过人工验收。",
)
st.info(
    "执行人：选择任务并提交交付材料。审核人：检查材料后通过或退回。只有验收通过，任务才算完成。日报用于记录进度。"
)
project_id, role = render_sidebar()
if project_id is None:
    st.warning("请先进入一个项目。")
    st.stop()

render_role_boundary_notice(role)
current_user = get_authenticated_user()
auth_token = st.session_state.get("auth_token", "")
tasks = list_tasks(project_id)
task_by_id = {task.id: task for task in tasks}

if role == "项目负责人":
    st.subheader("＋ 新建任务")
    members = list_project_members(project_id, current_user.id)
    users = {item.id: item for item in list_users(include_inactive=False)}
    member_options = [item.user_id for item in members if item.user_id in users]
    with st.form("manual_task_form", clear_on_submit=True):
        title = st.text_input("任务名称", placeholder="例如：确认德国市场包装文案")
        description = st.text_area("任务描述")
        assignee = st.selectbox(
            "任务负责人", options=member_options, format_func=lambda item: users[item].display_name
        )
        priority = st.selectbox(
            "优先级",
            ["low", "medium", "high", "urgent"],
            format_func={"low": "低", "medium": "中", "high": "高", "urgent": "紧急"}.get,
        )
        due_date = st.date_input("截止日期", value=date.today())
        delivery = st.text_area("交付要求", placeholder="说明需要提交的文件、记录或结果")
        criteria_text = st.text_area("验收标准", placeholder="每行一条，例如：负责人核对原始资料")
        create = st.form_submit_button("创建并发布任务", type="primary")
    if create:
        try:
            task = create_manual_task(
                project_id=project_id,
                session_token=auth_token,
                title=title,
                description=f"{description.strip()}\n交付要求：{delivery.strip()}".strip(),
                assignee_user_id=assignee,
                priority=priority,
                due_date=due_date,
                acceptance_criteria=criteria_text.splitlines(),
            )
            st.success(f"任务 #{task.id} 已创建并发布。")
            st.rerun()
        except (TradeLoopError, ValueError) as exc:
            render_user_error(exc, fallback="任务创建失败，请检查必填项。")

task_tab, report_tab = st.tabs(["任务执行", "提交日报"])

counts = {
    key: sum(item.status == key for item in tasks)
    for key in ["todo", "doing", "pending_review", "rejected", "completed"]
}
st.caption("任务统计：" + " · ".join(f"{key} {value}" for key, value in counts.items()))

with task_tab:
    if not tasks:
        st.info("暂无任务。可先在“客户反馈与质量改进”页审核发现并发布改进任务。")
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

            can_work = role == "项目负责人" or task.assignee_user_id in {None, current_user.id}
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
                        update_task_status_as_user(
                            project_id=project_id,
                            task_id=task.id,
                            status=status,
                            session_token=auth_token,
                        )
                    except TradeLoopError as exc:
                        render_user_error(exc)
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
                        submit_task_delivery_as_user(
                            project_id=project_id,
                            task_id=task.id,
                            session_token=auth_token,
                            content=delivery,
                            evidence_excerpt=delivery_evidence,
                        )
                    except (TradeLoopError, ValueError) as exc:
                        render_user_error(exc, fallback="交付提交失败，请检查交付材料。")
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
                    try:
                        review_task_submission_as_user(
                            project_id=project_id,
                            submission_id=submission.id,
                            session_token=auth_token,
                            decision="accepted",
                            note=note,
                        )
                    except (TradeLoopError, ValueError) as exc:
                        render_user_error(exc, fallback="验收操作失败，请检查审核信息。")
                    else:
                        st.rerun()
                if reject_col.button(
                    "驳回补充",
                    key=f"submission_reject_{submission.id}",
                    disabled=not can_review,
                ):
                    try:
                        review_task_submission_as_user(
                            project_id=project_id,
                            submission_id=submission.id,
                            session_token=auth_token,
                            decision="rejected",
                            note=note,
                        )
                    except (TradeLoopError, ValueError) as exc:
                        render_user_error(exc, fallback="验收操作失败，请检查审核信息。")
                    else:
                        st.rerun()

with report_tab:
    st.markdown("### 参与的项目")
    st.caption("这里记录你在当前项目中的工作；岗位来自项目成员设置，不需要重复选择。")
    role_tasks = [
        task
        for task in tasks
        if task.confirmed
        and (role == "项目负责人" or task.assignee_user_id in {None, current_user.id})
        and task.status != "completed"
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
            submit_daily_report_as_user(
                project_id=project_id,
                session_token=auth_token,
                task_id=report_task_id,
                completed=completed,
                evidence_text=report_evidence,
                blocker=blocker,
                next_plan=next_plan,
            )
        except (TradeLoopError, ValueError) as exc:
            render_user_error(exc, fallback="日报提交失败，请检查填写内容。")
        else:
            st.success("日报已记录；系统不会仅凭日报把任务判为完成。")
            st.rerun()

    st.markdown("### 我的部门")
    st.info(f"当前部门：{role}。日报会自动带上这个部门，负责人无需代填岗位。")
    reports = list_daily_reports(project_id)
    if reports:
        st.markdown("### 最近日报")
        for report in reports[:10]:
            st.write(
                f"#{report.id} · 部门：{report.role} · 任务 {report.task_id or '-'} · "
                f"{report.completed or report.blocker}"
            )

render_footer()
