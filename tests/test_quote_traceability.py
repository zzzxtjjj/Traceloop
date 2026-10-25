from pathlib import Path

import pytest
from sqlalchemy import func, select

from core.errors import CrossProjectReferenceError
from core.models import Evidence, Finding, Project
from services.imports import get_quotes, import_quotes
from services.quote_analysis import analyze_quote_artifact, confirm_supplier_decision

DEMO_FILE = Path(__file__).resolve().parents[1] / "data" / "demo" / "supplier_quotes.csv"


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


def test_quote_rows_become_evidence_and_risks_point_back_to_source(
    db_session, tmp_path
) -> None:
    project = make_project(db_session, "Quote project")
    artifact = import_quotes(
        project.id,
        DEMO_FILE,
        "October quotes",
        upload_root=tmp_path,
        session=db_session,
    )
    quotes = get_quotes(project.id, artifact.id, db_session)
    evidence_count = db_session.scalar(
        select(func.count(Evidence.id)).where(
            Evidence.project_id == project.id,
            Evidence.source_entity_type == "supplier_quote",
        )
    )
    assert len(quotes) == evidence_count == 3

    analysis = analyze_quote_artifact(
        project_id=project.id,
        artifact_id=artifact.id,
        session=db_session,
    )
    beta = next(item for item in analysis.assessments if item.supplier == "Shenzhen Beta")
    assert beta.risk_level == "yellow"
    assert any("样品未确认" in item for item in beta.risk_reasons)
    assert any("落地费用" in item for item in beta.clarification_questions)
    finding = db_session.get(Finding, beta.finding_id)
    assert finding.review_status == "pending_review"
    assert "样品未确认" in finding.statement
    assert any("不能据此比较总采购成本" in note for note in analysis.comparability_notes)


def test_quote_analysis_is_idempotent(db_session, tmp_path) -> None:
    project = make_project(db_session, "Quote project")
    artifact = import_quotes(
        project.id,
        DEMO_FILE,
        "October quotes",
        upload_root=tmp_path,
        session=db_session,
    )
    first = analyze_quote_artifact(
        project_id=project.id,
        artifact_id=artifact.id,
        session=db_session,
    )
    second = analyze_quote_artifact(
        project_id=project.id,
        artifact_id=artifact.id,
        session=db_session,
    )
    assert [item.finding_id for item in first.assessments] == [
        item.finding_id for item in second.assessments
    ]


def test_supplier_decision_requires_a_real_candidate_and_reason(db_session, tmp_path) -> None:
    project = make_project(db_session, "Quote project")
    artifact = import_quotes(
        project.id,
        DEMO_FILE,
        "October quotes",
        upload_root=tmp_path,
        session=db_session,
    )
    with pytest.raises(ValueError, match="不在当前报价批次"):
        confirm_supplier_decision(
            project_id=project.id,
            artifact_id=artifact.id,
            supplier="Invented supplier",
            reason="lowest price",
            actor_role="项目负责人",
            session=db_session,
        )
    with pytest.raises(ValueError, match="理由"):
        confirm_supplier_decision(
            project_id=project.id,
            artifact_id=artifact.id,
            supplier="Ningbo Alpha",
            reason="",
            actor_role="项目负责人",
            session=db_session,
        )
    decision = confirm_supplier_decision(
        project_id=project.id,
        artifact_id=artifact.id,
        supplier="Ningbo Alpha",
        reason="样品和质检记录相对完整，仍需确认落地成本。",
        actor_role="项目负责人",
        session=db_session,
    )
    assert decision.human_choice == "Ningbo Alpha"
    assert decision.ai_choice is None


def test_quote_artifact_cannot_be_read_from_another_project(db_session, tmp_path) -> None:
    owner = make_project(db_session, "Owner")
    outsider = make_project(db_session, "Outsider")
    artifact = import_quotes(
        owner.id,
        DEMO_FILE,
        "October quotes",
        upload_root=tmp_path,
        session=db_session,
    )
    with pytest.raises(ValueError, match="不属于当前项目"):
        get_quotes(outsider.id, artifact.id, db_session)
    with pytest.raises(CrossProjectReferenceError):
        analyze_quote_artifact(
            project_id=outsider.id,
            artifact_id=artifact.id,
            session=db_session,
        )
