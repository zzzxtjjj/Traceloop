from datetime import timedelta

import pytest
from sqlalchemy import select

from core.errors import EvidenceRequiredError, InvalidStateTransitionError
from core.models import EvidenceLink, Project, Task, utc_now
from services.task_service import (
    build_daily_risk_review,
    review_task_submission,
    submit_daily_report,
    submit_task_delivery,
    update_task_status,
)


def make_project_and_task(session, *, status: str = "todo", due_offset: int = 2):
    project = Project(
        name=f"Task project {status} {due_offset}",
        product_name="Demo product",
        access_code_hash="test",
        markets_json='["US"]',
    )
    session.add(project)
    session.flush()
    task = Task(
        project_id=project.id,
        source_type="manual",
        title="核查包装测试记录",
        owner_role="品控",
        status=status,
        acceptance_criteria_json='["提交测试记录"]',
        due_at=utc_now() + timedelta(days=due_offset),
        confirmed=True,
    )
    session.add(task)
    session.flush()
    return project, task


def test_task_cannot_enter_acceptance_without_delivery_evidence(db_session) -> None:
    project, task = make_project_and_task(db_session)
    with pytest.raises(EvidenceRequiredError, match="验收材料"):
        submit_task_delivery(
            project_id=project.id,
            task_id=task.id,
            submitted_by_role="品控",
            content="已经完成。",
            evidence_excerpt="",
            session=db_session,
        )
    assert task.status == "todo"


def test_delivery_requires_human_acceptance_before_task_is_completed(db_session) -> None:
    project, task = make_project_and_task(db_session)
    submission = submit_task_delivery(
        project_id=project.id,
        task_id=task.id,
        submitted_by_role="品控",
        content="完成跌落测试。",
        evidence_excerpt="测试编号 PKG-2026-10，六面跌落均已记录。",
        session=db_session,
    )
    assert task.status == "pending_review"
    assert submission.review_status == "pending_review"
    link = db_session.scalar(
        select(EvidenceLink).where(
            EvidenceLink.target_type == "task",
            EvidenceLink.target_id == task.id,
            EvidenceLink.relation_type == "delivery_for",
        )
    )
    assert link is not None

    review_task_submission(
        project_id=project.id,
        submission_id=submission.id,
        decision="accepted",
        reviewer="项目负责人",
        note="已核对测试编号。",
        session=db_session,
    )
    assert task.status == "completed"
    assert submission.review_status == "accepted"


def test_rejected_delivery_returns_task_to_todo(db_session) -> None:
    project, task = make_project_and_task(db_session)
    submission = submit_task_delivery(
        project_id=project.id,
        task_id=task.id,
        submitted_by_role="品控",
        content="完成检查。",
        evidence_excerpt="只有口头说明，没有测试编号。",
        session=db_session,
    )
    with pytest.raises(ValueError, match="理由"):
        review_task_submission(
            project_id=project.id,
            submission_id=submission.id,
            decision="rejected",
            reviewer="项目负责人",
            note="",
            session=db_session,
        )
    review_task_submission(
        project_id=project.id,
        submission_id=submission.id,
        decision="rejected",
        reviewer="项目负责人",
        note="缺少可核查的测试编号。",
        session=db_session,
    )
    assert task.status == "todo"


def test_daily_report_does_not_complete_task_and_blocker_is_flagged(db_session) -> None:
    project, task = make_project_and_task(db_session)
    report = submit_daily_report(
        project_id=project.id,
        role="品控",
        task_id=task.id,
        completed="已联系测试实验室。",
        blocker="实验室报告预计明天返回。",
        next_plan="收到报告后提交验收。",
        session=db_session,
    )
    assert task.status == "todo"
    risks = build_daily_risk_review(project.id, db_session)
    blocker = next(item for item in risks if item.risk_type == "reported_blocker")
    assert blocker.report_id == report.id
    assert blocker.evidence_id is not None


def test_status_change_is_role_scoped_and_completed_state_is_not_direct(db_session) -> None:
    project, task = make_project_and_task(db_session)
    with pytest.raises(InvalidStateTransitionError, match="岗位"):
        update_task_status(
            project_id=project.id,
            task_id=task.id,
            status="doing",
            actor_role="采购",
            session=db_session,
        )
    with pytest.raises(InvalidStateTransitionError, match="只能切换"):
        update_task_status(
            project_id=project.id,
            task_id=task.id,
            status="completed",
            actor_role="品控",
            session=db_session,
        )


def test_overdue_and_missing_acceptance_are_deterministic_risks(db_session) -> None:
    project, overdue = make_project_and_task(db_session, due_offset=-1)
    completed = Task(
        project_id=project.id,
        source_type="manual",
        title="手工错误完成状态",
        owner_role="采购",
        status="completed",
        acceptance_criteria_json='["提交记录"]',
        confirmed=True,
    )
    db_session.add(completed)
    db_session.flush()
    risks = build_daily_risk_review(project.id, db_session)
    assert any(item.risk_type == "overdue_task" and item.task_id == overdue.id for item in risks)
    assert any(
        item.risk_type == "completion_without_acceptance" and item.task_id == completed.id
        for item in risks
    )
