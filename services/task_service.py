import json
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import (
    CrossProjectReferenceError,
    EvidenceRequiredError,
    InvalidStateTransitionError,
)
from core.models import (
    AuditEvent,
    DailyReport,
    Evidence,
    EvidenceLink,
    ExtractedRequirement,
    Finding,
    ImprovementRecord,
    Insight,
    ReviewBatch,
    Task,
    TaskSubmission,
    utc_now,
)
from core.schemas import DailyRiskItem
from services.auth_service import require_session_member
from services.evidence_service import create_evidence, link_evidence
from services.membership_service import require_project_member

TASK_PUBLISH_ROLES = {"owner", "department_lead", "Project Owner", "Department Lead", "项目负责人"}
TASK_REVIEW_ROLES = TASK_PUBLISH_ROLES | {
    "reviewer_qa",
    "Reviewer / QA",
    "quality",
    "品控",
}


@dataclass(frozen=True)
class ProjectReviewSnapshot:
    project_id: int
    generated_at: object
    task_counts: dict[str, int]
    report_count: int
    accepted_delivery_count: int
    pending_delivery_count: int
    blocker_report_count: int
    risks: list[DailyRiskItem]

THEME_OWNER_ROLE = {
    "packaging_damage": "品控",
    "product_quality": "品控",
    "description_mismatch": "运营",
    "logistics_delay": "采购",
    "usage_difficulty": "运营",
    "customer_service": "运营",
    "other": "项目负责人",
}


def _theme_from_finding(finding: Finding) -> str:
    return finding.finding_type.rsplit(":", maxsplit=1)[-1]


def create_task_from_finding(
    *,
    project_id: int,
    finding_id: int,
    title: str | None = None,
    owner_role: str | None = None,
    acceptance_criteria: list[str] | None = None,
    due_in_days: int = 3,
    session: Session | None = None,
) -> Task:
    with session_context(session) as db:
        finding = db.get(Finding, finding_id)
        if not finding or finding.project_id != project_id:
            raise CrossProjectReferenceError("发现不存在或不属于当前项目。")
        if finding.review_status not in {"accepted", "revised"}:
            raise InvalidStateTransitionError("只有人工接受或修改后的发现才能创建任务。")
        existing = db.scalar(
            select(Task).where(
                Task.project_id == project_id,
                Task.source_type == "finding",
                Task.source_id == finding_id,
            )
        )
        if existing:
            return existing
        theme = _theme_from_finding(finding)
        criteria = acceptance_criteria or [
            "提交调查或改进结果说明",
            "附上可审核的交付材料",
            "明确仍未确认的信息",
        ]
        task = Task(
            project_id=project_id,
            source_type="finding",
            source_id=finding_id,
            title=title or f"调查并处理：{finding.statement[:80]}",
            owner_role=owner_role or THEME_OWNER_ROLE.get(theme, "项目负责人"),
            status="draft",
            acceptance_criteria_json=json.dumps(criteria, ensure_ascii=False),
            dependency="需先核查关联证据，不预设责任归属",
            due_at=utc_now() + timedelta(days=max(1, due_in_days)),
            confirmed=False,
        )
        db.add(task)
        db.flush()
        finding_evidence_ids = db.scalars(
            select(EvidenceLink.evidence_id).where(
                EvidenceLink.project_id == project_id,
                EvidenceLink.target_type == "finding",
                EvidenceLink.target_id == finding_id,
            )
        )
        for evidence_id in finding_evidence_ids:
            link_evidence(
                project_id=project_id,
                evidence_id=evidence_id,
                target_type="task",
                target_id=task.id,
                relation_type="source_for",
                session=db,
            )
        return task


