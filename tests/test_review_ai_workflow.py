
import pytest
from sqlalchemy import select

from core.errors import (
    CrossProjectReferenceError,
    ModelInputLimitError,
    ModelOutputValidationError,
)
from core.models import (
    AiRun,
    Evidence,
    Finding,
    Project,
    Review,
    ReviewBatch,
    ReviewThemeAssignment,
)
from services.evidence_service import create_evidence
from services.review_ai_service import (
    AI_TAXONOMY_VERSION,
    PROMPT_VERSION,
    analyze_review_batch_with_model,
    get_latest_review_ai_run,
)
from services.review_service import analyze_review_batch, list_batch_findings


class FakeProvider:
    model_name = "offline-review-model"

    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def generate(self, *, prompt, schema, repair_from=None):
        self.calls.append(
            {"prompt": prompt, "schema": schema, "repair_from": repair_from}
        )
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def make_batch(session, name: str = "AI review project"):
    project = Project(
        name=name,
        product_name="Bottle",
        access_code_hash="test",
        markets_json='["US"]',
    )
    session.add(project)
    session.flush()
    batch = ReviewBatch(
        project_id=project.id,
        name="October reviews",
        market="US",
        sample_size=2,
        prompt_version=PROMPT_VERSION,
    )
    session.add(batch)
    session.flush()
    reviews = [
        Review(
            batch_id=batch.id,
            external_id="R-1",
            rating=2,
            sku="SKU-1",
            review_text="The box arrived crushed, but the bottle works.",
        ),
        Review(
            batch_id=batch.id,
            external_id="R-2",
            rating=5,
            sku="SKU-1",
            review_text="The bottle works as expected.",
        ),
    ]
    session.add_all(reviews)
    session.flush()
    for review in reviews:
        create_evidence(
            project_id=project.id,
            evidence_type="review_text",
            source_entity_type="review",
            source_entity_id=review.id,
            locator={"batch_id": batch.id, "review_id": review.external_id},
            excerpt=review.review_text,
            session=session,
        )
    return project, batch, reviews


def valid_output():
    return {
        "classifications": [
            {
                "review_id": "R-1",
                "themes": ["packaging_damage"],
                "evidence_span": "box arrived crushed",
                "confidence": 0.9,
                "missing_info": ["production batch"],
                "alternative_explanations": ["last-mile compression"],
            },
            {
                "review_id": "R-2",
                "themes": ["other"],
                "evidence_span": "works as expected",
                "confidence": 0.6,
                "missing_info": [],
                "alternative_explanations": [],
            },
        ]
    }


def test_model_analysis_validates_then_writes_findings_and_evidence(db_session) -> None:
    project, batch, _ = make_batch(db_session)
    provider = FakeProvider(valid_output())

    result = analyze_review_batch_with_model(
        project.id, batch.id, provider=provider, session=db_session
    )

    assert result.status == "success"
    assert result.prompt_version == PROMPT_VERSION
    assert len(result.finding_ids) == 2
    run = db_session.get(AiRun, result.ai_run_id)
    assert run.status == "success"
    findings = list(
        db_session.scalars(
            select(Finding).where(Finding.id.in_(result.finding_ids)).order_by(Finding.id)
        )
    )
    packaging = next(item for item in findings if item.finding_type.endswith("packaging_damage"))
    assert packaging.model_run_id == run.id
    assert packaging.sample_size == 2
    assert packaging.denominator_value == 2
    assert "1 条" in packaging.statement
    assert "50.0%" in packaging.statement
    assert packaging.review_status == "pending_review"
    assignments = list(
        db_session.scalars(
            select(ReviewThemeAssignment).where(
                ReviewThemeAssignment.batch_id == batch.id,
                ReviewThemeAssignment.taxonomy_version == AI_TAXONOMY_VERSION,
            )
        )
    )
    assert len(assignments) == 2
    ai_evidence = list(
        db_session.scalars(
            select(Evidence).where(Evidence.evidence_type == "review_ai_excerpt")
        )
    )
    assert {item.excerpt for item in ai_evidence} == {
        "box arrived crushed",
        "works as expected",
    }
    assert len(provider.calls) == 1
    prompt = provider.calls[0]["prompt"]
    assert project.name not in prompt
    assert "project_id" not in prompt
    assert "rating" not in prompt
    assert "review_id" in prompt and "review_text" in prompt


