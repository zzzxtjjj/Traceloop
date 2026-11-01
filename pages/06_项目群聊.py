import html
import json

import streamlit as st

from core.access_ui import render_user_error, safe_error_message
from core.auth_ui import clear_private_state, get_authenticated_user
from core.db import init_db
from core.errors import ProjectAccessDeniedError
from core.theme import apply_brand_theme, render_footer, render_page_header
from services.auth_service import (
    authenticate,
    create_session,
    issue_email_verification,
    reset_password_with_code,
    revoke_session,
    set_password,
    verify_email,
)
from services.channel_service import list_messages, send_message
from services.email_service import mail_configured, send_verification_email
from services.file_service import download_project_file, upload_project_file
from services.membership_service import (
    UserEmailExistsError,
    create_user,
    get_user_by_email,
    list_project_members,
    list_user_projects,
    list_users,
)

init_db()
st.set_page_config(page_title="项目交流 · TradeLoop", page_icon="💬", layout="wide")
# Resolve navigation visibility before the shared theme renders the sidebar.
# This prevents a stale sidebar from a previous rerun exposing business links
# while the current server session is unauthenticated.
st.session_state["_auth_nav_visible"] = get_authenticated_user() is not None
apply_brand_theme()
render_page_header(
    "PROJECT CHANNEL · 项目群聊",
    "把讨论、文件和证据留在同一个项目里",
    "消息从数据库读取，附件进入受控项目文件库；每次访问都重新校验服务端会话和项目成员关系。",
)


def _current_user():
    return get_authenticated_user()


def _login() -> None:
    st.subheader("登录 TradeLoop")
    st.caption("本页面使用服务端密码会话；项目角色来自 ProjectMember，不接受客户端自行指定。")
    login_tab, register_tab, reset_tab = st.tabs(["登录", "注册账号", "找回密码"])
    with login_tab:
        with st.form("chat_login", clear_on_submit=False):
            email = st.text_input("邮箱", placeholder="owner@tradeloop.demo")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录", type="primary", width="stretch")
        if submitted:
            try:
                user = authenticate(email, password)
                st.session_state["auth_token"] = create_session(user.id)
                st.rerun()
            except Exception as exc:
                render_user_error(exc, fallback="登录失败，请检查邮箱和密码。")
    with register_tab:
        st.caption("邮箱必须唯一。注册后需完成邮箱验证，系统不会伪造验证成功。")
        with st.form("chat_register", clear_on_submit=True):
            display_name = st.text_input("姓名")
            register_email = st.text_input("邮箱")
            register_password = st.text_input("设置密码", type="password")
            register_confirm = st.text_input("确认密码", type="password")
            register_submit = st.form_submit_button("创建账号", width="stretch")
        if register_submit:
            try:
                if register_password != register_confirm:
                    raise ValueError("两次输入的密码不一致。")
                if len(register_password.strip()) < 8:
                    raise ValueError("密码至少需要 8 个字符。")
                user = create_user(
                    display_name,
                    register_email,
                    email_verified=False,
                    force_password_change=False,
                )
                set_password(user.id, register_password)
                if mail_configured():
                    send_verification_email(user.email, issue_email_verification(user.id))
                    st.success("账号已创建，验证码已发送，请先验证邮箱。")
                else:
                    st.warning("账号已创建但尚未激活。邮件服务待配置，未发送验证码。")
            except (ValueError, UserEmailExistsError) as exc:
                render_user_error(exc, fallback="注册失败，请检查输入内容。")
    with reset_tab:
        st.caption("通过已验证邮箱的验证码重置密码。未配置 SMTP 时不会伪造发送成功。")
        reset_email = st.text_input("注册邮箱", key="reset_email")
        if st.button("发送找回验证码", key="send_reset_code"):
            try:
                reset_user = get_user_by_email(reset_email)
                if reset_user is None or not reset_user.email_verified:
                    raise ValueError("如果账号存在且已验证，验证码将发送到邮箱。")
                if not mail_configured():
                    raise ValueError("邮件服务待配置，未发送验证码。")
                send_verification_email(reset_user.email, issue_email_verification(reset_user.id))
                st.success("验证码已发送，请查看邮箱。")
            except ValueError as exc:
                render_user_error(exc, fallback="未发送验证码，请检查邮件配置。")
        with st.form("password_reset_form", clear_on_submit=True):
            reset_code = st.text_input("邮箱验证码")
            reset_password = st.text_input("新密码", type="password")
            reset_confirm = st.text_input("确认新密码", type="password")
            reset_submit = st.form_submit_button("重置密码")
        if reset_submit:
            try:
                reset_user = get_user_by_email(reset_email)
                if reset_user is None or not reset_user.email_verified:
                    raise ValueError("验证码不正确或已过期。")
                if reset_password != reset_confirm:
                    raise ValueError("两次输入的密码不一致。")
                reset_password_with_code(reset_user.id, reset_code, reset_password)
                st.success("密码已重置，请返回登录。")
            except (ValueError, ProjectAccessDeniedError) as exc:
                render_user_error(exc, fallback="密码重置失败，请检查验证码。")
    with register_tab:
        verification_email = st.text_input("待验证邮箱", key="verification_email")
        if st.button("重新发送验证邮件"):
            try:
                account = get_user_by_email(verification_email)
                if not mail_configured():
                    raise ValueError("邮件服务待配置，未发送验证码。")
                if account and not account.email_verified:
                    send_verification_email(account.email, issue_email_verification(account.id))
                st.info("如存在待验证账号，验证码已发送。")
            except ValueError as exc:
                render_user_error(exc)
        code = st.text_input("注册邮箱验证码")
        if st.button("验证邮箱"):
            try:
                account = get_user_by_email(verification_email)
                if not account:
                    raise ValueError("验证码不正确或已过期。")
                verify_email(account.id, code)
                st.success("邮箱已验证，请返回登录。")
            except (ValueError, ProjectAccessDeniedError) as exc:
                render_user_error(exc)


