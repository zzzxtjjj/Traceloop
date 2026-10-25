import json

import streamlit as st

from services.project_service import list_projects, verify_project_access

ROLES = ["项目负责人", "采购", "运营", "品控"]


def render_sidebar(*, require_unlock: bool = True) -> tuple[int | None, str]:
    """Render the shared project/role selector and return the active values."""
    projects = list_projects()
    st.sidebar.header("当前工作区")

    if not projects:
        st.sidebar.warning("尚无项目，请先在项目首页创建或加载演示项目。")
        return None, ROLES[0]

    labels = {project.id: f"{project.name} · {project.product_name}" for project in projects}
    project_ids = list(labels)
    current_id = st.session_state.get("active_project_id")
    default_index = project_ids.index(current_id) if current_id in project_ids else 0
    project_id = st.sidebar.selectbox(
        "项目",
        options=project_ids,
        index=default_index,
        format_func=lambda item: labels[item],
    )
    role = st.sidebar.selectbox("演示身份", ROLES)
    st.session_state["active_role"] = role

    project = next(item for item in projects if item.id == project_id)
    markets = ", ".join(json.loads(project.markets_json))
    st.sidebar.caption(f"目标市场：{markets}")

    unlocked = set(st.session_state.get("unlocked_project_ids", []))
    if require_unlock and project_id not in unlocked:
        access_code = st.sidebar.text_input(
            "项目访问码", type="password", key="sidebar_access_code"
        )
        if st.sidebar.button("进入项目", use_container_width=True):
            if verify_project_access(project_id, access_code):
                unlocked.add(project_id)
                st.session_state["unlocked_project_ids"] = list(unlocked)
                st.session_state["active_project_id"] = project_id
                st.rerun()
            else:
                st.sidebar.error("访问码错误。")
        return None, role

    st.session_state["active_project_id"] = project_id
    return project_id, role

