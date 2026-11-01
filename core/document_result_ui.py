"""Chinese business-facing rendering for document AI results."""

import streamlit as st

STATUS_LABELS = {
    "explicit": "原文明确记载",
    "inferred": "AI 推断，需核实",
    "unknown": "资料未说明",
    "needs_review": "待人工核实",
    "confirmed": "已确认",
    "rejected": "已驳回",
    "low": "低",
    "medium": "中",
    "high": "高",
}

ATTRIBUTE_LABELS = {
    "product name": "产品名称",
    "product_name": "产品名称",
    "model": "产品型号",
    "sku": "产品型号",
    "capacity": "容量",
    "power": "功率",
    "material": "材料",
    "dimensions": "尺寸",
    "warranty": "保修信息",
}

ROLE_LABELS = {
    "project_manager": "项目负责人",
    "export_sales": "外贸销售",
    "procurement": "采购",
    "production": "生产",
    "quality_control": "品控",
    "product_engineering": "产品工程",
    "logistics": "物流",
}


def format_source_location(locator: dict) -> str:
    parts = []
    if locator.get("page") is not None:
        parts.append(f"第 {locator['page']} 页")
    if locator.get("sheet"):
        cell = locator.get("cell_range")
        parts.append(f"工作表“{locator['sheet']}”" + (f"，单元格 {cell}" if cell else ""))
    if locator.get("paragraph_index") is not None:
        parts.append(f"第 {locator['paragraph_index'] + 1} 段")
    if locator.get("table_index") is not None:
        table = f"第 {locator['table_index'] + 1} 个表格"
        if locator.get("row_index") is not None:
            table += f"，第 {locator['row_index'] + 1} 行"
        if locator.get("column_index") is not None:
            table += f"第 {locator['column_index'] + 1} 列"
        parts.append(table)
    if locator.get("line_start") is not None:
        end = locator.get("line_end") or locator["line_start"]
        parts.append(f"第 {locator['line_start']}–{end} 行")
    return " · ".join(parts) or "原文位置已记录"


def _status(value: str | None) -> str:
    return STATUS_LABELS.get(value or "", value or "")


def _evidence_index(refs: list[dict]) -> dict[int, dict]:
    return {item["evidence_id"]: item for item in refs}


def _render_quotes(quotes: list[dict], refs: dict[int, dict], *, label: str = "原文依据") -> None:
    if not quotes:
        st.caption(f"{label}：没有可引用的原文片段")
        return
    for quote in quotes:
        ref = refs.get(quote.get("evidence_id"), {})
        filename = ref.get("filename") or ref.get("source_file")
        locator = ref.get("locator") or {}
        source = " · ".join(item for item in (filename, format_source_location(locator)) if item)
        if source:
            st.caption(source)
        st.markdown(f"> {quote.get('quote', '')}")


def render_document_ai_result(response: dict, source_filename: str) -> None:
    """Render translated business content first and raw JSON as an optional audit view."""
    result = response.get("result", {})
    refs_list = response.get("evidence_refs", [])
    refs = _evidence_index(refs_list)
    st.success("AI 文档理解已完成 · 结果待人工审核，不能直接发布")

    if "requirements" in result:
        st.subheader("识别出的业务要求")
        requirements = result.get("requirements", [])
        if not requirements:
            st.info("未从文件中识别出明确的待办要求。")
        for index, item in enumerate(requirements, start=1):
            title = item.get("requirement_title") or f"要求 {index}"
            with st.expander(title, expanded=index == 1):
                st.write(item.get("description", ""))
                if item.get("suggested_role"):
                    role = item["suggested_role"]
                    role_label = ROLE_LABELS.get(role, role)
                    st.caption(f"建议负责岗位：{role_label}")
                if item.get("suggested_deadline"):
                    st.caption(f"建议期限：{item['suggested_deadline']}（需负责人确认）")
                for label, key in (
                    ("交付内容", "deliverables"),
                    ("验收标准", "acceptance_criteria"),
                    ("还需确认", "missing_information"),
                ):
                    values = item.get(key, [])
                    if values:
                        st.markdown(f"**{label}**")
                        for value in values:
                            st.markdown(f"- {value}")
                _render_quotes(item.get("source_evidence", []), refs, label="要求来源")
        gaps = result.get("missing_information", [])
        if gaps:
            st.subheader("仍需补充的信息")
            for item in gaps:
                st.markdown(f"- {item.get('question', '')}")
    else:
        classification = result.get("classification", {})
        if classification:
            st.subheader("文件理解")
            st.markdown(f"**文件类型：** {classification.get('document_type', '未能判断')}")
            scenarios = classification.get("business_scenarios", [])
            entities = classification.get("entities", [])
            if scenarios:
                st.markdown(f"**涉及业务：** {'、'.join(scenarios)}")
            if entities:
                st.markdown(f"**识别对象：** {'、'.join(entities)}")

        summaries = result.get("summary", [])
        if summaries:
            st.subheader("内容摘要")
            for item in summaries:
                st.markdown(
                    f"- {item.get('statement', '')} _({_status(item.get('epistemic_status'))})_"
                )

        attributes = result.get("dynamic_attributes", [])
        if attributes:
            st.subheader("识别到的资料字段")
            rows = []
            for item in attributes:
                raw_name = item.get("display_name") or item.get("field_name") or "未命名字段"
                label = ATTRIBUTE_LABELS.get(str(raw_name).casefold(), raw_name)
                value = item.get("value")
                if value in (None, ""):
                    value = "原资料未提供"
                elif item.get("unit") and item["unit"] not in str(value):
                    value = f"{value} {item['unit']}"
                rows.append(
                    {
                        "资料项目": label,
                        "识别结果": value,
                        "核验状态": _status(item.get("review_status")),
                    }
                )
            st.dataframe(rows, hide_index=True, use_container_width=True)

        facts = result.get("important_facts", [])
        if facts:
            st.subheader("其他重要事实")
            for item in facts:
                st.markdown(
                    f"- {item.get('statement', '')} _({_status(item.get('epistemic_status'))})_"
                )

        gaps = result.get("missing_information", [])
        if gaps:
            st.subheader("资料缺失，需人工确认")
            for item in gaps:
                st.markdown(f"- {item.get('question', '')}")

        conflicts = result.get("conflicts", [])
        if conflicts:
            st.subheader("资料冲突")
            for item in conflicts:
                st.warning(item.get("description", "发现信息冲突"))
                _render_quotes(item.get("evidence", []), refs, label="冲突依据")

        risks = result.get("risks", [])
        if risks:
            st.subheader("风险提示")
            for item in risks:
                st.warning(f"{_status(item.get('severity'))}风险：{item.get('description', '')}")

        signals = result.get("requirement_signals", [])
        if signals:
            st.subheader("文件中提到的要求")
            for item in signals:
                st.markdown(f"- {item.get('statement', '')}")

    if refs_list:
        st.subheader("可追溯的原文证据")
        for item in refs_list:
            locator = item.get("locator", {})
            source = " · ".join(
                value
                for value in (
                    item.get("filename") or source_filename,
                    format_source_location(locator),
                )
                if value
            )
            st.caption(source)
            st.code(item.get("excerpt", ""), language=None)

    with st.expander("技术详情（原始结构化结果）"):
        st.caption(
            f"模型：{response.get('model', '未知')} · "
            f"输入指纹：{response.get('input_hash', '未知')}"
        )
        st.json(result, expanded=False)
