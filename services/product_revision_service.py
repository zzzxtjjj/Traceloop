"""Human edits of existing structured copy, preserving evidence and version ancestry."""

import json
import re

from sqlalchemy import select

from core.db import session_context
from core.errors import CrossProjectReferenceError, ProjectAccessDeniedError
from core.models import AuditEvent, Evidence, Generation
from services.auth_service import require_session_member
from services.localization_ai_service import LocalizedCopy
from services.localization_workflow import check_generation
from services.product_identity_service import assign_product, link_revision, product_for


def fact_screen(output, sources):
    """Conservative numeric screen, explicitly not a full semantic fact verifier."""
    source_text = " ".join(item["text"] for item in sources)
    claims = [output["title"], *output["bullets"], output["description"]]
    allowed = {item["evidence_id"] for item in sources}
    invalid_ids = sorted(
        {eid for claim in claims for eid in claim["evidence_ids"] if eid not in allowed}
    )
    missing_numbers = sorted(
        {
            number
            for claim in claims
            for number in re.findall(r"(?<!\w)\d+(?:[.,]\d+)?", claim["text"])
            if number.replace(",", ".") not in source_text.replace(",", ".")
        }
    )
    return {
        "evidence_ids_valid": not invalid_ids,
        "invalid_ids": invalid_ids,
        "unconfirmed_numeric_claims": missing_numbers,
        "status": "FAIL" if invalid_ids or missing_numbers else "PARTIAL",
        "limitation": "仅验证引用范围和数字原文出现情况，不证明翻译、认证、安全或性能声明真实。",
        "needs_review": True,
        "publishable": False,
    }


def revise_copy(
    *,
    project_id,
    session_token,
    product_id,
    parent_id,
    output,
    feedback,
    improvement_id=None,
    session=None,
):
    parsed = LocalizedCopy.model_validate(output)
    if not feedback.strip():
        raise ValueError("请记录修改原因和反馈依据。")
    with session_context(session) as db:
        actor, member = require_session_member(session_token, project_id, session=db)
        if member.role != "owner":
            raise ProjectAccessDeniedError("只有负责人可以保存修订版本。")
        parent = db.get(Generation, parent_id)
        if (
            not parent
            or parent.project_id != project_id
            or product_for(db, "generation", parent_id) != product_id
        ):
            raise CrossProjectReferenceError("原版本不属于当前产品。")
        if db.scalar(select(Generation.id).where(Generation.parent_id == parent_id)):
            raise ValueError("原版本已有后续版本，请选择最新版本。")
        envelope = json.loads(parent.content)
        if parsed.language != parent.language:
            raise ValueError("修订不能改变原版本语言。")
        if parsed.model_dump() == envelope["output"]:
            raise ValueError("内容未变化。")
        for source in envelope["sources"]:
            evidence = db.get(Evidence, source["evidence_id"])
            if (
                not evidence
                or evidence.project_id != project_id
                or evidence.excerpt != source["text"]
                or product_for(db, "evidence", evidence.id) != product_id
            ):
                raise CrossProjectReferenceError("原始依据发生变化或产品不匹配。")
        screen = fact_screen(parsed.model_dump(), envelope["sources"])
        if not screen["evidence_ids_valid"]:
            raise ValueError("文案引用了未授权的依据。")
        content = {
            **envelope,
            "output": parsed.model_dump(),
            "authoring_mode": "human_revision",
            "needs_review": True,
            "publishable": False,
            "fact_screen": screen,
        }
        result = Generation(
            project_id=project_id,
            market=parent.market,
            language=parent.language,
            parent_id=parent_id,
            version=parent.version + 1,
            feedback=feedback.strip(),
            prompt_version=parent.prompt_version,
            content=json.dumps(content, ensure_ascii=False),
        )
        db.add(result)
        db.flush()
        assign_product(
            project_id=project_id,
            session_token=session_token,
            product_id=product_id,
            kind="generation",
            entity_id=result.id,
            session=db,
        )
        if improvement_id:
            link_revision(
                project_id=project_id,
                session_token=session_token,
                product_id=product_id,
                improvement_id=improvement_id,
                original_generation_id=parent_id,
                revised_generation_id=result.id,
                session=db,
            )
        check_generation(
            project_id=project_id, user_id=actor.id, generation_id=result.id, session=db
        )
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role=member.role,
                action="localized_copy_human_revision",
                entity_type="generation",
                entity_id=result.id,
                detail_json=json.dumps(
                    {
                        "user_id": actor.id,
                        "parent_id": parent_id,
                        "improvement_id": improvement_id,
                        "fact_screen": screen,
                    },
                    ensure_ascii=False,
                ),
            )
        )
        db.flush()
        return result