def create_task_from_requirement(
    *,
    project_id: int,
    requirement_id: int,
    session_token: str,
    session: Session | None = None,
) -> Task:
    """Convert an AI requirement draft into a separate, unpublished Task draft."""
    with session_context(session) as db:
        _actor, _membership = require_session_member(session_token, project_id, session=db)
        requirement = db.get(ExtractedRequirement, requirement_id)
        if not requirement or requirement.project_id != project_id:
            raise CrossProjectReferenceError("需求不属于当前项目。")
        if not requirement.source_evidence_id:
            raise EvidenceRequiredError("需求缺少真实 Evidence，不能创建任务草稿。")
        existing = db.scalar(
            select(Task).where(
                Task.project_id == project_id,
                Task.source_type == "extracted_requirement",
                Task.source_id == requirement_id,
            )
        )
        if existing:
            return existing
        task = Task(
            project_id=project_id,
            source_type="extracted_requirement",
            source_id=requirement_id,
            title=requirement.statement.split("\n", 1)[0][:200],
            owner_role=requirement.owner_role,
            status="draft",
            acceptance_criteria_json=requirement.acceptance_criteria_json,
            dependency="AI 草稿必须经过授权发布和人工验收。",
            due_at=utc_now() + timedelta(days=3),
            confirmed=False,
        )
        db.add(task)
        db.flush()
        requirement.task_id = task.id
        link_evidence(
            project_id=project_id,
            evidence_id=requirement.source_evidence_id,
            target_type="task",
            target_id=task.id,
            relation_type="source_for",
            session=db,
        )
        db.flush()
        return task


def publish_task(
    *,
    project_id: int,
    task_id: int,
    session_token: str,
    session: Session | None = None,
) -> Task:
    """Publish a draft only after a server-side role check."""
    with session_context(session) as db:
        _actor, membership = require_session_member(session_token, project_id, session=db)
        if membership.role not in TASK_PUBLISH_ROLES:
            raise InvalidStateTransitionError("当前角色不能发布正式任务。")
        task = db.get(Task, task_id)
        if not task or task.project_id != project_id:
            raise CrossProjectReferenceError("任务不属于当前项目。")
        if task.status != "draft" or task.confirmed:
            raise InvalidStateTransitionError("只有未发布任务草稿可以发布。")
        criteria = json.loads(task.acceptance_criteria_json)
        if not criteria:
            raise ValueError("任务缺少验收标准，不能发布。")
        task.confirmed = True
        task.status = "todo"
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role=membership.role,
                action="task_published",
                entity_type="task",
                entity_id=task.id,
            )
        )
        db.flush()
        return task


def confirm_task(
    *,
    project_id: int,
    task_id: int,
    confirmer_role: str,
    session: Session | None = None,
) -> Task:
    with session_context(session) as db:
        task = db.get(Task, task_id)
        if not task or task.project_id != project_id:
            raise CrossProjectReferenceError("任务不存在或不属于当前项目。")
        if task.status != "draft":
            raise InvalidStateTransitionError("只有草稿任务可以发布。")
        criteria = json.loads(task.acceptance_criteria_json)
        if not criteria:
            raise ValueError("任务缺少验收标准，不能发布。")
        task.confirmed = True
        task.status = "todo"
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role=confirmer_role,
                action="task_confirmed",
                entity_type="task",
                entity_id=task.id,
            )
        )
        db.flush()
        return task


