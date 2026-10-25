from datetime import datetime

from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import CrossProjectReferenceError, InvalidStateTransitionError
from core.models import AuditEvent, Finding, utc_now

ALLOWED_REVIEW_DECISIONS = {"accepted", "revised", "rejected"}


def review_finding(
    *,
    project_id: int,
    finding_id: int,
    decision: str,
    reviewer: str,
    note: str,
    revised_statement: str = "",
    reviewed_at: datetime | None = None,
    session: Session | None = None,
) -> Finding:
    if decision not in ALLOWED_REVIEW_DECISIONS:
        raise InvalidStateTransitionError("无效的审核决定。")
    if decision in {"revised", "rejected"} and not note.strip():
        raise ValueError("修改或驳回时必须填写理由。")
    if decision == "revised" and not revised_statement.strip():
        raise ValueError("修改结论时必须填写修改后的结论。")

    with session_context(session) as db:
        finding = db.get(Finding, finding_id)
        if not finding or finding.project_id != project_id:
            raise CrossProjectReferenceError("发现不存在或不属于当前项目。")
        if finding.review_status not in {"draft", "pending_review"}:
            raise InvalidStateTransitionError("该发现已经完成审核。")
        if decision == "revised":
            finding.statement = revised_statement.strip()
        finding.review_status = decision
        finding.reviewed_by = reviewer.strip()
        finding.reviewed_at = reviewed_at or utc_now()
        finding.review_note = note.strip()
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role=reviewer,
                action=f"finding_{decision}",
                entity_type="finding",
                entity_id=finding.id,
            )
        )
        db.flush()
        return finding

