"""Streamlit helpers for server-authenticated page access."""

import streamlit as st

from core.errors import ProjectAccessDeniedError
from services.auth_service import resolve_session


def clear_private_state():
    """Clear all session-local business results on logout or identity expiry."""
    for key in list(st.session_state):
        del st.session_state[key]


def get_authenticated_user():
    """Resolve the current server session; never trust a client-selected user id."""
    token = st.session_state.get("auth_token")
    if not token:
        return None
    try:
        return resolve_session(token)
    except ProjectAccessDeniedError:
        clear_private_state()
        return None


def require_authenticated_user():
    user = get_authenticated_user()
    if user is None:
        st.info("请先登录 TradeLoop。登录、注册和邮箱验证入口位于“项目交流”。")
        st.stop()
    if user.force_password_change:
        st.warning("请先到登录页面修改初始密码，再访问项目业务。")
        st.stop()
    return user
