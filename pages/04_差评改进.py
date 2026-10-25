import streamlit as st

from core.db import init_db
from core.theme import apply_brand_theme, render_footer, render_page_header
from core.ui import render_sidebar

init_db()
st.set_page_config(page_title="差评改进 · TradeLoop", page_icon="〰️", layout="wide")
apply_brand_theme()
render_page_header(
    "QUALITY INSIGHTS · 客户声音",
    "差评改进",
    "从原始评价证据出发，连接问题主题、改进任务与下一批复检。",
)
project_id, role = render_sidebar()
if project_id is None:
    st.warning("请先进入一个项目。")
    st.stop()

st.info("页面骨架已建立，将在第三阶段接入：批次 A 证据分析 → 改进任务 → 批次 B 同口径复检。")
render_footer()