user = _current_user()
if user is None:
    _login()
    render_footer()
    st.stop()

if user.force_password_change:
    st.warning("这是初始密码，请先设置新的登录密码。")
    with st.form("forced_password_change"):
        new_password = st.text_input("新密码", type="password")
        confirm_password = st.text_input("确认新密码", type="password")
        change_password = st.form_submit_button("保存新密码", type="primary")
    if change_password:
        try:
            if new_password != confirm_password:
                raise ValueError("两次输入的密码不一致。")
            set_password(user.id, new_password)
            st.success("密码已更新，请继续使用当前会话。")
            st.rerun()
        except ValueError as exc:
            render_user_error(exc, fallback="密码更新失败。")
    render_footer()
    st.stop()

projects = list_user_projects(user.id)
if not projects:
    st.warning("当前账号还没有加入任何项目。")
    render_footer()
    st.stop()

project_labels = {item.id: f"{item.name} · {item.product_name}" for item in projects}
project_id = st.sidebar.selectbox(
    "授权项目",
    options=list(project_labels),
    format_func=lambda item: project_labels[item],
    key="chat_project_id",
)

with st.sidebar:
    st.markdown(f"**当前账号**  \n{user.display_name}  \n{user.email}")
    if st.button("退出登录", key="chat_logout", width="stretch"):
        revoke_session(st.session_state.get("auth_token", ""))
        clear_private_state()
        st.session_state["_auth_nav_visible"] = False
        st.rerun()


members = list_project_members(project_id, user.id)
users_by_id = {item.id: item for item in list_users(include_inactive=True)}
role_by_user = {item.user_id: item.role for item in members}


def _member_label(item) -> str:
    member_user = users_by_id.get(item.user_id)
    display_name = member_user.display_name if member_user else item.user_id
    return f"{display_name}（{role_by_user.get(item.user_id, item.role)}）"


st.caption("项目成员：" + "、".join(_member_label(item) for item in members))

