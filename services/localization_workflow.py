"""Authorized version queries, rule snapshots and human content review."""

import difflib
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import CrossProjectReferenceError, RuleSourceError
from core.models import AuditEvent, Generation
from services.membership_service import require_project_member, require_project_role
from services.rule_service import RULES_FILE, run_rule_checks


def _generation(db, project_id, generation_id):
    item = db.get(Generation, generation_id)
    if not item or item.project_id != project_id:
        raise CrossProjectReferenceError("文案不存在或不属于当前项目。")
    return item


def _events(db, item, action):
    return list(
        db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.project_id == item.project_id,
                AuditEvent.entity_type == "generation",
                AuditEvent.entity_id == item.id,
                AuditEvent.action == action,
            )
            .order_by(AuditEvent.id)
        )
    )


def _output(item):
    try:
        return json.loads(item.content)["output"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("该版本不是结构化模型文案，请使用人工文案入口。") from exc


def list_project_localizations(
    *,
    project_id: int,
    user_id: int,
    session: Session | None = None,
) -> list[dict]:
    from services.localization_ai_service import PROMPT_VERSION

    with session_context(session) as db:
        require_project_member(project_id, user_id, session=db)
        items = db.scalars(
            select(Generation)
            .where(
                Generation.project_id == project_id,
                Generation.prompt_version == PROMPT_VERSION,
            )
            .order_by(Generation.id)
        ).all()
        return [
            {
                "id": item.id,
                "market": item.market,
                "language": item.language,
                "version": item.version,
                "parent_id": item.parent_id,
                "title": _output(item)["title"]["text"],
            }
            for item in items
        ]


def check_generation(
    *,
    project_id: int,
    user_id: int,
    generation_id: int,
    scenario: str = "platform_product",
    text: str | None = None,
    rules_path=RULES_FILE,
    session: Session | None = None,
) -> dict:
    """Platform checks use the actual title, never the JSON envelope."""
    with session_context(session) as db:
        require_project_member(project_id, user_id, session=db)
        item = _generation(db, project_id, generation_id)
        if scenario == "platform_product":
            checked_text = _output(item)["title"]["text"]
            target = "title"
        elif scenario in {"procurement", "consumer_contract"}:
            if not text or not text.strip():
                raise ValueError("请提供要检查的条款，不要用商品标题代替合同。")
            checked_text = text.strip()
            target = "attached_terms"
        else:
            raise ValueError("不支持的检查场景。")
        digest = hashlib.sha256(checked_text.encode("utf-8")).hexdigest()
        try:
            results = run_rule_checks(
                project_id=project_id,
                market=item.market,
                scenario=scenario,
                text=checked_text,
                rules_path=rules_path,
                session=db,
            )
            evaluations = [result.model_dump(mode="json") for result in results]
            error = None
        except RuleSourceError:
            evaluations = []
            error = "规则资料不可用或当前场景未覆盖，需要人工复核。"
        snapshot = {
            "generation_id": item.id,
            "version": item.version,
            "scenario": scenario,
            "target": target,
            "text": checked_text,
            "input_hash": digest,
            "results": evaluations,
            "error": error,
            "user_id": user_id,
            "requires_human_review": True,
        }
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role="member",
                action="generation_rule_check",
                entity_type="generation",
                entity_id=item.id,
                detail_json=json.dumps(snapshot, ensure_ascii=False),
            )
        )
        db.flush()
        return snapshot


def get_generation_chain(
    *,
    project_id: int,
    user_id: int,
    generation_id: int,
    session: Session | None = None,
) -> list[dict]:
    """Return ancestors through the selected version, with snapshots and text diffs."""
    with session_context(session) as db:
        require_project_member(project_id, user_id, session=db)
        cursor = _generation(db, project_id, generation_id)
        chain = []
        visited = set()
        while cursor:
            if cursor.id in visited:
                raise ValueError("版本链异常：存在循环。")
            visited.add(cursor.id)
            checks = [
                json.loads(event.detail_json)
                for event in _events(db, cursor, "generation_rule_check")
            ]
            reviews = [
                json.loads(event.detail_json)
                for event in _events(db, cursor, "generation_human_review")
            ]
            chain.append(
                {
                    "id": cursor.id,
                    "version": cursor.version,
                    "parent_id": cursor.parent_id,
                    "market": cursor.market,
                    "language": cursor.language,
                    "feedback": cursor.feedback,
                    "content": json.loads(cursor.content),
                    "checks": checks,
                    "reviews": reviews,
                    "review_status": reviews[-1]["decision"] if reviews else "pending_review",
                }
            )
            cursor = _generation(db, project_id, cursor.parent_id) if cursor.parent_id else None
        chain.reverse()
        for index, version in enumerate(chain):
            before = chain[index - 1]["content"]["output"] if index else {}
            after = version["content"]["output"]
            version["diff"] = "\n".join(
                difflib.unified_diff(
                    json.dumps(before, ensure_ascii=False, indent=2).splitlines(),
                    json.dumps(after, ensure_ascii=False, indent=2).splitlines(),
                    fromfile="previous",
                    tofile=f"V{version['version']}",
                    lineterm="",
                )
            )
        return chain


def review_generation(
    *,
    project_id: int,
    user_id: int,
    generation_id: int,
    decision: str,
    note: str,
    session: Session | None = None,
) -> dict:
    if decision not in {"accepted", "rejected"} or not note.strip():
        raise ValueError("请明确接受或驳回，并填写人工审核意见。")
    with session_context(session) as db:
        require_project_role(project_id, user_id, {"owner"}, session=db)
        item = _generation(db, project_id, generation_id)
        snapshot = check_generation(
            project_id=project_id, user_id=user_id, generation_id=generation_id, session=db
        )
        if decision == "accepted" and (
            snapshot["error"]
            or not any(result["status"] == "passed" for result in snapshot["results"])
            or any(result["status"] == "failed" for result in snapshot["results"])
        ):
            raise ValueError("规则检查不可用或存在未解决风险，不能确认文案。")
        review = {
            "decision": decision,
            "note": note.strip(),
            "user_id": user_id,
            "generation_id": item.id,
            "version": item.version,
            "content_hash": hashlib.sha256(item.content.encode("utf-8")).hexdigest(),
            "limitation": "人工内容审核不等于平台批准或全面法律合规。",
        }
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role="owner",
                action="generation_human_review",
                entity_type="generation",
                entity_id=item.id,
                detail_json=json.dumps(review, ensure_ascii=False),
            )
        )
        db.flush()
        return review
