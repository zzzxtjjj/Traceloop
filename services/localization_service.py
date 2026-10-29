import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import CrossProjectReferenceError
from core.models import Generation, Project

MARKET_LANGUAGES = {"US": "en-US", "DE": "de-DE"}
MANUAL_PROMPT_VERSION = "manual_market_content_v1"


def _clean_required(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{label}不能为空。")
    return cleaned


def _require_project_market(db: Session, project_id: int, market: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise CrossProjectReferenceError("项目不存在。")
    if market not in MARKET_LANGUAGES:
        raise ValueError("仅支持 US 或 DE 市场。")
    if market not in set(json.loads(project.markets_json)):
        raise ValueError("当前项目未启用所选市场。")
    return project


def create_v1_generation(
    *,
    project_id: int,
    market: str,
    content: str,
    session: Session | None = None,
) -> Generation:
    cleaned_content = _clean_required(content, "V1 内容")
    with session_context(session) as db:
        _require_project_market(db, project_id, market)
        generation = Generation(
            project_id=project_id,
            market=market,
            language=MARKET_LANGUAGES[market],
            version=1,
            parent_id=None,
            feedback="",
            content=cleaned_content,
            prompt_version=MANUAL_PROMPT_VERSION,
        )
        db.add(generation)
        db.flush()
        return generation


def create_v2_generation(
    *,
    project_id: int,
    parent_id: int,
    feedback: str,
    content: str,
    session: Session | None = None,
) -> Generation:
    cleaned_feedback = _clean_required(feedback, "修改反馈")
    cleaned_content = _clean_required(content, "V2 内容")
    with session_context(session) as db:
        parent = db.get(Generation, parent_id)
        if not parent or parent.project_id != project_id:
            raise CrossProjectReferenceError("V1 版本不存在或不属于当前项目。")
        if parent.version != 1 or parent.parent_id is not None:
            raise ValueError("V2 必须直接基于一个 V1 版本创建。")
        existing = db.scalar(
            select(Generation).where(
                Generation.project_id == project_id,
                Generation.parent_id == parent.id,
                Generation.version == 2,
            )
        )
        if existing:
            raise ValueError("该 V1 已经存在 V2，请选择其他 V1 或查看现有版本链。")
        generation = Generation(
            project_id=project_id,
            market=parent.market,
            language=parent.language,
            version=2,
            parent_id=parent.id,
            feedback=cleaned_feedback,
            content=cleaned_content,
            prompt_version=MANUAL_PROMPT_VERSION,
        )
        db.add(generation)
        db.flush()
        return generation


def list_generations(
    project_id: int,
    *,
    market: str | None = None,
    session: Session | None = None,
) -> list[Generation]:
    with session_context(session) as db:
        statement = select(Generation).where(Generation.project_id == project_id)
        if market is not None:
            if market not in MARKET_LANGUAGES:
                raise ValueError("仅支持 US 或 DE 市场。")
            statement = statement.where(Generation.market == market)
        return list(db.scalars(statement.order_by(Generation.id)).all())
