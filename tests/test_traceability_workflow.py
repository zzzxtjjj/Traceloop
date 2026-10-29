import pytest

from core.errors import CrossProjectReferenceError
from core.models import (
    Evidence,
    EvidenceLink,
    Finding,
    ImprovementRecord,
    Project,
    ReviewBatch,
    Task,
    TaskSubmission,
)
from services.traceability_service import get_finding_trace


def _project(db_session, name: str) -> Project:
    project = Project(
        name=name,
        product_name="Insulated Bottle",
        access_code_hash="test",
        markets_json='["US", "DE"]',
    )
    db_session.add(project)
    db_session.flush()
    return project


def _finding(db_session, project_id: int) -> Finding:
    finding = Finding(
        project_id=project_id,
        finding_type="review_theme:1:packaging_damage",
        statement="Packaging damage appears in the imported reviews.",
        epistemic_status="statistical_result",
        review_status="accepted",
        sample_size=12,
        denominator_value=12,
        denominator_type="reviews",
    )
    db_session.add(finding)
    db_session.flush()
    return finding


def test_trace_reports_missing_steps_without_inventing_relations(db_session) -> None:
    project = _project(db_session, "Missing Trace")
    finding = _finding(db_session, project.id)

    trace = get_finding_trace(
        project_id=project.id,
        finding_id=finding.id,
        session=db_session,
    )

    assert trace.evidence_status == "missing"
    assert trace.task_status == "missing"
    assert trace.delivery_status == "missing"
    assert trace.improvement_status == "missing"
    assert trace.recheck_status == "missing"
    assert trace.evidence == []
    assert trace.task is None
    assert trace.improvement is None


def test_trace_returns_complete_review_to_recheck_chain(db_session) -> None:
    project = _project(db_session, "Complete Trace")
    baseline = ReviewBatch(
        project_id=project.id,
        name="Before",
        market="US",
        sample_size=20,
    )
    followup = ReviewBatch(
        project_id=project.id,
        name="After",
        market="US",
        sample_size=24,
    )
    db_session.add_all([baseline, followup])
    db_session.flush()
    finding = _finding(db_session, project.id)
    source_evidence = Evidence(
        project_id=project.id,
        evidence_type="review_excerpt",
        source_entity_type="review",
        source_entity_id=101,
        locator_json='{"review_id": "R-101", "csv_row": 3}',
        excerpt="The box arrived crushed.",
        content_hash="source-content",
        dedupe_key="source-dedupe",
    )
    db_session.add(source_evidence)
    db_session.flush()
    db_session.add(
        EvidenceLink(
            project_id=project.id,
            evidence_id=source_evidence.id,
            target_type="finding",
            target_id=finding.id,
            relation_type="supports",
        )
    )
    task = Task(
        project_id=project.id,
        source_type="finding",
        source_id=finding.id,
        title="Improve protective packaging",
        owner_role="品控",
        status="completed",
        acceptance_criteria_json='["Provide packaging test evidence"]',
        confirmed=True,
    )
    db_session.add(task)
    db_session.flush()
    delivery_evidence = Evidence(
        project_id=project.id,
        evidence_type="task_delivery",
        source_entity_type="task",
        source_entity_id=task.id,
        locator_json=f'{{"task_id": {task.id}}}',
        excerpt="Drop test report PKG-22.",
        content_hash="delivery-content",
        dedupe_key="delivery-dedupe",
    )
    db_session.add(delivery_evidence)
    db_session.flush()
    submission = TaskSubmission(
        project_id=project.id,
        task_id=task.id,
        submitted_by_role="品控",
        content="Packaging test completed.",
        evidence_id=delivery_evidence.id,
        review_status="accepted",
        reviewed_by="项目负责人",
        review_note="Evidence checked.",
    )
    improvement = ImprovementRecord(
        project_id=project.id,
        finding_id=finding.id,
        task_id=task.id,
        baseline_batch_id=baseline.id,
        followup_batch_id=followup.id,
        theme="packaging_damage",
        baseline_count=8,
        baseline_share=0.4,
        baseline_sample_size=20,
        followup_count=4,
        followup_share=4 / 24,
        followup_sample_size=24,
        count_delta=-4,
        share_delta=(4 / 24) - 0.4,
        status="rechecked",
        limitation_note="The change does not prove causality.",
    )
    db_session.add_all([submission, improvement])
    db_session.flush()

    trace = get_finding_trace(
        project_id=project.id,
        finding_id=finding.id,
        session=db_session,
    )

    assert trace.evidence_status == "available"
    assert trace.evidence[0].locator["review_id"] == "R-101"
    assert trace.task_status == "available"
    assert trace.task is not None
    assert trace.task.id == task.id
    assert trace.delivery_status == "accepted"
    assert trace.task.submissions[0].evidence_excerpt == "Drop test report PKG-22."
    assert trace.task.submissions[0].review_note == "Evidence checked."
    assert trace.improvement_status == "rechecked"
    assert trace.recheck_status == "completed"
    assert trace.improvement is not None
    assert trace.improvement.baseline.id == baseline.id
    assert trace.improvement.followup is not None
    assert trace.improvement.followup.id == followup.id


def test_pending_delivery_and_recheck_are_explicit(db_session) -> None:
    project = _project(db_session, "Pending Trace")
    baseline = ReviewBatch(
        project_id=project.id,
        name="Before",
        market="DE",
        sample_size=10,
    )
    db_session.add(baseline)
    db_session.flush()
    finding = _finding(db_session, project.id)
    task = Task(
        project_id=project.id,
        source_type="finding",
        source_id=finding.id,
        title="Investigate packaging",
        owner_role="品控",
        status="pending_review",
        acceptance_criteria_json='["Evidence required"]',
        confirmed=True,
    )
    db_session.add(task)
    db_session.flush()
    delivery_evidence = Evidence(
        project_id=project.id,
        evidence_type="task_delivery",
        source_entity_type="task",
        source_entity_id=task.id,
        locator_json=f'{{"task_id": {task.id}}}',
        excerpt="Pending report.",
        content_hash="pending-content",
        dedupe_key="pending-dedupe",
    )
    db_session.add(delivery_evidence)
    db_session.flush()
    db_session.add_all(
        [
            TaskSubmission(
                project_id=project.id,
                task_id=task.id,
                submitted_by_role="品控",
                content="Awaiting review.",
                evidence_id=delivery_evidence.id,
                review_status="pending_review",
            ),
            ImprovementRecord(
                project_id=project.id,
                finding_id=finding.id,
                task_id=task.id,
                baseline_batch_id=baseline.id,
                theme="packaging_damage",
                baseline_count=3,
                baseline_share=0.3,
                baseline_sample_size=10,
                status="implemented",
                limitation_note="Awaiting comparable follow-up data.",
            ),
        ]
    )
    db_session.flush()

    trace = get_finding_trace(
        project_id=project.id,
        finding_id=finding.id,
        session=db_session,
    )

    assert trace.delivery_status == "pending"
    assert trace.improvement_status == "implemented"
    assert trace.recheck_status == "pending"
    assert trace.improvement is not None
    assert trace.improvement.followup is None


def test_trace_rejects_cross_project_finding(db_session) -> None:
    first = _project(db_session, "First Trace Project")
    second = _project(db_session, "Second Trace Project")
    finding = _finding(db_session, first.id)

    with pytest.raises(CrossProjectReferenceError):
        get_finding_trace(
            project_id=second.id,
            finding_id=finding.id,
            session=db_session,
        )
