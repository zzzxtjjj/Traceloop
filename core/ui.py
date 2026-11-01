import json

import streamlit as st

from core.auth_ui import get_authenticated_user
from core.errors import ProjectAccessDeniedError
from core.theme import render_sidebar_navigation  # noqa: F401
from services.membership_service import (
    list_user_projects,
    list_users,  # noqa: F401 - legacy AppTest fixtures patch this symbol
    require_project_member,
)

ROLE_LABELS = {
    "owner": "项目负责人",
    "procurement": "采购",
    "operations": "运营",
    "quality": "品控",
}
DEFAULT_ROLE = ROLE_LABELS["owner"]


def role_label(role: str) -> str:
    """Translate the persisted membership role for existing page compatibility."""
    return ROLE_LABELS.get(role, role)


def render_sidebar(*, require_unlock: bool = True) -> tuple[int | None, str]:
    """Render persisted identity/project selection and return project plus role label."""
    user = get_authenticated_user()
    if user is None:
        return None, DEFAULT_ROLE
    user_id = user.id
    st.sidebar.markdown("##### 当前工作区")
    st.sidebar.caption(f"当前账号：{user.display_name} · {user.email}")

    projects = list_user_projects(user_id)
    if not projects:
        st.sidebar.info("当前用户尚未加入任何项目。访问码不会自动赋予成员资格。")
        st.session_state.pop("active_project_id", None)
        st.session_state.pop("active_role", None)
        return None, DEFAULT_ROLE

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

    try:
        membership = require_project_member(project_id, user_id)
    except ProjectAccessDeniedError:
        st.sidebar.error("无权访问或对象不存在。")
        return None, DEFAULT_ROLE
    role = role_label(membership.role)
    st.session_state["active_role"] = role
    st.sidebar.text_input("项目岗位", value=role, disabled=True)

    project = next(item for item in projects if item.id == project_id)
    markets = ", ".join(json.loads(project.markets_json))
    st.sidebar.caption(f"目标市场 · {markets}")

    st.session_state["active_project_id"] = project_id
    return project_id, role