def create_improvement_record(
    *,
    project_id: int,
    finding_id: int,
    task_id: int,
    baseline_batch_id: int,
    session: Session | None = None,
) -> ImprovementRecord:
    with session_context(session) as db:
        finding = db.get(Finding, finding_id)
        task = db.get(Task, task_id)
        baseline_batch = db.get(ReviewBatch, baseline_batch_id)
        if (
            not finding
            or not task
            or not baseline_batch
            or finding.project_id != project_id
            or task.project_id != project_id
            or baseline_batch.project_id != project_id
        ):
            raise CrossProjectReferenceError(
                "Finding、任务或基线评价批次不存在或不属于当前项目。"
            )
        if task.source_type != "finding" or task.source_id != finding_id:
            raise CrossProjectReferenceError("任务未关联指定 Finding，不能建立改进记录。")
        if not task.confirmed:
            raise InvalidStateTransitionError("任务发布后才能建立改进记录。")
        theme = _theme_from_finding(finding)
        insight = db.scalar(
            select(Insight).where(Insight.batch_id == baseline_batch_id, Insight.theme == theme)
        )
        if not insight:
            raise ValueError("基线批次没有该主题的统计结果。")
        existing = db.scalar(
            select(ImprovementRecord).where(
                ImprovementRecord.project_id == project_id,
                ImprovementRecord.finding_id == finding_id,
                ImprovementRecord.task_id == task_id,
            )
        )
        if existing:
            return existing
        record = ImprovementRecord(
            project_id=project_id,
            finding_id=finding_id,
            task_id=task_id,
            baseline_batch_id=baseline_batch_id,
            theme=theme,
            baseline_count=insight.count,
            baseline_share=insight.share,
            baseline_sample_size=finding.sample_size or insight.count,
            status="planned",
            limitation_note="评价占比不是商品实际故障率；复检只描述趋势，不证明因果。",
            updated_at=utc_now(),
        )
        db.add(record)
        db.flush()
        return record


def list_tasks(project_id: int, session: Session | None = None) -> list[Task]:
    with session_context(session) as db:
        return list(
            db.scalars(
                select(Task).where(Task.project_id == project_id).order_by(Task.id.desc())
            )
        )


def list_improvement_records(
    project_id: int, session: Session | None = None
) -> list[ImprovementRecord]:
    with session_context(session) as db:
        return list(
            db.scalars(
                select(ImprovementRecord)
                .where(ImprovementRecord.project_id == project_id)
                .order_by(ImprovementRecord.id.desc())
            )
        )


def update_task_status(
    *,
    project_id: int,
    task_id: int,
    status: str,
    actor_role: str,
    session: Session | None = None,
) -> Task:
    allowed = {"todo", "doing", "blocked"}
    if status not in allowed:
        raise InvalidStateTransitionError("任务只能切换为待执行、执行中或被阻塞。")
    with session_context(session) as db:
        task = db.get(Task, task_id)
        if not task or task.project_id != project_id:
            raise CrossProjectReferenceError("任务不存在或不属于当前项目。")
        if not task.confirmed or task.status in {"draft", "pending_review", "completed"}:
            raise InvalidStateTransitionError("当前任务状态不能直接切换。")
        if actor_role not in {task.owner_role, "项目负责人"}:
            raise InvalidStateTransitionError("当前岗位不能更新该任务。")
        task.status = status
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role=actor_role,
                action=f"task_status_{status}",
                entity_type="task",
                entity_id=task.id,
            )
        )
        db.flush()
        return task


def submit_task_delivery(
    *,
    project_id: int,
    task_id: int,
    submitted_by_role: str,
    content: str,
    evidence_excerpt: str,
    submitted_by_user_id: int | None = None,
    session: Session | None = None,
) -> TaskSubmission:
    if not content.strip():
        raise ValueError("必须填写交付说明。")
    if not evidence_excerpt.strip():
        raise EvidenceRequiredError("缺少验收材料，任务不能提交验收。")
    with session_context(session) as db:
        task = db.get(Task, task_id)
        if not task or task.project_id != project_id:
            raise CrossProjectReferenceError("任务不存在或不属于当前项目。")
        if submitted_by_user_id is not None:
            require_project_member(project_id, submitted_by_user_id, session=db)
        if not task.confirmed or task.status not in {"todo", "doing", "blocked"}:
            raise InvalidStateTransitionError("当前任务不能提交验收。")
        if submitted_by_role not in {task.owner_role, "项目负责人"}:
            raise InvalidStateTransitionError("当前岗位不能提交该任务。")
        evidence = create_evidence(
            project_id=project_id,
            evidence_type="task_delivery",
            source_entity_type="task",
            source_entity_id=task.id,
            locator={"task_id": task.id, "submitted_by_role": submitted_by_role},
            excerpt=evidence_excerpt.strip(),
            session=db,
        )
        submission = TaskSubmission(
            project_id=project_id,
            task_id=task.id,
            submitted_by_user_id=submitted_by_user_id,
            submitted_by_role=submitted_by_role,
            content=content.strip(),
            evidence_id=evidence.id,
            review_status="pending_review",
        )
        db.add(submission)
        db.flush()
        link_evidence(
            project_id=project_id,
            evidence_id=evidence.id,
            target_type="task",
            target_id=task.id,
            relation_type="delivery_for",
            session=db,
        )
        task.status = "pending_review"
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role=submitted_by_role,
                action="task_delivery_submitted",
                entity_type="task_submission",
                entity_id=submission.id,
            )
        )
        db.flush()
        return submission


