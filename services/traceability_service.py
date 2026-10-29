import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import CrossProjectReferenceError
from core.models import (
    Evidence,
    EvidenceLink,
    Finding,
    ImprovementRecord,
    ReviewBatch,
    Task,
    TaskSubmission,
)


@dataclass(frozen=True)
class EvidenceTrace:
    id: int
    source_entity_type: str
    source_entity_id: int
    locator: dict[str, Any]
    excerpt: str


@dataclass(frozen=True)
class SubmissionTrace:
    id: int
    content: str
    evidence_id: int
    evidence_excerpt: str
    review_status: str
    submitted_by_role: str
    reviewed_by: str | None
    review_note: str


@dataclass(frozen=True)
class TaskTrace:
    id: int
    title: str
    owner_role: str
    status: str
    confirmed: bool
    submissions: list[SubmissionTrace] = field(default_factory=list)


@dataclass(frozen=True)
class BatchTrace:
    id: int
    name: str
    market: str
    sample_size: int


@dataclass(frozen=True)
class ImprovementTrace:
    id: int
    status: str
    theme: str
    baseline: BatchTrace
    followup: BatchTrace | None
    baseline_count: int
    baseline_share: float
    followup_count: int | None
    followup_share: float | None
    count_delta: int | None
    share_delta: float | None
    limitation_note: str


@dataclass(frozen=True)
class FindingTrace:
    finding_id: int
    finding_review_status: str
    evidence_status: str
    task_status: str
    delivery_status: str
    improvement_status: str
    recheck_status: str
    evidence: list[EvidenceTrace]
    task: TaskTrace | None
    improvement: ImprovementTrace | None


def _batch_trace(db: Session, project_id: int, batch_id: int) -> BatchTrace:
    batch = db.get(ReviewBatch, batch_id)
    if not batch or batch.project_id != project_id:
        raise CrossProjectReferenceError("评价批次不存在或不属于当前项目。")
    return BatchTrace(
        id=batch.id,
        name=batch.name,
        market=batch.market,
        sample_size=batch.sample_size,
    )


def get_finding_trace(
    *,
    project_id: int,
    finding_id: int,
    session: Session | None = None,
) -> FindingTrace:
    with session_context(session) as db:
        finding = db.get(Finding, finding_id)
        if not finding or finding.project_id != project_id:
            raise CrossProjectReferenceError("发现不存在或不属于当前项目。")

        evidence_rows = list(
            db.scalars(
                select(Evidence)
                .join(EvidenceLink, Evidence.id == EvidenceLink.evidence_id)
                .distinct()
                .where(
                    Evidence.project_id == project_id,
                    EvidenceLink.project_id == project_id,
                    EvidenceLink.target_type == "finding",
                    EvidenceLink.target_id == finding_id,
                )
                .order_by(Evidence.id)
            )
        )
        evidence = [
            EvidenceTrace(
                id=item.id,
                source_entity_type=item.source_entity_type,
                source_entity_id=item.source_entity_id,
                locator=json.loads(item.locator_json),
                excerpt=item.excerpt,
            )
            for item in evidence_rows
        ]

        task = db.scalar(
            select(Task)
            .where(
                Task.project_id == project_id,
                Task.source_type == "finding",
                Task.source_id == finding_id,
            )
            .order_by(Task.id)
        )
        task_trace: TaskTrace | None = None
        submissions: list[SubmissionTrace] = []
        if task:
            submission_rows = list(
                db.scalars(
                    select(TaskSubmission)
                    .where(
                        TaskSubmission.project_id == project_id,
                        TaskSubmission.task_id == task.id,
                    )
                    .order_by(TaskSubmission.id)
                )
            )
            for submission in submission_rows:
                delivery_evidence = db.get(Evidence, submission.evidence_id)
                if not delivery_evidence or delivery_evidence.project_id != project_id:
                    raise CrossProjectReferenceError("交付证据不存在或不属于当前项目。")
                submissions.append(
                    SubmissionTrace(
                        id=submission.id,
                        content=submission.content,
                        evidence_id=delivery_evidence.id,
                        evidence_excerpt=delivery_evidence.excerpt,
                        review_status=submission.review_status,
                        submitted_by_role=submission.submitted_by_role,
                        reviewed_by=submission.reviewed_by,
                        review_note=submission.review_note,
                    )
                )
            task_trace = TaskTrace(
                id=task.id,
                title=task.title,
                owner_role=task.owner_role,
                status=task.status,
                confirmed=task.confirmed,
                submissions=submissions,
            )

        improvement = db.scalar(
            select(ImprovementRecord)
            .where(
                ImprovementRecord.project_id == project_id,
                ImprovementRecord.finding_id == finding_id,
                *(
                    [ImprovementRecord.task_id == task.id]
                    if task is not None
                    else []
                ),
            )
            .order_by(ImprovementRecord.id)
        )
        improvement_trace: ImprovementTrace | None = None
        if improvement:
            baseline = _batch_trace(db, project_id, improvement.baseline_batch_id)
            followup = (
                _batch_trace(db, project_id, improvement.followup_batch_id)
                if improvement.followup_batch_id is not None
                else None
            )
            improvement_trace = ImprovementTrace(
                id=improvement.id,
                status=improvement.status,
                theme=improvement.theme,
                baseline=baseline,
                followup=followup,
                baseline_count=improvement.baseline_count,
                baseline_share=improvement.baseline_share,
                followup_count=improvement.followup_count,
                followup_share=improvement.followup_share,
                count_delta=improvement.count_delta,
                share_delta=improvement.share_delta,
                limitation_note=improvement.limitation_note,
            )

        if not submissions:
            delivery_status = "missing"
        elif any(item.review_status == "pending_review" for item in submissions):
            delivery_status = "pending"
        elif any(item.review_status == "accepted" for item in submissions):
            delivery_status = "accepted"
        else:
            delivery_status = "rejected"

        recheck_status = "missing"
        if improvement_trace:
            recheck_status = "completed" if improvement_trace.followup else "pending"

        return FindingTrace(
            finding_id=finding.id,
            finding_review_status=finding.review_status,
            evidence_status="available" if evidence else "missing",
            task_status="available" if task else "missing",
            delivery_status=delivery_status,
            improvement_status=improvement_trace.status if improvement_trace else "missing",
            recheck_status=recheck_status,
            evidence=evidence,
            task=task_trace,
            improvement=improvement_trace,
        )
