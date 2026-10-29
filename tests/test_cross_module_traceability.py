import pytest

from core.errors import CrossProjectReferenceError, InvalidStateTransitionError
from core.models import (
    Artifact,
    Evidence,
    Finding,
    Project,
    ReviewBatch,
    Task,
)
from services.evidence_service import create_evidence, link_evidence
from services.task_service import (
    create_improvement_record,
    review_task_submission,
    submit_task_delivery,
)


def make_project(session, name: str) -> Project:
    project = Project(
        name=name,
        product_name="Test product",
        access_code_hash="test",
        markets_json='["US"]',
    )
    session.add(project)
    session.flush()
    return project


def make_evidence(session, project_id: int, suffix: str) -> Evidence:
    return create_evidence(
        project_id=project_id,
        evidence_type="review_excerpt",
        source_entity_type="review",
        source_entity_id=1,
        locator={"review_id": suffix},
        excerpt=f"Source excerpt {suffix}",
        session=session,
    )


@pytest.mark.parametrize("target_type", ["finding", "task", "review_batch", "artifact"])
def test_evidence_cannot_link_to_cross_project_target(db_session, target_type: str) -> None:
    project_a = make_project(db_session, f"Project A {target_type}")
    project_b = make_project(db_session, f"Project B {target_type}")
    evidence = make_evidence(db_session, project_a.id, target_type)

    targets = {
        "finding": Finding(
            project_id=project_b.id,
            finding_type="review:packaging_damage",
            statement="Packaging damage",
            epistemic_status="statistical_result",
        ),
        "task": Task(
            project_id=project_b.id,
            title="Inspect packaging",
            owner_role="品控",
            status="todo",
            confirmed=True,
        ),
        "review_batch": ReviewBatch(
            project_id=project_b.id,
            name="Batch B",
            market="US",
            sample_size=1,
        ),
        "artifact": Artifact(
            project_id=project_b.id,
            artifact_type="reviews_csv",
            batch_name="Batch B",
            original_filename="reviews.csv",
            sha256="b" * 64,
        ),
    }
    target = targets[target_type]
    db_session.add(target)
    db_session.flush()

    with pytest.raises(CrossProjectReferenceError, match="不属于当前项目"):
        link_evidence(
            project_id=project_a.id,
            evidence_id=evidence.id,
            target_type=target_type,
            target_id=target.id,
            session=db_session,
        )


def test_missing_or_unsupported_evidence_target_is_rejected(db_session) -> None:
    project = make_project(db_session, "Missing target")
    evidence = make_evidence(db_session, project.id, "missing")

    with pytest.raises(CrossProjectReferenceError, match="不存在、不受支持"):
        link_evidence(
            project_id=project.id,
            evidence_id=evidence.id,
            target_type="invented_target",
            target_id=999,
            session=db_session,
        )


def test_improvement_record_rejects_cross_project_baseline_batch(db_session) -> None:
    project_a = make_project(db_session, "Improvement A")
    project_b = make_project(db_session, "Improvement B")
    finding = Finding(
        project_id=project_a.id,
        finding_type="review:packaging_damage",
        statement="Packaging damage",
        epistemic_status="statistical_result",
        review_status="accepted",
        sample_size=10,
    )
    db_session.add(finding)
    db_session.flush()
    task = Task(
        project_id=project_a.id,
        source_type="finding",
        source_id=finding.id,
        title="Improve packaging",
        owner_role="品控",
        status="todo",
        confirmed=True,
    )
    baseline = ReviewBatch(
        project_id=project_b.id,
        name="Other project batch",
        market="US",
        sample_size=10,
    )
    db_session.add_all([task, baseline])
    db_session.flush()

    with pytest.raises(CrossProjectReferenceError, match="基线评价批次"):
        create_improvement_record(
            project_id=project_a.id,
            finding_id=finding.id,
            task_id=task.id,
            baseline_batch_id=baseline.id,
            session=db_session,
        )


def test_task_submitter_cannot_review_own_delivery(db_session) -> None:
    project = make_project(db_session, "Self review")
    task = Task(
        project_id=project.id,
        title="Inspect packaging",
        owner_role="品控",
        status="todo",
        confirmed=True,
        acceptance_criteria_json='["Provide test record"]',
    )
    db_session.add(task)
    db_session.flush()
    submission = submit_task_delivery(
        project_id=project.id,
        task_id=task.id,
        submitted_by_role="品控",
        content="Inspection completed.",
        evidence_excerpt="Test record PKG-001.",
        session=db_session,
    )

    with pytest.raises(InvalidStateTransitionError, match="不能验收自己的交付"):
        review_task_submission(
            project_id=project.id,
            submission_id=submission.id,
            decision="accepted",
            reviewer="品控",
            note="Self review is not allowed.",
            session=db_session,
        )
