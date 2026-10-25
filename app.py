import streamlit as st

from core.db import init_db
from core.theme import (
    apply_brand_theme,
    render_footer,
    render_hero,
    render_route_strip,
    render_sidebar_navigation,
)

st.set_page_config(
    page_title="TradeLoop",
    page_icon="🔁",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
apply_brand_theme()
render_sidebar_navigation()

render_hero()
render_route_strip()

left, right = st.columns([1.05, 0.95], gap="large")
with left:
    st.subheader("从一个项目事实源开始")
    st.write(
        "项目、供应商报价、岗位任务、客户反馈与市场规则不再分散。"
        "请从左侧进入“项目首页”，第一次使用可以直接加载演示项目。"
    )
    st.info("当前第一阶段已开放项目空间、报价导入与可解释评分。")

with right:
    st.subheader("当前航线")
    st.markdown(
        """
        1. 创建或进入项目
        2. 导入供应商报价
        3. 调整权重并比较
        4. 后续接入 AI 摘要与人工确认
        """
    )
    st.caption("所有 AI 建议都必须由负责人确认后才能进入正式任务。")

render_footer()

