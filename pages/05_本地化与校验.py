import difflib

import streamlit as st

from core.access_ui import render_role_boundary_notice, render_user_error
from core.db import init_db
from core.errors import RuleSourceError, TradeLoopError
from core.theme import apply_brand_theme, render_footer, render_page_header
from core.ui import render_sidebar
from services.localization_service import (
    create_v1_generation,
    create_v2_generation,
    list_generations,
)
from services.rule_service import run_rule_checks

init_db()
st.set_page_config(page_title="本地化与校验 · TradeLoop", page_icon="✉️", layout="wide")
apply_brand_theme()
render_page_header(
    "GLOBAL MARKET LETTERS · 全球市场信笺",
    "内容版本与跨市场规则校验",
    "保留人工内容的 V1、反馈和 V2 版本链，并让规则检查独立、可追溯地运行。",
)
project_id, role = render_sidebar()
if project_id is None:
    st.warning("请先进入一个项目。")
    st.stop()
render_role_boundary_notice(role)

version_tab, rule_tab = st.tabs(["内容版本闭环", "独立规则校验"])

with version_tab:
    st.info(
        "当前版本不调用真实大模型。V1 和 V2 均由用户人工填写并保存；"
        "系统只负责版本关联、反馈记录和差异展示，不会把人工内容冒充为 AI 生成。"
    )
    version_market = st.selectbox(
        "目标市场",
        options=["US", "DE"],
        format_func=lambda item: "美国英语" if item == "US" else "德国德语",
        key="version_market",
    )
    st.markdown("### 1 · 保存 V1")
    v1_content = st.text_area(
        "V1 内容",
        height=160,
        placeholder="粘贴或填写第一版商品标题、卖点或市场文案。",
        key="v1_content",
    )
    if st.button("保存人工 V1", type="primary"):
        try:
            generation = create_v1_generation(
                project_id=project_id,
                market=version_market,
                content=v1_content,
            )
        except (TradeLoopError, ValueError) as exc:
            render_user_error(exc, fallback="V1 保存失败，请检查市场和内容。")
        else:
            st.success(f"V1 #{generation.id} 已保存。")
            st.rerun()

    generations = list_generations(project_id, market=version_market)
    roots = [item for item in generations if item.version == 1 and item.parent_id is None]
    children = {item.parent_id: item for item in generations if item.version == 2}

    if not roots:
        st.caption("当前市场还没有 V1。保存 V1 后即可记录反馈并创建 V2。")
    else:
        st.markdown("### 2 · 反馈并创建 V2")
        root_by_id = {item.id: item for item in roots}
        selected_v1_id = st.selectbox(
            "选择 V1",
            options=list(root_by_id),
            format_func=lambda item: f"V1 #{item} · {root_by_id[item].content[:40]}",
        )
        selected_v1 = root_by_id[selected_v1_id]
        st.code(selected_v1.content, language=None)
        existing_v2 = children.get(selected_v1.id)
        if existing_v2:
            st.info(f"该 V1 已有关联 V2 #{existing_v2.id}。版本链不会被重复覆盖。")
        else:
            feedback = st.text_area(
                "修改反馈",
                placeholder="说明需要修改的语气、事实、长度或市场表达。",
                key=f"feedback_{selected_v1.id}",
            )
            v2_content = st.text_area(
                "V2 内容",
                height=160,
                placeholder="根据反馈人工填写修改后的第二版内容。",
                key=f"v2_content_{selected_v1.id}",
            )
            if st.button("保存反馈和人工 V2", type="primary"):
                try:
                    generation = create_v2_generation(
                        project_id=project_id,
                        parent_id=selected_v1.id,
                        feedback=feedback,
                        content=v2_content,
                    )
                except (TradeLoopError, ValueError) as exc:
                    render_user_error(exc, fallback="V2 保存失败，请检查反馈和内容。")
                else:
                    st.success(
                        f"V2 #{generation.id} 已保存，parent_id 指向 V1 #{selected_v1.id}。"
                    )
                    st.rerun()

        st.markdown("### 3 · 查询版本链")
        for v1 in reversed(roots):
            v2 = children.get(v1.id)
            label = f"{v1.market} · V1 #{v1.id}"
            if v2:
                label += f" → V2 #{v2.id}"
            else:
                label += " · 待迭代"
            with st.expander(label):
                st.caption(
                    f"语言：{v1.language} · 记录方式：人工内容 · Prompt 标记：{v1.prompt_version}"
                )
                st.markdown("**V1**")
                st.code(v1.content, language=None)
                if v2:
                    st.markdown("**反馈**")
                    st.write(v2.feedback)
                    st.markdown("**V2**")
                    st.code(v2.content, language=None)
                    diff = "\n".join(
                        difflib.unified_diff(
                            v1.content.splitlines(),
                            v2.content.splitlines(),
                            fromfile=f"V1 #{v1.id}",
                            tofile=f"V2 #{v2.id}",
                            lineterm="",
                        )
                    )
                    st.markdown("**V1 与 V2 差异**")
                    st.code(diff or "内容无文本差异", language="diff")
                else:
                    st.warning("尚无 V2；系统不会创建空版本。")

with rule_tab:
    st.info(
        "规则检查是独立的确定性检查，不提供法律意见，也不会把“未命中规则”描述为全面合规。"
        "所有结果都需要人工复核。"
    )
    market = st.selectbox(
        "市场",
        options=["US", "DE"],
        format_func=lambda item: "美国" if item == "US" else "德国",
        key="rule_market",
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
        key="rule_content",
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
            render_user_error(exc, fallback="规则检查失败，请检查输入文本。")
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

render_footer()
