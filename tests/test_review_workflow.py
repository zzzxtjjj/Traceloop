import csv
import io
import json

import pytest
from sqlalchemy import select

from core.errors import ModelOutputValidationError
from core.models import Finding, Project
from core.schemas import ReviewClassification
from services.finding_service import review_finding
from services.review_service import (
    analyze_review_batch,
    compare_review_batches,
    get_finding_evidence,
    import_reviews,
    list_batch_findings,
)
from services.task_service import (
    confirm_task,
    create_improvement_record,
    create_task_from_finding,
)


def make_project(session, name: str = "Review project") -> Project:
    project = Project(
        name=name,
        product_name="Demo product",
        access_code_hash="test",
        markets_json='["US"]',
    )
    session.add(project)
    session.flush()
    return project


def review_csv(rows: list[dict[str, str]]) -> bytes:
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
            "order_id",
            "production_batch",
            "supplier",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


def make_rows(
    prefix: str,
    count: int,
    *,
    packaging_count: int,
    batch: str,
) -> list[dict[str, str]]:
    return [
        {
            "review_id": f"{prefix}-{index}",
            "batch": batch,
            "rating": "2" if index < packaging_count else "5",
            "date": "2026-10-01",
            "sku": "SKU-1",
            "market": "US",
            "review_text": (
                "The box arrived crushed." if index < packaging_count else "Works as expected."
            ),
            "order_id": "",
            "production_batch": "",
            "supplier": "",
        }
        for index in range(count)
    ]


def test_review_import_analysis_and_human_task_gate(db_session, tmp_path) -> None:
    project = make_project(db_session)
    payload = review_csv(make_rows("R", 3, packaging_count=2, batch="October"))

    outcome = import_reviews(
        project_id=project.id,
        source=payload,
        batch_name="October",
        upload_root=tmp_path,
        session=db_session,
    )
    summaries = analyze_review_batch(
        project_id=project.id,
        batch_id=outcome.batch_id,
        session=db_session,
    )

    packaging = next(item for item in summaries if item.theme == "packaging_damage")
    assert packaging.count == 2
    assert packaging.sample_size == 3
    assert packaging.share == pytest.approx(2 / 3)

    finding = next(
        item
        for item in list_batch_findings(project.id, outcome.batch_id, db_session)
        if item.id == packaging.finding_id
    )
    assert finding.review_status == "pending_review"
    missing = json.loads(finding.missing_info_json)
    assert any("生产批次" in item for item in missing)
    assert any("供应商" in item for item in missing)
    evidence = get_finding_evidence(project.id, finding.id, db_session)
    assert len(evidence) == 2
    assert all(item.excerpt == "The box arrived crushed." for item in evidence)

    review_finding(
        project_id=project.id,
        finding_id=finding.id,
        decision="accepted",
        reviewer="项目负责人",
        note="接受统计结论，不据此认定责任方。",
        session=db_session,
    )
    task = create_task_from_finding(
        project_id=project.id,
        finding_id=finding.id,
        session=db_session,
    )
    assert task.status == "draft"
    task = confirm_task(
        project_id=project.id,
        task_id=task.id,
        confirmer_role="项目负责人",
        session=db_session,
    )
    assert task.status == "todo"
    improvement = create_improvement_record(
        project_id=project.id,
        finding_id=finding.id,
        task_id=task.id,
        baseline_batch_id=outcome.batch_id,
        session=db_session,
    )
    assert improvement.baseline_count == 2
    assert improvement.baseline_sample_size == 3


def test_duplicate_file_and_cross_batch_review_id_are_not_counted_twice(
    db_session, tmp_path
) -> None:
    project = make_project(db_session)
    payload = review_csv(make_rows("R", 2, packaging_count=1, batch="First"))
    first = import_reviews(
        project_id=project.id,
        source=payload,
        batch_name="First",
        upload_root=tmp_path,
        session=db_session,
    )
    duplicate_file = import_reviews(
        project_id=project.id,
        source=payload,
        batch_name="First again",
        upload_root=tmp_path,
        session=db_session,
    )
    assert duplicate_file.batch_id == first.batch_id
    assert duplicate_file.duplicate_file is True
    assert duplicate_file.inserted_count == 0

    second_rows = make_rows("S", 2, packaging_count=0, batch="Second")
    second_rows[0]["review_id"] = "r-0"
    second = import_reviews(
        project_id=project.id,
        source=review_csv(second_rows),
        batch_name="Second",
        upload_root=tmp_path,
        session=db_session,
    )
    assert second.inserted_count == 1
    assert second.duplicate_count == 1