left, right = st.columns([1.45, 0.55], gap="large")
with left:
    st.subheader("频道消息")
    messages = list_messages(
        project_id=project_id,
        session_token=st.session_state.get("auth_token"),
        limit=100,
    )
    if not messages:
        st.info("还没有消息。发送第一条项目更新或上传一个 CSV/TXT 文件。")
    for message in reversed(messages):
        sender = users_by_id.get(message.sender_id)
        sender_name = sender.display_name if sender else f"用户 {message.sender_id}"
        mine = message.sender_id == user.id
        bubble_class = "tl-chat-bubble tl-chat-bubble--mine" if mine else "tl-chat-bubble"
        st.markdown(
            f'<div class="{bubble_class}"><div class="tl-chat-meta">'
            f"{html.escape('我' if mine else sender_name)} · {message.created_at:%Y-%m-%d %H:%M}"
            f"</div><div>{html.escape(message.content)}</div></div>",
            unsafe_allow_html=True,
        )
        if message.artifact_id:
            try:
                filename, raw, mime = download_project_file(
                    project_id=project_id,
                    session_token=st.session_state.get("auth_token"),
                    artifact_id=message.artifact_id,
                )
                st.download_button(
                    f"下载附件：{filename}",
                    data=raw,
                    file_name=filename,
                    mime=mime,
                    key=f"download_{message.id}",
                )
            except Exception as exc:
                st.caption(safe_error_message(exc, fallback="附件当前不可用。"))

    with st.form("send_channel_message", clear_on_submit=True):
        content = st.text_area(
            "发送消息", placeholder="例如：供应商已补充交期证据，请采购负责人确认。"
        )
        send = st.form_submit_button("发送", type="primary", width="stretch")
    if send:
        try:
            send_message(
                project_id=project_id,
                session_token=st.session_state.get("auth_token"),
                content=content,
                client_request_id=(
                    f"ui-{user.id}-{st.session_state.get('chat_message_nonce', 0) + 1}"
                ),
            )
            st.session_state["chat_message_nonce"] = (
                st.session_state.get("chat_message_nonce", 0) + 1
            )
            st.rerun()
        except Exception as exc:
            render_user_error(exc, fallback="消息发送失败。")

with right:
    st.subheader("上传项目文件")
    st.caption(
        "上传与当前项目有关的报价、合同、商品规格、客户评价或交付材料。"
        "支持 PDF、Word、Excel、CSV 和 TXT。"
    )
    st.markdown('<div class="tl-file-upload">', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "选择文件",
        type=["csv", "txt", "pdf", "docx", "xlsx", "png", "jpg", "jpeg"],
        key="project_file_upload",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    if st.button("上传并发送附件消息", disabled=uploaded is None, width="stretch"):
        try:
            artifact = upload_project_file(
                project_id=project_id,
                session_token=st.session_state.get("auth_token"),
                source=uploaded,
                filename=uploaded.name,
            )
            send_message(
                project_id=project_id,
                session_token=st.session_state.get("auth_token"),
                content=f"上传文件：{artifact.original_filename}",
                client_request_id=f"file-{artifact.sha256}",
                message_type="attachment",
                artifact_id=artifact.id,
            )
            st.success("文件已保存并关联到项目频道。")
            st.rerun()
        except Exception as exc:
            render_user_error(exc, fallback="文件上传失败。")

    st.subheader("当前项目事实")
    project = next(item for item in projects if item.id == project_id)
    markets = json.loads(project.markets_json)
    st.markdown(f"**项目名称：** {project.name}")
    st.markdown(f"**产品：** {project.product_name}")
    market_labels = ", ".join({"US": "美国", "DE": "德国"}.get(item, item) for item in markets)
    st.markdown(f"**目标市场：** {market_labels}")
    st.markdown("**数据来源：** 当前项目数据库")
    st.markdown("**权限状态：** 已通过项目成员权限检查")
    st.markdown("**AI 状态：** 本页面未调用 AI")

render_footer()