@pytest.mark.parametrize(
    "replacement",
    [
        {"review_id": "UNKNOWN"},
        {"evidence_span": "invented quotation"},
    ],
)
def test_invalid_model_evidence_leaves_no_partial_business_records(
    db_session, replacement: dict
) -> None:
    project, batch, _ = make_batch(db_session, name=f"Invalid {replacement}")
    output = valid_output()
    output["classifications"][0].update(replacement)

    with pytest.raises(ModelOutputValidationError):
        analyze_review_batch_with_model(
            project.id,
            batch.id,
            provider=FakeProvider(output),
            session=db_session,
        )

    run = get_latest_review_ai_run(project.id, batch.id, session=db_session)
    assert run is not None
    assert run.status == "failed"
    assert run.error_code == "MODEL_EVIDENCE_INVALID"
    assert not list(
        db_session.scalars(
            select(Finding).where(
                Finding.finding_type.like(f"review_ai_theme:{batch.id}:%")
            )
        )
    )
    assert not list(
        db_session.scalars(
            select(ReviewThemeAssignment).where(
                ReviewThemeAssignment.taxonomy_version == AI_TAXONOMY_VERSION
            )
        )
    )
    assert not list(
        db_session.scalars(
            select(Evidence).where(Evidence.evidence_type == "review_ai_excerpt")
        )
    )


def test_repeated_run_preserves_human_reviewed_finding(db_session) -> None:
    project, batch, _ = make_batch(db_session, "Repeat AI analysis")
    first = analyze_review_batch_with_model(
        project.id, batch.id, provider=FakeProvider(valid_output()), session=db_session
    )
    finding = db_session.get(Finding, first.finding_ids[0])
    finding.review_status = "accepted"
    finding.reviewed_by = "independent reviewer"
    original_statement = finding.statement
    provider = FakeProvider(AssertionError("model must not be called twice"))

    second = analyze_review_batch_with_model(
        project.id, batch.id, provider=provider, session=db_session
    )

    assert second.finding_ids == first.finding_ids
    assert second.ai_run_id == first.ai_run_id
    assert provider.calls == []
    assert finding.review_status == "accepted"
    assert finding.statement == original_statement


def test_rule_and_model_findings_can_be_queried_together(db_session) -> None:
    project, batch, _ = make_batch(db_session, "Rule and AI")
    analyze_review_batch(project_id=project.id, batch_id=batch.id, session=db_session)
    analyze_review_batch_with_model(
        project.id, batch.id, provider=FakeProvider(valid_output()), session=db_session
    )

    findings = list_batch_findings(project.id, batch.id, session=db_session)
    finding_types = {item.finding_type.split(":", maxsplit=1)[0] for item in findings}
    assert finding_types == {"review_theme", "review_ai_theme"}


def test_latest_ai_run_checks_project_ownership(db_session) -> None:
    project, batch, _ = make_batch(db_session, "Owned AI run")
    other = Project(
        name="Other project",
        product_name="Other",
        access_code_hash="test",
        markets_json='["US"]',
    )
    db_session.add(other)
    db_session.flush()

    with pytest.raises(CrossProjectReferenceError):
        get_latest_review_ai_run(other.id, batch.id, session=db_session)


@pytest.mark.parametrize(
    ("max_input_chars", "max_reviews_per_run"),
    [(1, 100), (100_000, 1)],
)
def test_model_budget_is_checked_before_transport_or_ai_run(
    db_session, max_input_chars: int, max_reviews_per_run: int
) -> None:
    project, batch, _ = make_batch(db_session, "Budget protected")
    provider = FakeProvider(valid_output())
    provider.max_input_chars = max_input_chars
    provider.max_reviews_per_run = max_reviews_per_run

    with pytest.raises(ModelInputLimitError):
        analyze_review_batch_with_model(
            project.id, batch.id, provider=provider, session=db_session
        )

    assert provider.calls == []
    assert get_latest_review_ai_run(project.id, batch.id, session=db_session) is None
