from pathlib import Path

import streamlit as st

from core.auth_ui import get_authenticated_user
from core.db import init_db
from core.display_language import translate
from core.theme import (
    apply_brand_theme,
    render_footer,
    render_page_header,
)

st.set_page_config(page_title="使用教学 · TradeLoop", page_icon="📖", layout="wide")
init_db()
apply_brand_theme()
if get_authenticated_user() is None:
    render_page_header(
        "TRADELOOP · SECURE WORKSPACE",
        "请先登录",
        "项目、成员、文件和业务数据只对已认证且属于项目成员的用户开放。",
    )
    st.info("请进入“项目交流”完成登录、注册或邮箱验证。")
    st.page_link("pages/06_项目群聊.py", label="登录 / 注册", icon="🔐")
    render_footer()
    st.stop()
render_page_header("GETTING STARTED", "使用教学", "从项目、协作、业务和执行四步完成跨境工作。")
language = st.session_state.get("display_language", "简体中文")
guide_file = "../docs/user/BL_TRADELOOP_BEGINNER_GUIDE.md"
guide = (Path(__file__).resolve().parent / "docs" / guide_file).read_text(encoding="utf-8")
intro, *sections = guide.split("\n## ")
st.markdown(intro)
for section in sections:
    heading, _, body = section.partition("\n")
    with st.expander(heading):
        st.markdown(body)
st.divider()
st.info(
    "先进入项目首页选择工作区，再使用项目交流、项目文件和 AI 助手处理资料；"
    "业务结果会回到任务与复盘中。"
)
for path, label in [
    ("pages/01_项目首页.py", "项目首页"),
    ("pages/06_项目群聊.py", "项目交流"),
    ("pages/07_AI文档理解.py", "文档与 AI 助手"),
    ("pages/09_AI文件分拣中心.py", "AI 文件分拣中心"),
    ("pages/02_报价决策.py", "供应商报价对比"),
    ("pages/04_差评改进.py", "客户反馈与质量改进"),
    ("pages/05_本地化与校验.py", "商品资料与多语言"),
    ("pages/03_任务与日报.py", "任务管理与日报"),
    ("pages/06_设置.py", "AI 服务配置"),
]:
    st.page_link(path, label=translate(label))
render_footer()
