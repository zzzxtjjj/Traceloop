import base64
import html
from functools import lru_cache
from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitPageNotFoundError

ROOT_DIR = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _harbor_data_uri() -> str:
    raw = (ROOT_DIR / "assets" / "harbor-hero.svg").read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")


GLOBAL_CSS = """
<style>
:root {
  --tl-ink: #263B46;
  --tl-copy: #4C514F;
  --tl-muted: #7C8583;
  --tl-paper: #FFFCF7;
  --tl-cream: #F8F5EF;
  --tl-mist: #F1F2ED;
  --tl-sea-pale: #DCEAF0;
  --tl-sea: #BFD9E2;
  --tl-jade: #A8C5C2;
  --tl-navy: #29485A;
  --tl-coral: #E77D66;
  --tl-vermilion: #C75C48;
  --tl-gold: #C6A36A;
  --tl-line: rgba(41, 72, 90, .16);
  --tl-shadow: 0 18px 48px rgba(41, 72, 90, .08);
  --tl-serif: "Noto Serif SC", "Source Han Serif SC", "Songti SC", STSong, SimSun, serif;
  --tl-sans: "Noto Sans SC", "Source Han Sans SC", "Microsoft YaHei", Arial, sans-serif;
}

html, body { font-family: var(--tl-sans); }
.stApp {
  color: var(--tl-copy);
  background:
    radial-gradient(circle at 92% 4%, rgba(191,217,226,.38), transparent 25rem),
    radial-gradient(circle at 6% 88%, rgba(198,163,106,.10), transparent 24rem),
    var(--tl-cream);
}
[data-testid="stMainBlockContainer"] {
  max-width: 1240px;
  padding-top: 2.1rem;
  padding-bottom: 5rem;
}
h1, h2, h3, .tl-serif { font-family: var(--tl-serif); color: var(--tl-ink); }
h1 { letter-spacing: -.035em; font-weight: 650; }
h2 { letter-spacing: -.02em; }
p, label, li { color: var(--tl-copy); }
a { color: var(--tl-vermilion); }
hr { border-color: var(--tl-line) !important; }

[data-testid="stSidebar"] {
  background:
    linear-gradient(180deg, rgba(220,234,240,.62), rgba(248,245,239,.94) 42%),
    var(--tl-cream);
  border-right: 1px solid var(--tl-line);
  overflow-x: clip !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
  padding-top: 1rem;
  overflow-x: hidden;
}
[data-testid="stSidebar"] * { max-width: 100%; }
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebar"] button[aria-label="Collapse sidebar"] { display: none !important; }
[data-testid="stSidebarNav"] { display: none; }
[data-testid="stPageLink"] a {
  border-radius: 10px;
  margin: 2px 0;
  color: var(--tl-ink);
}
[data-testid="stPageLink"] a:hover { background: rgba(191,217,226,.46); }

.tl-sidebar-brand { padding: .35rem .2rem 1rem; }
.tl-sidebar-brand__mark {
  display: inline-flex; align-items: center; gap: .65rem;
  font-family: var(--tl-serif); font-size: 1.35rem; color: var(--tl-ink); font-weight: 700;
}
.tl-sidebar-brand__mark::before {
  content: ""; width: 30px; height: 30px; border-radius: 50%;
  background: linear-gradient(145deg, var(--tl-coral), var(--tl-gold));
  box-shadow: inset 0 0 0 8px rgba(255,252,247,.65);
}
.tl-sidebar-brand__sub { margin-top: .35rem; color: var(--tl-muted); font-size: .75rem; letter-spacing: .08em; }

.tl-hero {
  position: relative; overflow: hidden; display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(300px, .95fr);
  gap: 2.2rem; align-items: center; min-height: 410px;
  padding: clamp(2rem, 5vw, 4.2rem); margin: .25rem 0 2rem;
  background: linear-gradient(135deg, rgba(255,252,247,.96), rgba(238,245,245,.88));
  border: 1px solid rgba(41,72,90,.14); border-radius: 32px;
  box-shadow: var(--tl-shadow);
}
.tl-hero::before {
  content: ""; position: absolute; width: 280px; height: 280px; left: -150px; bottom: -180px;
  border: 1px solid rgba(198,163,106,.34); border-radius: 50%; box-shadow: 0 0 0 28px rgba(198,163,106,.06);
}
.tl-kicker {
  display: inline-flex; align-items: center; gap: .55rem; margin-bottom: 1.2rem;
  color: var(--tl-vermilion); font-size: .76rem; font-weight: 750; letter-spacing: .16em;
}
.tl-kicker::before { content: ""; width: 34px; height: 1px; background: var(--tl-gold); }
.tl-hero h1 { margin: 0; max-width: 640px; font-size: clamp(2.25rem, 3.8vw, 3.5rem); line-height: 1.1; }
.tl-hero p { max-width: 600px; margin: 1.35rem 0 0; font-size: 1.08rem; line-height: 1.9; }
.tl-hero__note { margin-top: 1.5rem; color: var(--tl-muted); font-size: .84rem; letter-spacing: .04em; }
.tl-hero__art img { display: block; width: 100%; filter: drop-shadow(0 22px 28px rgba(41,72,90,.12)); }

.tl-page-head {
  position: relative; overflow: hidden; margin: .2rem 0 1.8rem; padding: 1.8rem 2rem 1.7rem;
  background: linear-gradient(105deg, rgba(255,252,247,.97), rgba(220,234,240,.58));
  border-top: 1px solid var(--tl-line); border-bottom: 1px solid var(--tl-line);
}
.tl-page-head::after {
  content: ""; position: absolute; right: -30px; bottom: -54px; width: 250px; height: 120px;
  border: 2px solid rgba(168,197,194,.54); border-radius: 50%; box-shadow: 0 0 0 15px rgba(191,217,226,.12);
}
.tl-page-head h1 { position: relative; z-index: 1; margin: .25rem 0 .45rem; font-size: clamp(2rem, 4vw, 3.3rem); }
.tl-page-head p { position: relative; z-index: 1; max-width: 760px; margin: 0; line-height: 1.7; }
.tl-page-head__meta { position: relative; z-index: 1; color: var(--tl-vermilion); font-size: .72rem; font-weight: 800; letter-spacing: .16em; }

.tl-route {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px; overflow: hidden;
  margin: 1.4rem 0 2rem; background: var(--tl-line); border: 1px solid var(--tl-line); border-radius: 16px;
}
.tl-route__item { padding: 1rem 1.1rem; background: rgba(255,252,247,.9); }
.tl-route__index { color: var(--tl-coral); font-family: var(--tl-serif); font-size: 1.35rem; }
.tl-route__label { color: var(--tl-ink); font-weight: 650; font-size: .86rem; }
.tl-route__sub { color: var(--tl-muted); font-size: .72rem; margin-top: .2rem; }

.tl-security-note {
  margin: .5rem 0 1.25rem; padding: 1.1rem 1.25rem;
  background: rgba(220,234,240,.45); border-left: 3px solid var(--tl-gold); border-radius: 0 14px 14px 0;
}
.tl-security-note strong { color: var(--tl-ink); }
.tl-security-note p { margin: .25rem 0 0; font-size: .86rem; line-height: 1.65; }

div[data-testid="stForm"], div[data-testid="stExpander"] {
  background: rgba(255,252,247,.9); border: 1px solid var(--tl-line) !important;
  border-radius: 18px; box-shadow: 0 10px 30px rgba(41,72,90,.055);
}
div[data-testid="stForm"] { padding: 1.25rem 1.35rem .55rem; }
div[data-testid="stVerticalBlockBorderWrapper"] {
  border-color: var(--tl-line) !important; border-radius: 18px !important;
}
[data-testid="stMetric"] {
  background: rgba(255,252,247,.82); border: 1px solid var(--tl-line);
  border-radius: 15px; padding: .85rem 1rem; box-shadow: 0 8px 22px rgba(41,72,90,.04);
}
[data-testid="stMetricValue"] { font-family: var(--tl-serif); color: var(--tl-ink); }

.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {
  border-radius: 999px !important; border: 1px solid rgba(199,92,72,.26) !important;
  font-weight: 700 !important; letter-spacing: .015em;
  transition: transform .16s ease, box-shadow .16s ease, background .16s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
  transform: translateY(-1px); box-shadow: 0 8px 20px rgba(199,92,72,.14);
}
button[kind="primary"] { background: var(--tl-vermilion) !important; color: white !important; }

[data-baseweb="input"] > div, [data-baseweb="select"] > div, [data-baseweb="base-input"], textarea {
  background: rgba(255,252,247,.95) !important; border-color: rgba(41,72,90,.18) !important;
  border-radius: 11px !important;
}
[data-baseweb="input"] > div:focus-within, [data-baseweb="select"] > div:focus-within {
  border-color: var(--tl-coral) !important; box-shadow: 0 0 0 2px rgba(231,125,102,.12) !important;
}
[data-testid="stFileUploaderDropzone"] {
  background: rgba(220,234,240,.25); border-color: rgba(41,72,90,.22); border-radius: 16px;
}
[data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"] { display: none; }
[data-testid="stFileUploaderDropzone"] button p { font-size: 0; }
[data-testid="stFileUploaderDropzone"] button p::after {
  content: "选择文件";
  font-size: .875rem;
}
[data-testid="stDataFrame"] { border: 1px solid var(--tl-line); border-radius: 14px; overflow: hidden; }
[data-baseweb="tab-list"] { gap: .5rem; border-bottom: 1px solid var(--tl-line); }
[data-baseweb="tab"] { border-radius: 10px 10px 0 0; padding-left: 1rem; padding-right: 1rem; }
[aria-selected="true"][data-baseweb="tab"] { background: rgba(220,234,240,.52); color: var(--tl-ink); }
[data-testid="stAlert"] { border-radius: 14px; border: 1px solid rgba(41,72,90,.10); }

.tl-footer {
  margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--tl-line);
  color: var(--tl-muted); font-size: .73rem; letter-spacing: .08em;
}

@media (max-width: 820px) {
  [data-testid="stMainBlockContainer"] { padding-left: 1rem; padding-right: 1rem; }
  .tl-hero { grid-template-columns: 1fr; padding: 2rem 1.4rem; border-radius: 22px; }
  .tl-route { grid-template-columns: 1fr 1fr; }
  .tl-page-head { padding: 1.4rem 1rem; }
}
@media (max-width: 520px) {
  .tl-route { grid-template-columns: 1fr; }
  .tl-hero h1 { font-size: 2.45rem; }
}
</style>
"""


