import streamlit as st

from core.db import init_db

st.set_page_config(
    page_title="TradeLoop",
    page_icon="🔁",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

st.title("TradeLoop")
st.caption("AI 跨境业务协同与持续改进平台 · Hackathon V1")

st.info("请从左侧进入“项目首页”。第一次使用可直接加载演示项目。")

st.markdown(
    """
### V1 演示链路

`项目 → 报价导入 → 确定性比较 → AI 决策摘要 → 人工确认 → 任务 → 日报 → 差评复检 → 本地化校验`

当前第一阶段已实现：

- 项目创建、访问码哈希存储与演示身份切换；
- 固定模板的供应商报价 CSV 校验、预览和持久化；
- 可解释的供应商加权评分与排名；
- 后续三个工作流页面和服务目录骨架。

所有 AI 建议在后续版本中都必须由负责人确认后才能进入正式任务。
"""
)

