import json
from pathlib import Path

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from core.access_ui import render_user_error
from core.auth_ui import get_authenticated_user
from core.db import init_db
from core.errors import ProjectAccessDeniedError
from core.schemas import ProjectCreate
from core.theme import (
    apply_brand_theme,
    render_footer,
    render_page_header,
    render_security_note,
)
from core.ui import ROLE_LABELS, render_sidebar
from services.imports import import_quotes, list_quote_artifacts
from services.membership_service import (
    add_project_member,
    can_create_projects,
    list_project_members,
    list_user_projects,
    list_users,
)
from services.project_service import (
    ProjectNameExistsError,
    create_project,
    get_project_by_name,
)

init_db()
DEMO_FILE = Path(__file__).resolve().parents[1] / "data" / "demo" / "supplier_quotes.csv"
ACCEPTANCE_ROOT = Path(__file__).resolve().parents[1] / "data" / "acceptance"
DEMO_PROJECTS = {
    "demo1": ("便携式空气炸锅 4L", ACCEPTANCE_ROOT / "demo1" / "supplier_quotes_30.csv"),
    "demo2": ("桌面空气净化器", ACCEPTANCE_ROOT / "demo2" / "supplier_quotes_30.csv"),
    "demo3": ("多功能电热水壶", ACCEPTANCE_ROOT / "demo3" / "supplier_quotes_30.csv"),
}
MEMBER_ROLES = ["procurement", "operations", "quality", "owner"]

st.set_page_config(page_title="项目首页 · TradeLoop", page_icon="🌊", layout="wide")
apply_brand_theme(require_auth=True)
render_page_header(
    "PROJECT JOURNAL · 项目航海志",
    "选择项目，开始处理业务",
    "登录后只能查看自己加入的项目；每个人可执行的操作由其项目岗位决定。",
)

project_id, role = render_sidebar(require_unlock=True)
current_user = get_authenticated_user()
if current_user is None:
    st.stop()
current_user_id = current_user.id
users = list_users(include_inactive=True)

is_owner = role == ROLE_LABELS["owner"]
can_create = can_create_projects(current_user_id) or is_owner

if can_create:
    with st.expander("＋ 新建项目", expanded=False):
        st.caption("只有项目负责人可以新建项目。新项目会把当前用户登记为负责人。")
        with st.form("create_project_form", clear_on_submit=True):
            name = st.text_input("项目名称", placeholder="例如：秋季新品出海")
            product_name = st.text_input("产品名称", placeholder="例如：真空保温杯")
            markets = st.multiselect(
                "目标市场",
                options=["US", "DE"],
                default=["US", "DE"],
                format_func=lambda item: {"US": "美国", "DE": "德国"}[item],
            )
            access_code = st.text_input("项目访问码", type="password", help="至少 8 位")
            submitted = st.form_submit_button("创建项目", width="stretch")

    if submitted:
        try:
            payload = ProjectCreate(
                name=name,
                product_name=product_name,
                access_code=access_code,
                markets=markets,
            )
            project = create_project(
                payload,
                owner_user_id=current_user_id,
                require_existing_owner=True,
            )
            unlocked = set(st.session_state.get("unlocked_project_ids", []))
            unlocked.add(project.id)
            st.session_state["unlocked_project_ids"] = list(unlocked)
            st.session_state["active_project_id"] = project.id
            st.success(f"项目“{project.name}”已创建，当前用户已登记为项目负责人。")
            st.rerun()
        except ValidationError as exc:
            for issue in exc.errors():
                st.error(f"{issue['loc'][0]}：{issue['msg']}")
        except (ProjectNameExistsError, ProjectAccessDeniedError) as exc:
            render_user_error(exc)

else:
    st.info("当前账号不是项目负责人。新建项目由负责人统一管理；你可以进入已加入的项目继续工作。")

