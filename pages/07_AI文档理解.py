"""Project-file document parsing and review-only A3 analysis."""

import json

import streamlit as st

from core.access_ui import render_user_error
from core.config import settings
from core.db import session_scope
from core.document_result_ui import render_document_ai_result
from core.errors import TradeLoopError
from core.models import Artifact, DocumentExtraction
from core.product_ui import select_product
from core.theme import apply_brand_theme, render_footer, render_page_header
from core.ui import render_sidebar
from services.app_preferences import runtime_config
from services.document_ai_schemas import DocumentSegment, DocumentSnapshot, SourceLocation
from services.document_ai_service import analyze_document, extract_requirements
from services.document_fact_service import confirm_extraction_sources, source_blocks
from services.document_parser import extract_artifact
from services.file_service import list_project_files, upload_project_file
from services.model_readiness import check_model_readiness

st.set_page_config(page_title="文档与 AI 助手 · TradeLoop", page_icon="📄", layout="wide")
apply_brand_theme(require_auth=True)
render_page_header(
    "LIVE AI · DOCUMENT WORKSPACE",
    "文档与 AI 助手",
    "从当前项目文件库解析资料，再用真实模型提取事实和待审核需求。",
)

project_id, _role = render_sidebar()
token = st.session_state.get("auth_token")
if project_id is None:
    st.warning("请先进入一个项目。")
    st.stop()
if not token:
    st.warning("请先在项目交流页面完成登录，才能读取项目文件库。")
    st.stop()

product_id = select_product(project_id, token, owner=_role == "项目负责人")

try:
    files = list_project_files(project_id=project_id, session_token=token)
except TradeLoopError as exc:
    render_user_error(exc, fallback="无法读取当前项目文件。")
    st.stop()

st.info("文件上传和解析不会自动调用 AI。只有点击分析按钮后，才会发送当前文件快照。")
uploaded = st.file_uploader(
    "上传项目文件",
    type=["pdf", "docx", "xlsx", "csv", "txt", "png", "jpg", "jpeg"],
    help="文件会保存到当前项目文件库，并由后端校验项目权限。",
)
if uploaded and st.button("保存到项目文件库", key="save_project_file"):
    try:
        with st.spinner("正在保存文件…"):
            saved_artifact = upload_project_file(
                project_id=project_id,
                session_token=token,
                source=uploaded.getvalue(),
                filename=uploaded.name,
            )
        if saved_artifact.parsing_status == "pending":
            st.success("文件已保存到当前项目文件库。请在下方选择后解析。")
        else:
            st.info("该文件已存在于当前项目文件库，已复用原有 Artifact。")
        st.rerun()
    except (TradeLoopError, ValueError) as exc:
        render_user_error(exc, fallback="文件保存失败。")

if not files:
    st.info("当前项目还没有文件。上传 PDF、DOCX、XLSX、CSV、图片或 TXT 后即可开始。")
    render_footer()
    st.stop()

labels = {
    item.id: f"{item.original_filename} · {item.parsing_status} · {item.file_size or 0} bytes"
    for item in files
}
selected_ids = st.multiselect("选择项目文件", list(labels), format_func=labels.get)
st.caption("可以同时选择多个文件查看，但 A3 会对每个文件分别建立快照和分析结果。")