def submit_task_delivery_as_user(
    *,
    project_id: int,
    task_id: int,
    session_token: str,
    content: str,
    evidence_excerpt: str,
    session: Session | None = None,
) -> TaskSubmission:
    """Submit delivery with user identity and role resolved from the server session."""
    with session_context(session) as db:
        actor, membership = require_session_member(session_token, project_id, session=db)
        return submit_task_delivery(
            project_id=project_id,
            task_id=task_id,
            submitted_by_user_id=actor.id,
            submitted_by_role=membership.role,
            content=content,
            evidence_excerpt=evidence_excerpt,
            session=db,
        )


def review_task_submission(
    *,
    project_id: int,
    submission_id: int,
    decision: str,
    reviewer: str,
    note: str,
    session: Session | None = None,
) -> TaskSubmission:
    if decision not in {"accepted", "rejected"}:
        raise InvalidStateTransitionError("验收决定只能是接受或驳回。")
    if decision == "rejected" and not note.strip():
        raise ValueError("驳回交付时必须填写理由。")
    with session_context(session) as db:
        submission = db.get(TaskSubmission, submission_id)
        if not submission or submission.project_id != project_id:
            raise CrossProjectReferenceError("交付记录不存在或不属于当前项目。")
        if submission.review_status != "pending_review":
            raise InvalidStateTransitionError("该交付已经完成验收。")
        task = db.get(Task, submission.task_id)
        if not task or task.project_id != project_id:
            raise CrossProjectReferenceError("任务不存在或不属于当前项目。")
        if reviewer.strip() == submission.submitted_by_role.strip():
            raise InvalidStateTransitionError("交付提交人不能验收自己的交付。")
        submission.review_status = decision
        submission.reviewed_by = reviewer
        submission.review_note = note.strip()
        submission.reviewed_at = utc_now()
        task.status = "completed" if decision == "accepted" else "todo"
        if decision == "accepted":
            for record in db.scalars(
                select(ImprovementRecord).where(
                    ImprovementRecord.project_id == project_id,
                    ImprovementRecord.task_id == task.id,
                )
            ):
                record.status = "implemented"
                record.updated_at = utc_now()
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role=reviewer,
                action=f"task_delivery_{decision}",
                entity_type="task_submission",
                entity_id=submission.id,
            )
        )
        db.flush()
        return submission


