import streamlit as st

from core.db import init_db
from core.theme import apply_brand_theme, render_footer, render_page_header
from core.ui import render_sidebar

init_db()
st.set_page_config(page_title="本地化与校验 · TradeLoop", page_icon="✉️", layout="wide")
apply_brand_theme()
render_page_header(
    "GLOBAL MARKET LETTERS · 全球市场信笺",
    "本地化与校验",
    "并列审阅美国与德国市场内容，用版本差异、规则批注和风险状态支持人工判断。",
)
project_id, role = render_sidebar()
if project_id is None:
    st.warning("请先进入一个项目。")
    st.stop()

st.info("页面骨架已建立，将在第四阶段接入：美国英语/德国德语 V1 → 用户反馈 → V2 → 两类规则校验。")
render_footer()