def test_classifier_must_quote_the_actual_review(db_session, tmp_path) -> None:
    class BadClassifier:
        def classify(self, review):
            return ReviewClassification(
                review_id=review.external_id,
                themes=["packaging_damage"],
                evidence_excerpt="text that is not in the review",
                confidence=0.9,
                classification_method="ai",
            )

    project = make_project(db_session)
    outcome = import_reviews(
        project_id=project.id,
        source=review_csv(make_rows("R", 1, packaging_count=1, batch="October")),
        batch_name="October",
        upload_root=tmp_path,
        session=db_session,
    )
    with pytest.raises(ModelOutputValidationError, match="连续片段"):
        analyze_review_batch(
            project_id=project.id,
            batch_id=outcome.batch_id,
            classifier=BadClassifier(),
            session=db_session,
        )


def test_comparison_uses_each_batch_sample_size_and_avoids_causal_claims(
    db_session, tmp_path
) -> None:
    project = make_project(db_session)
    baseline = import_reviews(
        project_id=project.id,
        source=review_csv(make_rows("B", 10, packaging_count=5, batch="Baseline")),
        batch_name="Baseline",
        upload_root=tmp_path,
        session=db_session,
    )
    followup = import_reviews(
        project_id=project.id,
        source=review_csv(make_rows("F", 20, packaging_count=4, batch="Followup")),
        batch_name="Followup",
        upload_root=tmp_path,
        session=db_session,
    )
    analyze_review_batch(project_id=project.id, batch_id=baseline.batch_id, session=db_session)
    analyze_review_batch(project_id=project.id, batch_id=followup.batch_id, session=db_session)

    comparison = compare_review_batches(
        project_id=project.id,
        baseline_batch_id=baseline.batch_id,
        followup_batch_id=followup.batch_id,
        theme="packaging_damage",
        session=db_session,
    )
    assert comparison.baseline_count == 5
    assert comparison.followup_count == 4
    assert comparison.baseline_sample_size == 10
    assert comparison.followup_sample_size == 20
    assert comparison.baseline_share == pytest.approx(0.5)
    assert comparison.followup_share == pytest.approx(0.2)
    assert "下降趋势" in comparison.conclusion
    assert "不能单独证明" in comparison.limitation_note


def test_analysis_is_idempotent_and_preserves_reviewed_findings(db_session, tmp_path) -> None:
    project = make_project(db_session)
    outcome = import_reviews(
        project_id=project.id,
        source=review_csv(make_rows("R", 2, packaging_count=1, batch="October")),
        batch_name="October",
        upload_root=tmp_path,
        session=db_session,
    )
    first = analyze_review_batch(
        project_id=project.id, batch_id=outcome.batch_id, session=db_session
    )
    finding_id = next(item.finding_id for item in first if item.theme == "packaging_damage")
    review_finding(
        project_id=project.id,
        finding_id=finding_id,
        decision="accepted",
        reviewer="项目负责人",
        note="已核对原文。",
        session=db_session,
    )
    second = analyze_review_batch(
        project_id=project.id, batch_id=outcome.batch_id, session=db_session
    )
    second_finding_id = next(item.finding_id for item in second if item.theme == "packaging_damage")
    assert second_finding_id == finding_id
    finding = db_session.get(Finding, finding_id)
    assert finding.review_status == "accepted"


def test_import_with_missing_review_date_keeps_unknown_and_succeeds(db_session, tmp_path) -> None:
    from core.models import Evidence, Review, ReviewBatch, ReviewImportMetadata

    project = make_project(db_session)
    payload = (
        b"review_id,rating,sku,market,review_text\n"
        b"R-NODATE,2,SKU-1,US,The product arrived damaged\n"
    )
    outcome = import_reviews(
        project_id=project.id,
        source=payload,
        batch_name="Missing date",
        upload_root=tmp_path,
        session=db_session,
    )
    review = db_session.scalar(select(Review).where(Review.external_id == "R-NODATE"))
    evidence = db_session.scalar(
        select(Evidence).where(
            Evidence.source_entity_type == "review",
            Evidence.source_entity_id == review.id,
        )
    )
    batch = db_session.get(ReviewBatch, outcome.batch_id)
    metadata = db_session.scalar(
        select(ReviewImportMetadata).where(ReviewImportMetadata.batch_id == batch.id)
    )
    assert review.review_date is None
    assert '"date":null' in evidence.locator_json
    assert batch.market == "US"
    assert metadata.time_window_start is None
    assert metadata.time_window_end is None
