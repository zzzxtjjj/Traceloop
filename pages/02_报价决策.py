from pathlib import Path

import pandas as pd
import streamlit as st

from core.db import init_db
from core.ui import render_sidebar
from services.imports import (
    QuoteImportValidationError,
    get_quotes,
    import_quotes,
    list_quote_artifacts,
    preview_quote_csv,
)
from services.supplier_scoring import DEFAULT_WEIGHTS, calculate_supplier_scores

init_db()
TEMPLATE_FILE = Path(__file__).resolve().parents[1] / "data" / "demo" / "supplier_quotes.csv"

st.set_page_config(page_title="报价决策 · TradeLoop", page_icon="📊", layout="wide")
st.title("报价决策")
st.caption("先由代码做可复现的加权比较，再由 AI 补充决策摘要（下一阶段）。")

project_id, role = render_sidebar()
if project_id is None:
    st.warning("请在左侧输入访问码，或先到项目首页创建项目。")
    st.stop()

upload_tab, score_tab = st.tabs(["1. 导入报价", "2. 比较与排名"])

with upload_tab:
    st.subheader("报价 CSV")
    st.download_button(
        "下载模板",
        data=TEMPLATE_FILE.read_bytes(),
        file_name="supplier_quotes_template.csv",
        mime="text/csv",
    )
    uploaded = st.file_uploader("上传报价 CSV", type=["csv"])
    batch_name = st.text_input("批次名称", value="供应商报价")

    if uploaded is not None:
        preview = preview_quote_csv(uploaded)
        c1, c2, c3 = st.columns(3)
        c1.metric("有效行", len(preview.rows))
        c2.metric("错误数", len(preview.errors))
        c3.metric("文件指纹", preview.sha256[:10])

        if preview.rows:
            st.dataframe(
                pd.DataFrame([row.model_dump() for row in preview.rows]),
                hide_index=True,
                use_container_width=True,
            )
        if preview.errors:
            st.error("文件未通过校验，不会写入数据库。")
            st.dataframe(
                pd.DataFrame([error.model_dump() for error in preview.errors]),
                hide_index=True,
                use_container_width=True,
            )
        elif st.button("确认导入", type="primary"):
            try:
                artifact = import_quotes(project_id, uploaded, batch_name)
                st.success(f"导入成功：批次 #{artifact.id}。重复文件不会重复写入。")
            except QuoteImportValidationError as exc:
                st.error(str(exc))

with score_tab:
    artifacts = list_quote_artifacts(project_id)
    if not artifacts:
        st.info("请先导入一批报价。")
        st.stop()

    artifact_lookup = {artifact.id: artifact for artifact in artifacts}
    artifact_id = st.selectbox(
        "报价批次",
        options=list(artifact_lookup),
        format_func=lambda item: f"#{item} · {artifact_lookup[item].batch_name}",
    )
    st.write("调整权重。总和必须为 100%。")
    cols = st.columns(4)
    price = cols[0].number_input("价格", 0, 100, DEFAULT_WEIGHTS["price"])
    moq = cols[1].number_input("MOQ", 0, 100, DEFAULT_WEIGHTS["moq"])
    lead_time = cols[2].number_input("交期", 0, 100, DEFAULT_WEIGHTS["lead_time"])
    quality = cols[3].number_input("质量风险", 0, 100, DEFAULT_WEIGHTS["quality"])
    weights = {"price": price, "moq": moq, "lead_time": lead_time, "quality": quality}

    if sum(weights.values()) != 100:
        st.error(f"当前权重合计 {sum(weights.values())}%，请调整为 100%。")
    else:
        scores = calculate_supplier_scores(get_quotes(artifact_id), weights)
        score_rows = []
        for rank, score in enumerate(scores, start=1):
            score_rows.append(
                {
                    "排名": rank,
                    "供应商": score.supplier,
                    "总分": score.total_score,
                    "单价": score.unit_price,
                    "币种": score.currency,
                    "MOQ": score.moq,
                    "交期/天": score.lead_time_days,
                    "价格分": score.price_score,
                    "MOQ分": score.moq_score,
                    "交期分": score.lead_time_score,
                    "质量分": score.quality_score,
                    "风险命中": "、".join(score.risk_hits) or "无",
                }
            )
        frame = pd.DataFrame(score_rows)
        st.dataframe(frame, hide_index=True, use_container_width=True)
        st.bar_chart(frame.set_index("供应商")["总分"])

        winner = scores[0]
        st.success(
            f"当前确定性排名第一：{winner.supplier}（{winner.total_score} 分）。"
            "这是加权比较结果，不是最终采购决定。"
        )
        with st.expander("评分方法和边界"):
            st.markdown(
                """
- 价格、MOQ、交期按本批次 min-max 归一化，数值越低得分越高。
- 所有候选某项数值相同时，该项均得 100 分，不制造虚假差异。
- 质量风险按透明关键词扣分；命中的关键词直接显示在表格中。
- 混合币种会在导入阶段被阻止，V1 不做实时汇率换算。
- 排名只提供决策依据，后续必须由项目负责人确认。
"""
            )

st.divider()
st.info("下一阶段：在当前排名之上接入结构化 AI 决策摘要、风险问题和负责人确认。")

