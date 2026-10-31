from pathlib import Path

import streamlit as st

from core.db import init_db
from core.display_language import translate
from core.theme import (
    apply_brand_theme,
    render_footer,
    render_page_header,
    render_sidebar_navigation,
)

st.set_page_config(page_title="使用教学 · TradeLoop", page_icon="📖", layout="wide")
init_db()
apply_brand_theme()
render_sidebar_navigation()
render_page_header("GETTING STARTED", "使用教学", "了解六个板块，按步骤完成业务处理。")
language = st.session_state.get("display_language", "简体中文")
guide_file = {"English": "USER_GUIDE.en.md", "Deutsch": "USER_GUIDE.de.md"}.get(
    language, "USER_GUIDE.md"
)
guide = (Path(__file__).resolve().parent / "docs" / guide_file).read_text(encoding="utf-8")
intro, *sections = guide.split("\n## ")
st.markdown(intro)
for section in sections:
    heading, _, body = section.partition("\n")
    with st.expander(heading):
        st.markdown(body)
st.divider()
for path, label in [
    ("pages/01_项目首页.py", "项目首页"),
    ("pages/02_报价决策.py", "报价决策"),
    ("pages/03_任务与日报.py", "任务与日报"),
    ("pages/04_差评改进.py", "差评改进"),
    ("pages/05_本地化与校验.py", "本地化与校验"),
    ("pages/06_设置.py", "设置"),
    ("pages/07_AI文档理解.py", "AI 文档理解"),
]:
    st.page_link(path, label=translate(label))
render_footer()
