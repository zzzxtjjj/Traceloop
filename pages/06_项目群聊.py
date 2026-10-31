import json

import streamlit as st

from core.access_ui import render_user_error, safe_error_message
from core.db import init_db
from core.theme import apply_brand_theme, render_footer, render_page_header
from services.auth_service import authenticate, create_session, resolve_session, revoke_session
from services.channel_service import list_messages, send_message
from services.file_service import download_project_file, upload_project_file
from services.membership_service import list_project_members, list_user_projects, list_users
from services.project_service import verify_project_access

init_db()
st.set_page_config(page_title="项目群聊 · TradeLoop", page_icon="💬", layout="wide")
apply_brand_theme()
render_page_header(
    "PROJECT CHANNEL · 项目群聊",
    "把讨论、文件和证据留在同一个项目里",
    "消息从数据库读取，附件进入受控项目文件库；每次访问都重新校验服务端会话和项目成员关系。",
)


def _current_user():
    token = st.session_state.get("auth_token")
    if not token:
        return None
    try:
        return resolve_session(token)
    except Exception:
        st.session_state.pop("auth_token", None)
        return None


def _login() -> None:
    st.subheader("登录 TradeLoop")
    st.caption("本页面使用服务端密码会话；项目角色来自 ProjectMember，不接受客户端自行指定。")
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


user = _current_user()
if user is None:
    _login()
    render_footer()
    st.stop()

with st.sidebar:
    st.markdown(f"**当前账号**  \n{user.display_name}  \n{user.email}")
    if st.button("退出登录", key="chat_logout", width="stretch"):
        revoke_session(st.session_state.get("auth_token", ""))
        st.session_state.pop("auth_token", None)
        st.rerun()

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

unlocked = set(st.session_state.get("chat_unlocked_project_ids", []))
if project_id not in unlocked:
    st.info("请输入项目访问码完成演示层解锁；这不会替代服务端成员权限检查。")
    with st.form("chat_unlock"):
        access_code = st.text_input("项目访问码", type="password")
        unlock = st.form_submit_button("进入项目频道", type="primary")
    if unlock:
        if verify_project_access(project_id, access_code):
            unlocked.add(project_id)
            st.session_state["chat_unlocked_project_ids"] = list(unlocked)
            st.rerun()
        st.error("访问码不正确。")
    render_footer()
    st.stop()

members = list_project_members(project_id, user.id)
users_by_id = {item.id: item for item in list_users(include_inactive=True)}
role_by_user = {item.user_id: item.role for item in members}


def _member_label(item) -> str:
    member_user = users_by_id.get(item.user_id)
    display_name = member_user.display_name if member_user else item.user_id
    return f"{display_name}（{role_by_user.get(item.user_id, item.role)}）"


st.caption(
    "项目成员："
    + "、".join(_member_label(item) for item in members)
)

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
        with st.container(border=True):
            st.markdown(f"**{sender_name}** · {message.created_at:%Y-%m-%d %H:%M}")
            st.write(message.content)
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
    st.caption("白名单：CSV、TXT、PDF、DOCX、XLSX；首期仅 CSV/TXT 进入确定性解析。")
    uploaded = st.file_uploader("选择文件", type=["csv", "txt", "pdf", "docx", "xlsx"])
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
    st.json(
        {
            "project_id": project.id,
            "markets": json.loads(project.markets_json),
            "message_source": "database",
            "permission_source": "ProjectMember",
            "ai_status": "not invoked by chat page",
        }
    )

render_footer()
