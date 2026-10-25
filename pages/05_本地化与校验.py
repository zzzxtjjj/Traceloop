import streamlit as st

from core.db import init_db
from core.errors import RuleSourceError
from core.theme import apply_brand_theme, render_footer, render_page_header
from core.ui import render_sidebar
from services.rule_service import run_rule_checks

init_db()
st.set_page_config(page_title="本地化与校验 · TradeLoop", page_icon="✉️", layout="wide")
apply_brand_theme()
render_page_header(
    "GLOBAL MARKET LETTERS · 全球市场信笺",
    "跨市场规则校验",
    "将平台商品信息、消费者合同信息与内部采购标准分开检查，并保留规则来源和版本。",
)
project_id, role = render_sidebar()
if project_id is None:
    st.warning("请先进入一个项目。")
    st.stop()

st.info(
    "此页面提供确定性文本检查，不提供法律意见，也不会把“未命中规则”描述为全面合规。"
    "所有结果都需要人工复核。"
)

market = st.selectbox(
    "市场",
    options=["US", "DE"],
    format_func=lambda item: "美国" if item == "US" else "德国",
)
scenario_labels = {
    "platform_product": "平台商品标题",
    "consumer_contract": "消费者合同/购买信息",
    "procurement": "内部采购条款",
}
scenario = st.selectbox(
    "业务场景",
    options=list(scenario_labels),
    format_func=lambda item: scenario_labels[item],
)
if market == "US" and scenario == "consumer_contract":
    st.warning("当前规则库尚无已核实的美国消费者合同检查；运行时会明确提示未覆盖。")

content = st.text_area(
    "待检查文本",
    height=220,
    placeholder=(
        "商品标题示例：Stainless Steel Bottle 750 ml\n"
        "或条款示例：Gesamtpreis ... Lieferkosten ..."
    ),
)
if st.button("运行规则检查", type="primary"):
    try:
        results = run_rule_checks(
            project_id=project_id,
            market=market,
            scenario=scenario,
            text=content,
        )
    except (RuleSourceError, ValueError) as exc:
        st.error(str(exc))
    else:
        for result in results:
            heading = f"{result.rule_id} · {result.status}"
            if result.status == "failed":
                st.error(heading)
            elif result.status in {"warning", "not_covered"}:
                st.warning(heading)
            else:
                st.success(heading)
            st.write(result.explanation)
            if result.matched_text:
                st.code(result.matched_text, language=None)
            source_label = (
                "平台政策"
                if result.rule_type == "platform_policy"
                else "消费者信息规则"
                if result.rule_type == "legal_information"
                else "TradeLoop 内部标准"
            )
            if result.source_reference.startswith("http"):
                st.markdown(
                    f"来源类型：{source_label} · "
                    f"[打开来源]({result.source_reference}) · 版本：{result.source_version}"
                )
            else:
                st.caption(
                    f"来源类型：{source_label} · 来源：{result.source_reference} · "
                    f"版本：{result.source_version}"
                )
            st.caption("人工复核状态：待复核")

st.divider()
st.caption(
    "本阶段未接入真实大模型，因此不会把模板或规则输出冒充为 AI 本地化文案。"
    "后续可在配置模型供应商后接入版本生成，但规则校验仍保持程序化。"
)
render_footer()

