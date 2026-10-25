import pytest

from core.errors import CrossProjectReferenceError, EvidenceRequiredError, ProjectAccessDeniedError
from core.models import Project
from services.evidence_service import (
    create_evidence,
    create_finding,
    link_evidence,
    submit_finding_for_review,
)
from services.project_access import require_project_access


def make_project(session, name: str) -> Project:
    project = Project(
        name=name,
        product_name="Demo product",
        access_code_hash="test",
        markets_json='["US"]',
    )
    session.add(project)
    session.flush()
    return project


def test_evidence_is_deduplicated(db_session) -> None:
    project = make_project(db_session, "P1")
    kwargs = {
        "project_id": project.id,
        "evidence_type": "review_text",
        "source_entity_type": "review",
        "source_entity_id": 10,
        "locator": {"review_id": "R-10"},
        "excerpt": "The box arrived crushed.",
        "session": db_session,
    }
    first = create_evidence(**kwargs)
    second = create_evidence(**kwargs)
    assert first.id == second.id


def test_cross_project_evidence_link_is_rejected(db_session) -> None:
    project_a = make_project(db_session, "P1")
    project_b = make_project(db_session, "P2")
    evidence = create_evidence(
        project_id=project_a.id,
        evidence_type="review_text",
        source_entity_type="review",
        source_entity_id=1,
        locator={"review_id": "R-1"},
        excerpt="Damaged box",
        session=db_session,
    )
    finding = create_finding(
        project_id=project_b.id,
        finding_type="review_theme",
        statement="Packaging issue",
        epistemic_status="model_judgment",
        session=db_session,
    )
    with pytest.raises(CrossProjectReferenceError):
        link_evidence(
            project_id=project_b.id,
            evidence_id=evidence.id,
            target_type="finding",
            target_id=finding.id,
            session=db_session,
        )


def test_confirmed_fact_requires_evidence_before_review(db_session) -> None:
    project = make_project(db_session, "P1")
    finding = create_finding(
        project_id=project.id,
        finding_type="review_statistic",
        statement="Two reviews mention damage.",
        epistemic_status="confirmed_fact",
        session=db_session,
    )
    with pytest.raises(EvidenceRequiredError):
        submit_finding_for_review(finding.id, project_id=project.id, session=db_session)


def test_project_access_boundary() -> None:
    require_project_access(1, {1, 2})
    with pytest.raises(ProjectAccessDeniedError):
        require_project_access(3, {1, 2})