def review_task_submission_as_user(
    *,
    project_id: int,
    submission_id: int,
    session_token: str,
    decision: str,
    note: str,
    session: Session | None = None,
) -> TaskSubmission:
    """Review a delivery using the authenticated user and persisted role."""
    if decision not in {"accepted", "rejected"}:
        raise InvalidStateTransitionError("验收决定只能是接受或驳回。")
    if decision == "rejected" and not note.strip():
        raise ValueError("驳回交付时必须填写理由。")
    with session_context(session) as db:
        actor, membership = require_session_member(session_token, project_id, session=db)
        if membership.role not in TASK_REVIEW_ROLES:
            raise InvalidStateTransitionError("当前角色不能执行人工验收。")
        submission = db.get(TaskSubmission, submission_id)
        if not submission or submission.project_id != project_id:
            raise CrossProjectReferenceError("交付记录不存在或不属于当前项目。")
        if submission.submitted_by_user_id == actor.id:
            raise InvalidStateTransitionError("任务提交者不能验收自己的成果。")
        if submission.review_status != "pending_review":
            raise InvalidStateTransitionError("该交付已经完成验收。")
        task = db.get(Task, submission.task_id)
        if not task or task.project_id != project_id:
            raise CrossProjectReferenceError("任务不存在或不属于当前项目。")
        submission.review_status = decision
        submission.reviewed_by = str(actor.id)
        submission.review_note = note.strip()
        submission.reviewed_at = utc_now()
        task.status = "completed" if decision == "accepted" else "todo"
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role=membership.role,
                action=f"task_delivery_{decision}",
                entity_type="task_submission",
                entity_id=submission.id,
            )
        )
        db.flush()
        return submission


def submit_daily_report(
    *,
    project_id: int,
    role: str,
    task_id: int | None,
    submitted_by_user_id: int | None = None,
    completed: str,
    evidence_text: str = "",
    blocker: str = "",
    next_plan: str = "",
    session: Session | None = None,
) -> DailyReport:
    if not completed.strip() and not blocker.strip():
        raise ValueError("日报至少需要填写完成项或阻塞事项。")
    with session_context(session) as db:
        task = db.get(Task, task_id) if task_id else None
        if task_id and (not task or task.project_id != project_id):
            raise CrossProjectReferenceError("日报引用的任务不属于当前项目。")
        if task and role not in {task.owner_role, "项目负责人"}:
            raise InvalidStateTransitionError("当前岗位不能提交该任务的日报。")
        report = DailyReport(
            project_id=project_id,
            submitted_by_user_id=submitted_by_user_id,
            role=role,
            task_id=task_id,
            completed=completed.strip(),
            evidence=evidence_text.strip(),
            blocker=blocker.strip(),
            next_plan=next_plan.strip(),
        )
        db.add(report)
        db.flush()
        if completed.strip() or blocker.strip() or evidence_text.strip():
            evidence = create_evidence(
                project_id=project_id,
                evidence_type="daily_report_claim",
                source_entity_type="daily_report",
                source_entity_id=report.id,
                locator={"report_id": report.id, "task_id": task_id, "role": role},
                excerpt="\n".join(
                    item
                    for item in [completed.strip(), evidence_text.strip(), blocker.strip()]
                    if item
                ),
                session=db,
            )
            if task:
                link_evidence(
                    project_id=project_id,
                    evidence_id=evidence.id,
                    target_type="task",
                    target_id=task.id,
                    relation_type="reported_for",
                    session=db,
                )
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role=role,
                action="daily_report_submitted",
                entity_type="daily_report",
                entity_id=report.id,
            )
        )
        db.flush()
        return report


def submit_daily_report_as_user(
    *,
    project_id: int,
    task_id: int | None,
    session_token: str,
    completed: str,
    evidence_text: str = "",
    blocker: str = "",
    next_plan: str = "",
    session: Session | None = None,
) -> DailyReport:
    with session_context(session) as db:
        actor, membership = require_session_member(session_token, project_id, session=db)
        return submit_daily_report(
            project_id=project_id,
            role=membership.role,
            task_id=task_id,
            submitted_by_user_id=actor.id,
            completed=completed,
            evidence_text=evidence_text,
            blocker=blocker,
            next_plan=next_plan,
            session=db,
        )


def list_task_submissions(
    project_id: int, session: Session | None = None
) -> list[TaskSubmission]:
    with session_context(session) as db:
        return list(
            db.scalars(
                select(TaskSubmission)
                .where(TaskSubmission.project_id == project_id)
                .order_by(TaskSubmission.id.desc())
            )
        )


def list_daily_reports(
    project_id: int, session: Session | None = None
) -> list[DailyReport]:
    with session_context(session) as db:
        return list(
            db.scalars(
                select(DailyReport)
                .where(DailyReport.project_id == project_id)
                .order_by(DailyReport.created_at.desc(), DailyReport.id.desc())
            )
        )


