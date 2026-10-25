import json
import math
import time

import streamlit as st

from core.theme import render_sidebar_navigation
from services.project_service import list_projects, verify_project_access

ROLES = ["项目负责人", "采购", "运营", "品控"]


def render_sidebar(*, require_unlock: bool = True) -> tuple[int | None, str]:
    """Render the shared project/role selector and return the active values."""
    render_sidebar_navigation()
    projects = list_projects()
    st.sidebar.markdown("##### 当前工作区")

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
            st.sidebar.caption("连续失败 5 次，本浏览器会暂时锁定 60 秒。")
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

