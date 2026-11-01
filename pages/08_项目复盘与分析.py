import streamlit as st

from core.auth_ui import get_authenticated_user
from core.db import init_db
from core.theme import apply_brand_theme, render_footer, render_page_header
from core.ui import render_sidebar
from services.task_service import list_daily_reports, list_tasks

init_db()
st.set_page_config(page_title="项目复盘与分析 · TradeLoop", page_icon="📊", layout="wide")
apply_brand_theme(require_auth=True)
render_page_header(
    "EXECUTION REVIEW · 项目复盘",
    "项目复盘与分析",
    "汇总任务、日报和交付状态，帮助负责人判断项目阶段性进展。",
)
project_id, role = render_sidebar()
if project_id is None or get_authenticated_user() is None:
    st.warning("请先进入一个授权项目。")
    st.stop()

tasks = list_tasks(project_id)
reports = list_daily_reports(project_id)
st.caption("这里是执行复盘入口；任务发布、交付验收和日报提交仍在“任务管理与日报”。")
first, second, third = st.columns(3)
first.metric("任务总数", len(tasks))
second.metric("已完成", sum(item.status == "done" for item in tasks))
third.metric("日报记录", len(reports))

st.subheader("任务执行概览")
if tasks:
    st.dataframe(
        [
            {
                "任务": item.title,
                "责任岗位": item.owner_role,
                "状态": item.status,
                "已发布": "是" if item.confirmed else "否",
            }
            for item in tasks
        ],
        hide_index=True,
        width="stretch",
    )
else:
    st.info("当前项目暂无任务。")

st.subheader("近期日报")
if reports:
    st.dataframe(
        [
            {
                "日期": item.report_date,
                "部门": item.role,
                "完成事项": item.completed,
                "阻塞事项": item.blocker,
                "下一步": item.next_plan,
            }
            for item in reports[:20]
        ],
        hide_index=True,
        width="stretch",
    )
else:
    st.info("当前项目暂无日报记录。")
render_footer()