def build_daily_risk_review(
    project_id: int, session: Session | None = None
) -> list[DailyRiskItem]:
    with session_context(session) as db:
        tasks = list(db.scalars(select(Task).where(Task.project_id == project_id)))
        reports = list(
            db.scalars(select(DailyReport).where(DailyReport.project_id == project_id))
        )
        submissions = list(
            db.scalars(select(TaskSubmission).where(TaskSubmission.project_id == project_id))
        )
        report_task_ids = {report.task_id for report in reports if report.task_id}
        accepted_task_ids = {
            submission.task_id
            for submission in submissions
            if submission.review_status == "accepted"
        }
        risks: list[DailyRiskItem] = []
        now = utc_now()
        for task in tasks:
            if task.status == "blocked":
                risks.append(
                    DailyRiskItem(
                        risk_type="blocked_task",
                        severity="red",
                        task_id=task.id,
                        message=f"任务“{task.title}”处于被阻塞状态，需要负责人协调。",
                    )
                )
            if task.due_at and task.due_at < now and task.status != "completed":
                risks.append(
                    DailyRiskItem(
                        risk_type="overdue_task",
                        severity="red",
                        task_id=task.id,
                        message=f"任务“{task.title}”已超过截止日期且未完成验收。",
                    )
                )
            if task.confirmed and task.status not in {"completed", "draft"}:
                if task.id not in report_task_ids:
                    risks.append(
                        DailyRiskItem(
                            risk_type="missing_report",
                            severity="info",
                            task_id=task.id,
                            message=f"任务“{task.title}”尚无日报记录；仅标记资料缺失。",
                        )
                    )
            if task.status == "completed" and task.id not in accepted_task_ids:
                risks.append(
                    DailyRiskItem(
                        risk_type="completion_without_acceptance",
                        severity="red",
                        task_id=task.id,
                        message=f"任务“{task.title}”缺少已接受的交付证据。",
                    )
                )
        for report in reports:
            if report.blocker.strip():
                evidence = db.scalar(
                    select(Evidence).where(
                        Evidence.project_id == project_id,
                        Evidence.source_entity_type == "daily_report",
                        Evidence.source_entity_id == report.id,
                    )
                )
                risks.append(
                    DailyRiskItem(
                        risk_type="reported_blocker",
                        severity="yellow",
                        task_id=report.task_id,
                        report_id=report.id,
                        evidence_id=evidence.id if evidence else None,
                        message=f"{report.role} 报告阻塞：{report.blocker}",
                    )
                )
        return risks


def get_project_review_snapshot(
    *,
    project_id: int,
    session_token: str,
    session: Session | None = None,
) -> ProjectReviewSnapshot:
    """Return a deterministic, member-scoped project review snapshot for B7."""
    with session_context(session) as db:
        require_session_member(session_token, project_id, session=db)
        tasks = list(db.scalars(select(Task).where(Task.project_id == project_id)))
        reports = list(
            db.scalars(select(DailyReport).where(DailyReport.project_id == project_id))
        )
        submissions = list(
            db.scalars(select(TaskSubmission).where(TaskSubmission.project_id == project_id))
        )
        risks = build_daily_risk_review(project_id, session=db)
        task_counts: dict[str, int] = {}
        for task in tasks:
            task_counts[task.status] = task_counts.get(task.status, 0) + 1
        return ProjectReviewSnapshot(
            project_id=project_id,
            generated_at=utc_now(),
            task_counts=task_counts,
            report_count=len(reports),
            accepted_delivery_count=sum(
                item.review_status == "accepted" for item in submissions
            ),
            pending_delivery_count=sum(
                item.review_status == "pending_review" for item in submissions
            ),
            blocker_report_count=sum(bool(item.blocker.strip()) for item in reports),
            risks=risks,
        )

