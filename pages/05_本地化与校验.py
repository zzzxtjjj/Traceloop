import streamlit as st

from core.db import init_db
from core.ui import render_sidebar

init_db()
st.set_page_config(page_title="本地化与校验 · TradeLoop", page_icon="🌍", layout="wide")
st.title("本地化与校验")
project_id, role = render_sidebar()
if project_id is None:
    st.warning("请先进入一个项目。")
    st.stop()

st.info("页面骨架已建立，将在第四阶段接入：美国英语/德国德语 V1 → 用户反馈 → V2 → 两类规则校验。")

