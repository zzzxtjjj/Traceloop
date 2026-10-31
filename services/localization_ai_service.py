"""Evidence-grounded model copy and append-only feedback rounds."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import CrossProjectReferenceError, ModelOutputValidationError, TradeLoopError
from core.models import AiRun, AuditEvent, Evidence, Generation
from services.ai_service import run_structured_model
from services.localization_service import MARKET_LANGUAGES, _require_project_market
from services.membership_service import require_project_role
from services.model_provider import OpenAICompatibleProvider
from services.model_readiness import validate_model_input_budget

PROMPT_VERSION = "localize_evidence_v1"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / f"{PROMPT_VERSION}.txt"


class CopyClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1)
    evidence_ids: list[int] = Field(min_length=1)


class LocalizedCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: CopyClaim
    bullets: list[CopyClaim] = Field(min_length=1, max_length=5)
    description: CopyClaim
    missing_information: list[str]
    review_notes: list[str]


def generate_localized_copy(
    *,
    project_id: int,
    user_id: int,
    market: str,
    evidence_ids: list[int],
    facts_confirmed: bool,
    parent_id: int | None = None,
    feedback: str = "",
    provider=None,
    session: Session | None = None,
) -> Generation:
    """Owner confirms which source facts may be used. No automatic publishing."""
    failure = None
    result = None
    with session_context(session) as db:
        require_project_role(project_id, user_id, {"owner"}, session=db)
        _require_project_market(db, project_id, market)
        if not facts_confirmed or not evidence_ids:
            raise ValueError("请由负责人确认商品事实并选择来源依据。")
        sources = []
        for source_id in sorted(set(evidence_ids)):
            source = db.get(Evidence, source_id)
            if not source or source.project_id != project_id:
                raise CrossProjectReferenceError("来源依据不存在或不属于当前项目。")
            if not source.excerpt.strip():
                raise ValueError("商品事实依据不能为空。")
            sources.append({"evidence_id": source.id, "text": source.excerpt})

        history = []
        parent = db.get(Generation, parent_id) if parent_id is not None else None
        if parent_id is not None:
            if not parent or parent.project_id != project_id or parent.market != market:
                raise CrossProjectReferenceError("父版本不存在或不属于当前项目和市场。")
            if parent.prompt_version != PROMPT_VERSION:
                raise ValueError("请从模型生成的版本继续修订，人工版本保留原入口。")
            if not feedback.strip():
                raise ValueError("请填写本轮修改意见。")
            existing = db.scalar(select(Generation).where(Generation.parent_id == parent.id))
            if existing:
                raise ValueError("该版本已有后续版本，请选择最新版本继续。")
            cursor = parent
            visited = set()
            while cursor:
                if cursor.id in visited or cursor.project_id != project_id:
                    raise ValueError("版本历史异常，不能继续生成。")
                visited.add(cursor.id)
                envelope = json.loads(cursor.content)
                if envelope["sources"] != sources:
                    raise ValueError("修订必须沿用同一组商品事实；变更事实请创建新的初稿。")
                history.append(
                    {
                        "version": cursor.version,
                        "feedback": cursor.feedback,
                        "copy": envelope["output"],
                    }
                )
                cursor = db.get(Generation, cursor.parent_id) if cursor.parent_id else None
            history.reverse()
        elif feedback.strip():
            raise ValueError("初稿无需修改反馈。")

        context = {
            "market": market,
            "language": MARKET_LANGUAGES[market],
            "platform": "google_merchant",
            "confirmed_sources": sources,
            "history": history,
            "feedback": feedback.strip(),
        }
        if parent:
            checks = db.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.project_id == project_id,
                    AuditEvent.entity_type == "generation",
                    AuditEvent.entity_id == parent.id,
                    AuditEvent.action == "generation_rule_check",
                )
                .order_by(AuditEvent.id)
            ).all()
            context["previous_rule_checks"] = [json.loads(item.detail_json) for item in checks]
        prompt = (
            PROMPT_PATH.read_text(encoding="utf-8") + "\n" + json.dumps(context, ensure_ascii=False)
        )
        active = provider or OpenAICompatibleProvider.from_settings()
        validate_model_input_budget(
            prompt=prompt,
            review_count=0,
            max_input_chars=getattr(active, "max_input_chars", None),
        )
        try:
            output = run_structured_model(
                project_id=project_id,
                run_type="localized_copy",
                prompt_version=PROMPT_VERSION,
                prompt=prompt,
                evidence_ids=evidence_ids,
                output_model=LocalizedCopy,
                provider=active,
                session=db,
            )
        except TradeLoopError as exc:
            failure = exc
        else:
            run = db.scalar(
                select(AiRun)
                .where(AiRun.project_id == project_id, AiRun.run_type == "localized_copy")
                .order_by(AiRun.id.desc())
            )
            allowed = set(evidence_ids)
            claims = [output.title, *output.bullets, output.description]
            copy_unchanged = False
            if parent:
                previous = json.loads(parent.content)["output"]
                copy_unchanged = (
                    output.title.text == previous["title"]["text"]
                    and output.description.text == previous["description"]["text"]
                    and [item.text for item in output.bullets]
                    == [item["text"] for item in previous["bullets"]]
                )
            if copy_unchanged:
                run.status = "failed"
                run.error_code = "MODEL_REVISION_UNCHANGED"
                failure = ModelOutputValidationError("正文没有按反馈修改，请明确修改要求后重试。")
            elif len(output.title.text) > 150:
                run.status = "failed"
                run.error_code = "MODEL_TITLE_TOO_LONG"
                failure = ModelOutputValidationError("商品标题超过150字符，请缩短后重试。")
            elif any(not set(claim.evidence_ids) <= allowed for claim in claims):
                run.status = "failed"
                run.error_code = "MODEL_EVIDENCE_INVALID"
                failure = ModelOutputValidationError("模型引用了不存在或未确认的依据。")
            else:
                result = Generation(
                    project_id=project_id,
                    market=market,
                    language=MARKET_LANGUAGES[market],
                    version=parent.version + 1 if parent else 1,
                    parent_id=parent_id,
                    feedback=feedback.strip(),
                    prompt_version=PROMPT_VERSION,
                    content=json.dumps(
                        {
                            "platform": "google_merchant",
                            "sources": sources,
                            "ai_run_id": run.id,
                            "output": output.model_dump(),
                        },
                        ensure_ascii=False,
                    ),
                )
                db.add(result)
                db.flush()
                db.add(
                    AuditEvent(
                        project_id=project_id,
                        actor_role="owner",
                        action="localized_copy_generated",
                        entity_type="generation",
                        entity_id=result.id,
                        detail_json=json.dumps(
                            {"user_id": user_id, "facts_confirmed": True, "ai_run_id": run.id}
                        ),
                    )
                )
                from services.localization_workflow import check_generation

                check_generation(
                    project_id=project_id, user_id=user_id, generation_id=result.id, session=db
                )
        db.flush()
    if failure:
        raise failure
    return result
