"""Live, review-only document AI actions for authorized project members."""

import hashlib
import json

import streamlit as st

from core.access_ui import render_user_error
from core.config import settings
from core.errors import TradeLoopError
from core.theme import apply_brand_theme, render_footer, render_page_header
from core.ui import render_sidebar
from services.app_preferences import runtime_config
from services.document_ai_schemas import DocumentSegment, DocumentSnapshot, SourceLocation
from services.document_ai_service import analyze_document, extract_requirements
from services.model_readiness import check_model_readiness

st.set_page_config(page_title="AI 文档理解 · TradeLoop", page_icon="📄", layout="wide")
apply_brand_theme()
render_page_header(
    "LIVE AI · DOCUMENT UNDERSTANDING",
    "文档理解与需求提取",
    "对当前项目的文本快照执行真实模型分析；结论和任务建议都需要人工审核。",
)
project_id, _role = render_sidebar()
if project_id is None:
    st.warning("请先进入一个项目。")
    st.stop()

readiness = check_model_readiness(runtime_config(settings))
if readiness.configured:
    st.caption(f"模型配置已就绪：{readiness.model_name}。只有点击分析按钮时才会发起请求。")
else:
    st.error("模型配置不完整，当前不能运行文档 AI。请到“设置”完成模型配置。")

st.warning(
    "本页接收手动提供的文本快照，目前不读取项目文件库。内容只用于本次请求；"
    "引用编号是临时编号，不代表数据库中的已存档 Evidence。"
)
with st.form("document_snapshot"):
    filename = st.text_input("来源文件名", value="pasted-document.txt", max_chars=255)
    file_type = st.selectbox("内容类型", ["text/plain", "text/csv", "application/pdf", "other"])
    source_text = st.text_area(
        "粘贴已授权的文档解析文本",
        height=260,
        placeholder="保留原文段落或表格行。不要粘贴不必要的个人敏感信息。",
    )
    project_context = st.text_area(
        "可选项目背景",
        height=80,
        max_chars=5_000,
        help="仅填写理解当前文件所需的最少背景，不要放入其他项目资料。",
    )
    submitted = st.form_submit_button("准备本次文本快照", disabled=not source_text.strip())

if submitted:
    normalized = source_text.strip()
    digest = hashlib.sha256((filename + "\n" + normalized).encode("utf-8")).hexdigest()
    file_id = int(digest[:7], 16) + 1
    segments = []
    lines = normalized.splitlines()
    start = 1
    for index, line in enumerate(lines + [""], start=1):
        if line.strip():
            continue
        if index > start:
            content = "\n".join(lines[start - 1 : index - 1]).strip()
            if content:
                segments.append(
                    DocumentSegment(
                        evidence_id=len(segments) + 1,
                        file_id=file_id,
                        file_version=digest[:12],
                        content_kind="text",
                        locator=SourceLocation(kind="text", line_start=start, line_end=index - 1),
                        content=content[:20_000],
                    )
                )
        start = index + 1
    snapshot = DocumentSnapshot(
        project_id=project_id,
        file_id=file_id,
        file_version=digest[:12],
        filename=filename.strip() or "pasted-document.txt",
        file_type=file_type,
        parser_status="parsed",
        segments=segments[:500],
        project_context=project_context.strip(),
    )
    st.session_state["document_ai_snapshot"] = snapshot.model_dump(mode="json")
    st.session_state.pop("document_ai_analysis", None)
    st.session_state.pop("document_ai_requirements", None)

snapshot_data = st.session_state.get("document_ai_snapshot")
if snapshot_data:
    snapshot = DocumentSnapshot.model_validate(snapshot_data)
    st.caption(
        f"当前快照：{snapshot.filename} · {len(snapshot.segments)} 个文本片段 · "
        f"版本指纹 {snapshot.file_version}"
    )
    col_analysis, col_requirements = st.columns(2)
    with col_analysis:
        analyze_clicked = st.button(
            "真实 AI 分析文档", type="primary", disabled=not readiness.configured
        )
    with col_requirements:
        requirements_clicked = st.button(
            "真实 AI 提取需求", disabled=not readiness.configured
        )

    if analyze_clicked or requirements_clicked:
        state_key = "document_ai_analysis" if analyze_clicked else "document_ai_requirements"
        request_key = f"{state_key}_request"
        fingerprint = hashlib.sha256(
            json.dumps(snapshot_data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if st.session_state.get(request_key) == fingerprint and st.session_state.get(state_key):
            st.info("相同输入已有成功结果；为避免重复计费，未再次发送请求。修改输入后可运行新请求。")
        else:
            st.caption("每次请求都可能产生费用。超时不能证明服务端未收到请求，请勿自动或盲目重试。")
            try:
                with st.spinner("正在等待真实模型响应并校验结构与原文引用…"):
                    if analyze_clicked:
                        response = analyze_document(snapshot)
                    else:
                        prior = st.session_state.get("document_ai_analysis")
                        analysis = json.loads(prior)["result"] if prior else None
                        response = extract_requirements(snapshot, analysis=analysis)
            except (TradeLoopError, ValueError) as exc:
                render_user_error(exc, fallback="模型请求失败或输出校验未通过；没有生成结果。")
            else:
                st.session_state[state_key] = response.model_dump_json()
                st.session_state[request_key] = fingerprint
                st.rerun()

    for key, title in (
        ("document_ai_analysis", "文档分析结果"),
        ("document_ai_requirements", "需求草稿"),
    ):
        raw = st.session_state.get(key)
        if not raw:
            continue
        response = json.loads(raw)
        st.markdown(f"### {title}")
        st.success("真实模型调用成功 · 结构和 Evidence 校验通过 · 待人工审核 · 不可直接发布")
        st.caption(
            f"模型：{response['model']} · Prompt：{response['prompt_version']} · "
            f"输入指纹：{response['input_hash']}"
        )
        st.json(response["result"], expanded=False)
        st.markdown("**已核验的原文引用**")
        if response["evidence_refs"]:
            for ref in response["evidence_refs"]:
                locator = ref["locator"]
                st.write(
                    f"临时引用 #{ref['evidence_id']} · {ref['file_version']} · "
                    f"行 {locator.get('line_start', '?')}–{locator.get('line_end', '?')}"
                )
                st.code(ref["excerpt"], language=None)
        else:
            st.info("模型没有引用具体原文。")

render_footer()
