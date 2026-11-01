from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

import core.auth_ui
import core.ui
import services.membership_service

ROOT_DIR = Path(__file__).resolve().parents[1]
HOME_PAGE = ROOT_DIR / "pages" / "01_项目首页.py"


def _user(user_id: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id, display_name=name, email=f"u{user_id}@example.com", force_password_change=False
    )


def _project(project_id: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=project_id,
        name=name,
        product_name="演示产品",
        markets_json='["US"]',
    )


def _sidebar_app() -> AppTest:
    return AppTest.from_string(
        """
import streamlit as st
from core.ui import render_sidebar

project_id, role = render_sidebar(require_unlock=False)
st.text(f"RESULT:{project_id}:{role}")
"""
    )


def test_homepage_allows_first_local_user_when_no_users(monkeypatch) -> None:
    monkeypatch.setattr(core.ui, "render_sidebar_navigation", lambda: None)
    monkeypatch.setattr(core.ui, "list_users", lambda: [])
    monkeypatch.setattr(services.membership_service, "list_users", lambda: [])

    app = AppTest.from_file(str(HOME_PAGE)).run(timeout=10)

    assert not app.exception
    assert any("请先登录" in item.value for item in app.info)
    assert not app.sidebar.selectbox


def test_non_member_cannot_see_unrelated_project(monkeypatch) -> None:
    user = _user(1, "普通成员")
    visible = _project(10, "可见项目")
    secret = _project(99, "其他项目的秘密")
    calls: list[int] = []

    monkeypatch.setattr(core.ui, "render_sidebar_navigation", lambda: None)
    monkeypatch.setattr(core.auth_ui, "get_authenticated_user", lambda: user)
    monkeypatch.setattr(core.ui, "get_authenticated_user", lambda: user)

    def fake_list_user_projects(user_id: int):
        calls.append(user_id)
        return [visible]

    monkeypatch.setattr(core.ui, "list_user_projects", fake_list_user_projects)
    monkeypatch.setattr(
        core.ui,
        "require_project_member",
        lambda project_id, user_id: SimpleNamespace(role="operations"),
    )

    app = _sidebar_app().run(timeout=10)

    assert not app.exception
    assert calls == [user.id]
    project_selector = next(item for item in app.sidebar.selectbox if item.label == "项目")
    assert project_selector.options == [f"{visible.name} · {visible.product_name}"]
    assert secret.name not in str(app)


def test_sidebar_role_comes_from_membership_record(monkeypatch) -> None:
    user = _user(3, "采购同事")
    project = _project(21, "采购项目")

    monkeypatch.setattr(core.ui, "render_sidebar_navigation", lambda: None)
    monkeypatch.setattr(core.auth_ui, "get_authenticated_user", lambda: user)
    monkeypatch.setattr(core.ui, "get_authenticated_user", lambda: user)
    monkeypatch.setattr(core.ui, "list_user_projects", lambda user_id: [project])
    monkeypatch.setattr(
        core.ui,
        "require_project_member",
        lambda project_id, user_id: SimpleNamespace(role="procurement"),
    )

    app = _sidebar_app().run(timeout=10)

    assert not app.exception
    assert app.session_state["active_role"] == "采购"
    assert any(item.value == "采购" and item.disabled for item in app.sidebar.text_input)
    assert any(item.value == "RESULT:21:采购" for item in app.text)