left, right = st.columns(2)
with left:
    st.subheader("小家电演示项目")
    st.write("负责人可以从这里进入三个预置小家电项目，分别用于测试报价、客户反馈和商品资料流程。")
    st.code("演示访问码：demo2026", language=None)
    selected_demo = st.selectbox(
        "选择演示项目",
        options=list(DEMO_PROJECTS),
        format_func=lambda item: f"{item} · {DEMO_PROJECTS[item][0]}",
    )
    if st.button("进入演示项目", type="primary", width="stretch", disabled=not can_create):
        demo_product, demo_file = DEMO_PROJECTS[selected_demo]
        accessible_projects = list_user_projects(current_user_id)
        project = next((item for item in accessible_projects if item.name == selected_demo), None)
        existing_project = get_project_by_name(selected_demo)
        if project is None and existing_project is not None:
            render_user_error(ProjectAccessDeniedError("项目存在但当前用户不是成员"))
        else:
            if project is None:
                project = create_project(
                    ProjectCreate(
                        name=selected_demo,
                        product_name=demo_product,
                        access_code="demo2026",
                        markets=["US", "DE"],
                    ),
                    owner_user_id=current_user_id,
                    require_existing_owner=True,
                )
            if not list_quote_artifacts(project.id):
                import_quotes(
                    project.id,
                    demo_file if demo_file.exists() else DEMO_FILE,
                    "首轮供应商报价",
                )
            unlocked = set(st.session_state.get("unlocked_project_ids", []))
            unlocked.add(project.id)
            st.session_state["unlocked_project_ids"] = list(unlocked)
            st.session_state["active_project_id"] = project.id
            st.success("演示项目已就绪，请进入“报价决策”。")
            st.rerun()

st.divider()
projects = list_user_projects(current_user_id)
if projects:
    st.subheader("我加入的项目")
    table = [
        {
            "ID": project.id,
            "项目": project.name,
            "产品": project.product_name,
            "目标市场": ", ".join(json.loads(project.markets_json)),
            "创建时间": project.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for project in projects
    ]
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
else:
    st.info("当前用户尚未加入任何项目。可以创建一个新项目，由当前用户担任负责人。")

if project_id is not None:
    st.divider()
    st.subheader("项目成员与岗位")
    try:
        memberships = list_project_members(project_id, current_user_id)
        users_by_id = {user.id: user for user in list_users(include_inactive=True)}
        member_rows = []
        for membership in memberships:
            member_user = users_by_id.get(membership.user_id)
            member_rows.append(
                {
                    "成员": (
                        member_user.display_name if member_user else f"用户 {membership.user_id}"
                    ),
                    "邮箱": member_user.email if member_user else "不可用",
                    "岗位": ROLE_LABELS.get(membership.role, membership.role),
                    "状态": membership.status,
                }
            )
        st.dataframe(pd.DataFrame(member_rows), hide_index=True, width="stretch")

        member_user_ids = {membership.user_id for membership in memberships}
        candidates = [user for user in users if user.id not in member_user_ids]
        is_owner = role == ROLE_LABELS["owner"]
        st.caption("只有项目负责人可添加成员；界面禁用只是提示，后端仍会重新校验负责人权限。")
        if candidates:
            candidate_labels = {
                user.id: f"{user.display_name} · {user.email}" for user in candidates
            }
            with st.form("add_project_member_form"):
                target_user_id = st.selectbox(
                    "选择已有用户",
                    options=list(candidate_labels),
                    format_func=lambda item: candidate_labels[item],
                    disabled=not is_owner,
                )
                member_role = st.selectbox(
                    "项目岗位",
                    options=MEMBER_ROLES,
                    format_func=lambda item: ROLE_LABELS[item],
                    disabled=not is_owner,
                )
                add_member_submitted = st.form_submit_button(
                    "添加项目成员", width="stretch", disabled=not is_owner
                )
            if add_member_submitted:
                try:
                    add_project_member(
                        project_id,
                        current_user_id,
                        target_user_id,
                        member_role,
                    )
                    st.success("项目成员已添加。")
                    st.rerun()
                except (ValueError, ProjectAccessDeniedError) as exc:
                    render_user_error(exc)
        else:
            st.info("所有现有本地用户都已加入该项目。")
    except ProjectAccessDeniedError as exc:
        render_user_error(exc)

render_security_note()
render_footer()