def apply_brand_theme() -> None:
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def render_sidebar_brand() -> None:
    st.sidebar.markdown(
        """
        <div class="tl-sidebar-brand">
          <div class="tl-sidebar-brand__mark">TradeLoop</div>
          <div class="tl-sidebar-brand__sub">NINGBO · GLOBAL TRADE</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_navigation() -> None:
    render_sidebar_brand()
    links = [
        ("app.py", "总览"),
        ("pages/01_项目首页.py", "项目首页"),
        ("pages/02_报价决策.py", "报价决策"),
        ("pages/03_任务与日报.py", "任务与日报"),
        ("pages/04_差评改进.py", "差评改进"),
        ("pages/05_本地化与校验.py", "本地化与校验"),
    ]
    try:
        for path, label in links:
            st.sidebar.page_link(path, label=label)
    except StreamlitPageNotFoundError:
        # AppTest can execute a page outside its normal multipage entrypoint.
        # The production app always resolves these links through app.py.
        pass
    st.sidebar.divider()


def render_hero() -> None:
    st.markdown(
        f"""
        <section class="tl-hero">
          <div class="tl-hero__copy">
            <div class="tl-kicker">NINGBO · GLOBAL TRADE OPERATIONS</div>
            <h1>让每一次<br>跨境协作，<br>都有迹可循。</h1>
            <p>从供应商决策到客户反馈，让项目事实、岗位行动与市场规则沿着同一条航线持续改进。</p>
            <div class="tl-hero__note">海港连接世界 · 数据沉淀知识 · AI 辅助决策</div>
          </div>
          <div class="tl-hero__art">
            <img src="{_harbor_data_uri()}" alt="港口、货船与全球贸易航线线稿插画">
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(kicker: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <header class="tl-page-head">
          <div class="tl-page-head__meta">{html.escape(kicker)}</div>
          <h1>{html.escape(title)}</h1>
          <p>{html.escape(subtitle)}</p>
        </header>
        """,
        unsafe_allow_html=True,
    )


def render_route_strip() -> None:
    steps = [
        ("01", "供应商决策", "报价与风险"),
        ("02", "协同执行", "任务与日报"),
        ("03", "客户声音", "洞察与改进"),
        ("04", "全球适配", "生成与校验"),
    ]
    content = "".join(
        '<div class="tl-route__item">'
        f'<div class="tl-route__index">{index}</div>'
        f'<div class="tl-route__label">{label}</div>'
        f'<div class="tl-route__sub">{sub}</div>'
        "</div>"
        for index, label, sub in steps
    )
    st.markdown(f'<div class="tl-route">{content}</div>', unsafe_allow_html=True)


def render_security_note() -> None:
    st.markdown(
        """
        <div class="tl-security-note">
          <strong>演示级访问控制</strong>
          <p>当前访问码以哈希保存并用于项目隔离。正式产品应升级为成员邀请 + 设备 Passkey，
          由 Windows Hello、Touch ID 或手机生物识别在设备本地完成验证，服务端不保存人脸模板。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer() -> None:
    st.markdown(
        '<div class="tl-footer">TRADELOOP · TRACEABLE CROSS-BORDER COLLABORATION</div>',
        unsafe_allow_html=True,
    )

