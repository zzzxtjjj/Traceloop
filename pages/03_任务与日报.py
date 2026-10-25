import streamlit as st

from core.db import init_db
from core.ui import render_sidebar

init_db()
st.set_page_config(page_title="任务与日报 · TradeLoop", page_icon="✅", layout="wide")
st.title("任务与日报")
project_id, role = render_sidebar()
if project_id is None:
    st.warning("请先进入一个项目。")
    st.stop()

st.info("页面骨架已建立，将在第二阶段接入：AI 任务草稿 → 人工确认 → 角色任务 → 日报风险复盘。")
st.write(f"当前演示身份：**{role}**")

