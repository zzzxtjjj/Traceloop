import json
from pathlib import Path

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from core.access_ui import render_user_error
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
    create_user,
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
MEMBER_ROLES = ["procurement", "operations", "quality", "owner"]

st.set_page_config(page_title="项目首页 · TradeLoop", page_icon="🌊", layout="wide")
apply_brand_theme()
render_page_header(
    "PROJECT JOURNAL · 项目航海志",
    "选择项目，开始处理业务",
    "选择本地演示用户后，只能查看其已加入的项目；每个人可执行的操作由其项目岗位决定。",
)

project_id, role = render_sidebar(require_unlock=True)
users = list_users()

if not users:
    st.subheader("创建首个本地演示用户")
    st.info("本地演示身份选择不等于登录认证；它用于演示项目成员和岗位权限。")
    with st.form("create_first_user", clear_on_submit=True):
        display_name = st.text_input("显示名称", placeholder="例如：项目负责人")
        email = st.text_input("邮箱", placeholder="例如：owner@example.com")
        create_user_submitted = st.form_submit_button("创建演示用户", width="stretch")
    if create_user_submitted:
        try:
            user = create_user(display_name, email)
            st.session_state["current_user_id"] = user.id
            st.success("首个本地演示用户已创建。")
            st.rerun()
        except ValueError as exc:
            render_user_error(exc, fallback="用户创建失败，请检查名称和邮箱。")
    render_security_note()
    render_footer()
    st.stop()

current_user_id = st.session_state.get("current_user_id")
current_user = next((item for item in users if item.id == current_user_id), users[0])
current_user_id = current_user.id
st.session_state["current_user_id"] = current_user_id
st.caption(
    f"当前本地演示用户：{current_user.display_name}。这不是登录认证；"
    "访问码也不会把用户自动加入项目。"
)

with st.expander("创建另一个本地演示用户"):
    st.caption("创建用户不会自动把该用户加入任何项目；项目负责人需在下方成员区单独添加。")
    with st.form("create_additional_user", clear_on_submit=True):
        additional_name = st.text_input("新用户显示名称")
        additional_email = st.text_input("新用户邮箱")
        additional_user_submitted = st.form_submit_button("创建本地演示用户")
    if additional_user_submitted:
        try:
            create_user(additional_name, additional_email)
            st.success("新用户已创建，但尚未加入任何项目。")
            st.rerun()
        except ValueError as exc:
            render_user_error(exc, fallback="用户创建失败，请检查名称和邮箱。")

left, right = st.columns(2)

with left:
    st.subheader("创建项目档案")
    st.caption("新项目会把当前用户登记为项目负责人。")
    with st.form("create_project_form", clear_on_submit=True):
        name = st.text_input("项目名称", placeholder="例如：秋季新品出海")
        product_name = st.text_input("产品名称", placeholder="例如：真空保温杯")
        markets = st.multiselect(
            "目标市场",
            options=["US", "DE"],
            default=["US", "DE"],
            format_func=lambda item: {"US": "美国", "DE": "德国"}[item],
        )
        access_code = st.text_input(
            "项目访问码",
            type="password",
            help="至少 8 位，只保存加盐哈希；它是成员权限后的第二道解锁。",
        )
        submitted = st.form_submit_button("创建项目", width="stretch")

    if submitted:
        try:
            payload = ProjectCreate(
                name=name,
                product_name=product_name,
                access_code=access_code,
                markets=markets,
            )
            project = create_project(payload, owner_user_id=current_user_id)
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

with right:
    st.subheader("试航项目")
    st.write("将创建保温杯新品项目，并导入 3 家供应商的标准报价。")
    st.code("演示访问码：demo2026", language=None)
    if st.button("加载演示项目", type="primary", width="stretch"):
        accessible_projects = list_user_projects(current_user_id)
        project = next(
            (item for item in accessible_projects if item.name == "保温杯新品出海"),
            None,
        )
        existing_project = get_project_by_name("保温杯新品出海")
        if project is None and existing_project is not None:
            render_user_error(ProjectAccessDeniedError("项目存在但当前用户不是成员"))
        else:
            if project is None:
                project = create_project(
                    ProjectCreate(
                        name="保温杯新品出海",
                        product_name="真空保温杯 750ml",
                        access_code="demo2026",
                        markets=["US", "DE"],
                    ),
                    owner_user_id=current_user_id,
                )
            if not list_quote_artifacts(project.id):
                import_quotes(project.id, DEMO_FILE, "首轮供应商报价")
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
        users_by_id = {user.id: user for user in users}
        member_rows = []
        for membership in memberships:
            member_user = users_by_id.get(membership.user_id)
            member_rows.append(
                {
                    "成员": (
                        member_user.display_name
                        if member_user
                        else f"用户 {membership.user_id}"
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
