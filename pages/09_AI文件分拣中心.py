import streamlit as st

from core.db import init_db
from core.theme import apply_brand_theme, render_footer, render_page_header
from core.ui import render_sidebar
from services.document_routing_service import create_routing_task_draft, route_artifact
from services.file_service import list_project_files, upload_project_file

init_db()
st.set_page_config(page_title="AI 文件分拣中心 · TradeLoop", page_icon="🧭", layout="wide")
apply_brand_theme(require_auth=True)
render_page_header(
    "AI INTAKE ROUTER",
    "AI 文件分拣中心",
    "统一上传后，由系统推荐业务类型和主责部门；负责人确认后才生成任务草稿。",
)
project_id, _role = render_sidebar()
if project_id is None:
    st.warning("请先登录并进入一个项目。")
    st.stop()
token = st.session_state.get("auth_token", "")

st.subheader("统一上传")
uploaded = st.file_uploader(
    "上传项目业务文件",
    type=["pdf", "docx", "xlsx", "csv", "txt", "png", "jpg", "jpeg"],
    key="routing_upload",
)
if uploaded is not None and st.button("保存并开始分拣", type="primary"):
    try:
        artifact = upload_project_file(
            project_id=project_id,
            session_token=token,
            source=uploaded.getvalue(),
            filename=uploaded.name,
        )
        st.session_state["routing_artifact_id"] = artifact.id
        st.success("文件已保存到当前项目文件库。")
    except Exception as exc:
        st.error(f"上传失败：{exc}")

files = list_project_files(project_id=project_id, session_token=token)
if not files:
    st.info("暂无待分拣文件。")
    render_footer()
    st.stop()

st.subheader("待分拣文件")
for artifact in files:
    with st.expander(
        f"{artifact.original_filename} · {artifact.parse_status}",
        expanded=artifact.id == st.session_state.get("routing_artifact_id"),
    ):
        if st.button("分析并推荐部门", key=f"route_{artifact.id}"):
            try:
                result = route_artifact(
                    project_id=project_id, artifact_id=artifact.id, session_token=token
                )
                st.session_state[f"route_result_{artifact.id}"] = result
            except Exception as exc:
                st.error(f"分拣失败：{exc}")
        result = st.session_state.get(f"route_result_{artifact.id}")
        if result:
            st.write(f"文件类型：{result.document_type}")
            st.write(f"主责部门：{result.primary_department or '待人工判断'}")
            st.write(f"协同部门：{', '.join(result.collaborating_departments) or '无'}")
            st.write(f"关联产品：{result.related_product or '未确认'}")
            st.write(f"置信度：{result.routing_confidence:.0%} · {result.uncertainty}")
            st.info(result.routing_reason)
            st.caption("Evidence 关键词：" + ("、".join(result.source_evidence) or "暂无"))
            if result.missing_information:
                st.warning("待补充：" + "、".join(result.missing_information))
            if result.primary_department and st.button(
                "负责人确认并生成任务草稿", key=f"draft_{artifact.id}"
            ):
                try:
                    task = create_routing_task_draft(
                        project_id=project_id,
                        artifact_id=artifact.id,
                        result=result,
                        session_token=token,
                    )
                    st.success(f"任务草稿已创建：#{task.id}，尚未正式发布。")
                except Exception as exc:
                    st.error(f"无法创建任务草稿：{exc}")
render_footer()