for artifact_id in selected_ids:
    artifact = next(item for item in files if item.id == artifact_id)
    st.markdown(f"### {artifact.original_filename}")
    st.caption(
        f"格式：{artifact.mime_type} · 上传时间：{artifact.uploaded_at} · "
        f"版本：{artifact.version} · 状态：{artifact.parsing_status}"
    )
    parse_key = f"document_parse_{project_id}_{artifact.id}_{artifact.sha256}"
    if st.button("解析或读取已有结果", key=f"parse_{artifact.id}"):
        try:
            with st.spinner("正在解析文件…"):
                extraction = extract_artifact(
                    project_id=project_id,
                    session_token=token,
                    artifact_id=artifact.id,
                )
            st.session_state[parse_key] = extraction.id
            st.rerun()
        except (TradeLoopError, ValueError) as exc:
            render_user_error(exc, fallback="文件解析失败，原文件仍然保留。")

    extraction_id = st.session_state.get(parse_key)
    if extraction_id is None:
        st.info("点击“解析或读取已有结果”查看结构化内容。")
        continue
    with session_scope() as db:
        extraction = db.get(DocumentExtraction, extraction_id)
        current_artifact = db.get(Artifact, artifact.id)
    if (
        not extraction
        or not current_artifact
        or current_artifact.project_id != project_id
        or extraction.project_id != project_id
        or extraction.artifact_id != artifact.id
    ):
        st.error("解析结果不存在或项目不匹配。")
        continue
    if extraction.status not in {"succeeded", "partial"}:
        st.error(f"解析未成功：{extraction.error_code or extraction.status}")
        continue
    metadata = json.loads(extraction.locator_json or "{}")
    st.write("解析预览")
    st.code(extraction.text_excerpt[:12_000], language=None)
    for warning in metadata.get("warnings", []):
        st.warning(warning)
    if product_id and _role == "项目负责人":
        confirmed = st.checkbox(
            "我已逐条核对上方原文，确认作为当前产品的事实依据",
            key=f"confirm_sources_{project_id}_{artifact.id}",
        )
        if st.button(
            "保存已确认原文与产品关联", key=f"save_sources_{artifact.id}", disabled=not confirmed
        ):
            try:
                sources = confirm_extraction_sources(
                    project_id=project_id,
                    session_token=token,
                    product_id=product_id,
                    extraction_id=extraction.id,
                )
                st.success(f"已保存 {len(sources)} 条真实原文依据，可前往商品资料与多语言使用。")
            except (TradeLoopError, ValueError) as exc:
                render_user_error(exc)

    blocks = list(source_blocks(metadata))
    segments = []
    for index, block in enumerate(blocks[:500], 1):
        content = str(block.get("text") or block.get("value") or "").strip()
        if not content:
            continue
        locator_kind = (
            "pdf" if block.get("page") else "spreadsheet" if block.get("sheet") else "document"
        )
        locator = SourceLocation(
            kind=locator_kind,
            page=block.get("page"),
            sheet=block.get("sheet"),
            cell_range=block.get("cell"),
            paragraph_index=block.get("paragraph_index"),
            table_index=block.get("table_index"),
            row_index=block.get("row_index"),
            column_index=block.get("column_index"),
        )
        segments.append(
            DocumentSegment(
                evidence_id=index,
                file_id=artifact.id,
                file_version=str(artifact.version),
                content_kind=(
                    "table" if block.get("kind") in {"table", "spreadsheet_cell"} else "text"
                ),
                locator=locator,
                content=content[:20_000],
            )
        )
    if not segments and extraction.text_excerpt:
        segments = [
            DocumentSegment(
                evidence_id=1,
                file_id=artifact.id,
                file_version=str(artifact.version),
                content_kind="text",
                locator=SourceLocation(kind="text", line_start=1),
                content=extraction.text_excerpt[:20_000],
            )
        ]
    if not segments:
        st.warning("没有可供 AI 使用的文本证据。")
        continue
    snapshot = DocumentSnapshot(
        project_id=project_id,
        file_id=artifact.id,
        file_version=str(artifact.version),
        filename=artifact.original_filename,
        file_type=artifact.original_filename.rsplit(".", 1)[-1].casefold()
        if "." in artifact.original_filename
        else (artifact.mime_type or "unknown")[:30],
        parser_status="parsed",
        segments=segments,
    )
    readiness = check_model_readiness(runtime_config(settings))
    analyze_clicked = st.button(
        "真实 AI 分析文档",
        key=f"analyze_{artifact.id}",
        disabled=not readiness.configured,
    )
    requirements_clicked = st.button(
        "真实 AI 提取需求",
        key=f"requirements_{artifact.id}",
        disabled=not readiness.configured,
    )
    if not readiness.configured:
        st.warning("AI 服务未配置；解析预览仍可使用。")
    if analyze_clicked or requirements_clicked:
        try:
            with st.spinner("正在调用真实模型并校验证据…"):
                response = (
                    analyze_document(snapshot)
                    if analyze_clicked
                    else extract_requirements(snapshot)
                )
            st.session_state[f"document_ai_result_{artifact.id}"] = response.model_dump(mode="json")
            st.rerun()
        except (TradeLoopError, ValueError) as exc:
            render_user_error(exc, fallback="AI 分析失败或 Evidence 校验未通过，没有生成结果。")
    result = st.session_state.get(f"document_ai_result_{artifact.id}")
    if result:
        render_document_ai_result(result, artifact.original_filename)

render_footer()
