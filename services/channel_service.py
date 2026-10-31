"""Project channel persistence with server-side membership and idempotency."""

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import CrossProjectReferenceError, ProjectAccessDeniedError
from core.models import Artifact, ChannelMessage
from services.auth_service import require_session_member

MAX_MESSAGE_LENGTH = 10_000


def send_message(
    *,
    project_id: int,
    session_token: str,
    content: str,
    client_request_id: str,
    message_type: str = "text",
    reply_to_id: int | None = None,
    artifact_id: int | None = None,
    session: Session | None = None,
) -> ChannelMessage:
    text = content.strip()
    request_id = client_request_id.strip()
    if not text or len(text) > MAX_MESSAGE_LENGTH:
        raise ValueError("消息内容不能为空且不能超过 10000 个字符。")
    if not request_id or len(request_id) > 120:
        raise ValueError("client_request_id 必须是 1 到 120 个字符。")
    if message_type not in {"text", "system", "attachment"}:
        raise ValueError("不支持的消息类型。")

    with session_context(session) as db:
        actor, _membership = require_session_member(session_token, project_id, session=db)
        actor_user_id = actor.id
        existing = db.scalar(
            select(ChannelMessage).where(
                ChannelMessage.project_id == project_id,
                ChannelMessage.sender_id == actor_user_id,
                ChannelMessage.client_request_id == request_id,
            )
        )
        if existing:
            return existing
        if reply_to_id is not None:
            reply = db.get(ChannelMessage, reply_to_id)
            if not reply or reply.project_id != project_id:
                raise CrossProjectReferenceError("回复消息不属于当前项目。")
        if artifact_id is not None:
            artifact = db.get(Artifact, artifact_id)
            if not artifact or artifact.project_id != project_id:
                raise CrossProjectReferenceError("附件不属于当前项目。")
        message = ChannelMessage(
            project_id=project_id,
            sender_id=actor_user_id,
            message_type=message_type,
            content=text,
            reply_to_id=reply_to_id,
            artifact_id=artifact_id,
            client_request_id=request_id,
        )
        db.add(message)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            duplicate = db.scalar(
                select(ChannelMessage).where(
                    ChannelMessage.project_id == project_id,
                    ChannelMessage.sender_id == actor_user_id,
                    ChannelMessage.client_request_id == request_id,
                )
            )
            if duplicate:
                return duplicate
            raise
        return message


def list_messages(
    *,
    project_id: int,
    session_token: str,
    limit: int = 50,
    before: tuple[datetime, int] | None = None,
    session: Session | None = None,
) -> list[ChannelMessage]:
    if limit < 1 or limit > 100:
        raise ValueError("limit 必须在 1 到 100 之间。")
    with session_context(session) as db:
        require_session_member(session_token, project_id, session=db)
        statement = select(ChannelMessage).where(ChannelMessage.project_id == project_id)
        if before is not None:
            created_at, message_id = before
            statement = statement.where(
                or_(
                    ChannelMessage.created_at < created_at,
                    and_(
                        ChannelMessage.created_at == created_at,
                        ChannelMessage.id < message_id,
                    ),
                )
            )
        return list(
            db.scalars(
                statement.order_by(
                    ChannelMessage.created_at.desc(), ChannelMessage.id.desc()
                ).limit(limit)
            )
        )


def get_message(
    *,
    project_id: int,
    session_token: str,
    message_id: int,
    session: Session | None = None,
) -> ChannelMessage:
    with session_context(session) as db:
        require_session_member(session_token, project_id, session=db)
        message = db.get(ChannelMessage, message_id)
        if not message or message.project_id != project_id:
            raise ProjectAccessDeniedError("消息不存在或不属于当前项目。")
        return message
