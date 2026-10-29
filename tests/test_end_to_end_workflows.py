import csv
import io
from pathlib import Path

import pytest
from sqlalchemy import select

from core.models import AuditEvent, Project
from services.finding_service import review_finding
from services.imports import import_quotes
from services.quote_analysis import analyze_quote_artifact, confirm_supplier_decision
from services.review_service import (
    analyze_review_batch,
    apply_comparison_to_improvement,
    compare_review_batches,
    import_reviews,
    list_batch_findings,
)
from services.task_service import (
    confirm_task,
    create_improvement_record,
    create_task_from_finding,
    review_task_submission,
    submit_task_delivery,
)

DEMO_QUOTES = Path(__file__).resolve().parents[1] / "data" / "demo" / "supplier_quotes.csv"


def make_project(session, name: str) -> Project:
    project = Project(
        name=name,
        product_name="Vacuum bottle",
        access_code_hash="test",
        markets_json='["US", "DE"]',
    )
    session.add(project)
    session.flush()
    return project


def review_payload(prefix: str, count: int, damaged: int, batch: str) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "review_id",
            "batch",
            "rating",
            "date",
            "sku",
            "market",
            "review_text",
        ],
    )
    writer.writeheader()
    for index in range(count):
        writer.writerow(
            {
                "review_id": f"{prefix}-{index}",
                "batch": batch,
                "rating": 2 if index < damaged else 5,
                "date": "2026-10-01",
                "sku": "BOTTLE-750",
                "market": "US",
                "review_text": (
                    "The box arrived crushed." if index < damaged else "Works as expected."
                ),
            }
        )
    return output.getvalue().encode()


def test_quote_to_reviewed_delivery_workflow(db_session, tmp_path) -> None:
    project = make_project(db_session, "Quote workflow")
    artifact = import_quotes(
        project.id,
        DEMO_QUOTES,
        "October quotes",
        upload_root=tmp_path,
        session=db_session,
    )
    analysis = analyze_quote_artifact(
        project_id=project.id,
        artifact_id=artifact.id,
        session=db_session,
    )
    assessment = next(item for item in analysis.assessments if item.risk_level == "yellow")
    review_finding(
        project_id=project.id,
        finding_id=assessment.finding_id,
        decision="accepted",
        reviewer="项目负责人",
        note="确认风险仅来自报价备注，未判定供应商责任。",
        session=db_session,
    )
    task = create_task_from_finding(
        project_id=project.id,
        finding_id=assessment.finding_id,
        session=db_session,
    )
    confirm_task(
        project_id=project.id,
        task_id=task.id,
        confirmer_role="项目负责人",
        session=db_session,
    )
    decision = confirm_supplier_decision(
        project_id=project.id,
        artifact_id=artifact.id,
        supplier="Ningbo Alpha",
        reason="样品记录较完整；落地成本仍列为合同前置确认项。",
        actor_role="项目负责人",
        session=db_session,
    )
    submission = submit_task_delivery(
        project_id=project.id,
        task_id=task.id,
        submitted_by_role="项目负责人",
        content="已向候选供应商发送澄清清单。",
        evidence_excerpt="澄清记录 RFQ-CLARIFY-001，包含 Incoterm、运税和样品问题。",
        session=db_session,
    )
    review_task_submission(
        project_id=project.id,
        submission_id=submission.id,
        decision="accepted",
        reviewer="独立验收人",
        note="已核对澄清记录。",
        session=db_session,
    )
    assert decision.human_choice == "Ningbo Alpha"
    assert task.status == "completed"
    actions = set(db_session.scalars(select(AuditEvent.action)))
    assert "supplier_decision_confirmed" in actions
    assert "task_delivery_accepted" in actions


def test_review_improvement_and_followup_recheck_workflow(db_session, tmp_path) -> None:
    project = make_project(db_session, "Review workflow")
    baseline = import_reviews(
        project_id=project.id,
        source=review_payload("B", 10, 5, "Before"),
        batch_name="Before",
        upload_root=tmp_path,
        session=db_session,
    )
    analyze_review_batch(
        project_id=project.id,
        batch_id=baseline.batch_id,
        session=db_session,
    )
    finding = next(
        item
        for item in list_batch_findings(project.id, baseline.batch_id, db_session)
        if item.finding_type.endswith(":packaging_damage")
    )
    review_finding(
        project_id=project.id,
        finding_id=finding.id,
        decision="accepted",
        reviewer="项目负责人",
        note="已核对五条评价原文；原因仍待调查。",
        session=db_session,
    )
    task = create_task_from_finding(
        project_id=project.id,
        finding_id=finding.id,
        session=db_session,
    )
    confirm_task(
        project_id=project.id,
        task_id=task.id,
        confirmer_role="项目负责人",
        session=db_session,
    )
    improvement = create_improvement_record(
        project_id=project.id,
        finding_id=finding.id,
        task_id=task.id,
        baseline_batch_id=baseline.batch_id,
        session=db_session,
    )
    submission = submit_task_delivery(
        project_id=project.id,
        task_id=task.id,
        submitted_by_role=task.owner_role,
        content="完成包装跌落测试并更新包装规范。",
        evidence_excerpt="测试记录 PKG-DROP-008；规范版本 PACK-SPEC-1.1。",
        session=db_session,
    )
    review_task_submission(
        project_id=project.id,
        submission_id=submission.id,
        decision="accepted",
        reviewer="项目负责人",
        note="验收材料齐全。",
        session=db_session,
    )
    assert improvement.status == "implemented"

    followup = import_reviews(
        project_id=project.id,
        source=review_payload("F", 10, 1, "After"),
        batch_name="After",
        upload_root=tmp_path,
        session=db_session,
    )
    analyze_review_batch(
        project_id=project.id,
        batch_id=followup.batch_id,
        session=db_session,
    )
    comparison = compare_review_batches(
        project_id=project.id,
        baseline_batch_id=baseline.batch_id,
        followup_batch_id=followup.batch_id,
        theme="packaging_damage",
        session=db_session,
    )
    apply_comparison_to_improvement(
        improvement_id=improvement.id,
        comparison=comparison,
        project_id=project.id,
        session=db_session,
    )
    assert comparison.share_delta == pytest.approx(-0.4)
    assert "下降趋势" in comparison.conclusion
    assert "不能单独证明" in comparison.limitation_note
    assert improvement.status == "rechecked"
    assert improvement.followup_batch_id == followup.batch_id
