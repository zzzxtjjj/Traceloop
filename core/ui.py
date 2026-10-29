import json
import math
import time

import streamlit as st

from core.errors import ProjectAccessDeniedError
from core.theme import render_sidebar_navigation
from services.membership_service import (
    list_user_projects,
    list_users,
    require_project_member,
)
from services.project_service import verify_project_access

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
    render_sidebar_navigation()
    st.sidebar.markdown("##### 当前工作区")

    users = list_users()
    if not users:
        st.sidebar.warning("尚无本地用户，请先在项目首页创建首个演示用户。")
        st.sidebar.caption("本地演示身份选择不等于登录认证。")
        return None, DEFAULT_ROLE

    user_labels = {user.id: f"{user.display_name} · {user.email}" for user in users}
    user_ids = list(user_labels)
    current_user_id = st.session_state.get("current_user_id")
    user_index = user_ids.index(current_user_id) if current_user_id in user_ids else 0
    user_id = st.sidebar.selectbox(
        "本地演示用户",
        options=user_ids,
        index=user_index,
        format_func=lambda item: user_labels[item],
        key="sidebar_user_id",
    )
    if user_id != current_user_id:
        st.session_state["current_user_id"] = user_id
        st.session_state.pop("active_project_id", None)
        st.session_state.pop("unlocked_project_ids", None)
        st.session_state.pop("sidebar_access_code", None)
    st.sidebar.caption("本地用户选择仅用于演示，不等于登录认证。")

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

    unlocked = set(st.session_state.get("unlocked_project_ids", []))
    if require_unlock and project_id not in unlocked:
        attempt_key = f"project_access_attempts_{project_id}"
        attempts = st.session_state.get(attempt_key, {"failures": 0, "locked_until": 0.0})
        remaining = max(0, math.ceil(attempts["locked_until"] - time.time()))
        locked = remaining > 0
        access_code = st.sidebar.text_input(
            "项目访问码",
            type="password",
            key="sidebar_access_code",
            disabled=locked,
        )
        if locked:
            st.sidebar.error(f"尝试次数过多，请在 {remaining} 秒后重试。")
        else:
            st.sidebar.caption("访问码是成员权限后的第二道解锁；连续失败 5 次将锁定 60 秒。")
        if st.sidebar.button("进入项目", width="stretch", disabled=locked):
            if verify_project_access(project_id, access_code):
                unlocked.add(project_id)
                st.session_state["unlocked_project_ids"] = list(unlocked)
                st.session_state["active_project_id"] = project_id
                st.session_state.pop(attempt_key, None)
                st.rerun()
            else:
                failures = attempts["failures"] + 1
                locked_until = time.time() + 60 if failures >= 5 else 0.0
                st.session_state[attempt_key] = {
                    "failures": failures,
                    "locked_until": locked_until,
                }
                if failures >= 5:
                    st.sidebar.error("访问码错误，已暂时锁定 60 秒。")
                else:
                    st.sidebar.error(f"访问码错误，还可尝试 {5 - failures} 次。")
        return None, role

    st.session_state["active_project_id"] = project_id
    return project_id, role
