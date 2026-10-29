import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import CrossProjectReferenceError, ModelOutputValidationError
from core.models import (
    AiRun,
    AuditEvent,
    Evidence,
    Finding,
    Review,
    ReviewBatch,
    ReviewThemeAssignment,
)
from core.schemas import ReviewAIAnalysisResult, ReviewModelBatchOutput
from services.ai_service import StructuredModelProvider, run_structured_model
from services.evidence_service import create_evidence, create_finding, submit_finding_for_review
from services.model_provider import OpenAICompatibleProvider
from services.model_readiness import validate_model_input_budget
from services.review_service import THEME_ACTIONS, THEME_ALTERNATIVES, THEME_LABELS

PROMPT_VERSION = "review_classify_v1"
AI_TAXONOMY_VERSION = "review_themes_ai_v1"
RUN_TYPE_PREFIX = "review_batch_model"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / f"{PROMPT_VERSION}.txt"


def _run_type(batch_id: int) -> str:
    return f"{RUN_TYPE_PREFIX}:{batch_id}"


def get_latest_review_ai_run(
    project_id: int,
    batch_id: int,
    session: Session | None = None,
) -> AiRun | None:
    with session_context(session) as db:
        batch = db.get(ReviewBatch, batch_id)
        if not batch or batch.project_id != project_id:
            raise CrossProjectReferenceError("评价批次不存在或不属于当前项目。")
        return db.scalar(
            select(AiRun)
            .where(
                AiRun.project_id == project_id,
                AiRun.run_type == _run_type(batch_id),
            )
            .order_by(AiRun.id.desc())
        )


def _existing_result(
    db: Session, project_id: int, batch_id: int
) -> ReviewAIAnalysisResult | None:
    findings = list(
        db.scalars(
            select(Finding)
            .where(
                Finding.project_id == project_id,
                Finding.finding_type.like(f"review_ai_theme:{batch_id}:%"),
            )
            .order_by(Finding.id)
        )
    )
    if not findings:
        return None
    run_id = next((item.model_run_id for item in findings if item.model_run_id), None)
    if run_id is None:
        latest = get_latest_review_ai_run(project_id, batch_id, session=db)
        run_id = latest.id if latest else None
    if run_id is None:
        raise ModelOutputValidationError("已有 AI Finding 缺少模型运行记录，不能安全覆盖。")
    return ReviewAIAnalysisResult(
        ai_run_id=run_id,
        finding_ids=[item.id for item in findings],
        prompt_version=PROMPT_VERSION,
        status="success",
    )


def _minimal_prompt(reviews: list[Review]) -> str:
    instructions = PROMPT_PATH.read_text(encoding="utf-8").strip()
    review_data = [
        {"review_id": review.external_id, "review_text": review.review_text}
        for review in reviews
    ]
    return (
        f"{instructions}\n\n"
        "Classify every review exactly once. Allowed themes: "
        f"{', '.join(sorted(THEME_LABELS))}.\n"
        f"Reviews:\n{json.dumps(review_data, ensure_ascii=False, separators=(',', ':'))}"
    )


def _validate_output(
    output: ReviewModelBatchOutput, reviews: list[Review]
) -> dict[str, Review]:
    review_by_external = {review.external_id: review for review in reviews}
    result_ids = [item.review_id for item in output.classifications]
    if len(result_ids) != len(set(result_ids)):
        raise ModelOutputValidationError("模型对同一评价返回了重复分类。")
    if set(result_ids) != set(review_by_external):
        raise ModelOutputValidationError("模型分类的评价 ID 与当前批次不一致。")
    for item in output.classifications:
        review = review_by_external[item.review_id]
        if item.evidence_span not in review.review_text:
            raise ModelOutputValidationError("模型证据不是评价原文的连续片段。")
        unknown_themes = set(item.themes) - set(THEME_LABELS)
        if unknown_themes:
            raise ModelOutputValidationError(
                f"模型分类包含未知主题：{', '.join(sorted(unknown_themes))}"
            )
    return review_by_external


def analyze_review_batch_with_model(
    project_id: int,
    batch_id: int,
    provider: StructuredModelProvider | None = None,
    session: Session | None = None,
) -> ReviewAIAnalysisResult:
    with session_context(session) as db:
        batch = db.get(ReviewBatch, batch_id)
        if not batch or batch.project_id != project_id:
            raise CrossProjectReferenceError("评价批次不存在或不属于当前项目。")

        existing = _existing_result(db, project_id, batch_id)
        if existing:
            return existing

        reviews = list(
            db.scalars(select(Review).where(Review.batch_id == batch_id).order_by(Review.id))
        )
        if not reviews:
            raise ValueError("评价批次为空，不能运行模型分析。")
        source_evidence = list(
            db.scalars(
                select(Evidence).where(
                    Evidence.project_id == project_id,
                    Evidence.source_entity_type == "review",
                    Evidence.source_entity_id.in_([item.id for item in reviews]),
                )
            )
        )
        evidence_ids = sorted({item.id for item in source_evidence})
        active_provider = provider or OpenAICompatibleProvider.from_settings()
        prompt = _minimal_prompt(reviews)
        validate_model_input_budget(
            prompt=prompt,
            review_count=len(reviews),
            max_input_chars=getattr(active_provider, "max_input_chars", None),
            max_reviews_per_run=getattr(active_provider, "max_reviews_per_run", None),
        )
        output = run_structured_model(
            project_id=project_id,
            run_type=_run_type(batch_id),
            prompt_version=PROMPT_VERSION,
            prompt=prompt,
            evidence_ids=evidence_ids,
            output_model=ReviewModelBatchOutput,
            provider=active_provider,
            session=db,
        )
        ai_run = get_latest_review_ai_run(project_id, batch_id, session=db)
        if ai_run is None:
            raise ModelOutputValidationError("模型运行记录不存在。")

        try:
            review_by_external = _validate_output(output, reviews)
        except ModelOutputValidationError:
            ai_run.status = "failed"
            ai_run.error_code = "MODEL_EVIDENCE_INVALID"
            db.flush()
            raise

        classifications_by_theme: dict[str, list] = defaultdict(list)
        evidence_by_review_id: dict[str, Evidence] = {}
        finding_ids: list[int] = []
        try:
            with db.begin_nested():
                for item in output.classifications:
                    review = review_by_external[item.review_id]
                    ai_evidence = create_evidence(
                        project_id=project_id,
                        evidence_type="review_ai_excerpt",
                        source_entity_type="review",
                        source_entity_id=review.id,
                        locator={
                            "batch_id": batch_id,
                            "review_id": item.review_id,
                            "classification_method": "ai",
                            "prompt_version": PROMPT_VERSION,
                        },
                        excerpt=item.evidence_span,
                        session=db,
                    )
                    evidence_by_review_id[item.review_id] = ai_evidence
                    for theme in sorted(set(item.themes)):
                        db.add(
                            ReviewThemeAssignment(
                                project_id=project_id,
                                batch_id=batch_id,
                                review_id=review.id,
                                theme=theme,
                                classification_method="ai",
                                confidence=item.confidence,
                                evidence_excerpt=item.evidence_span,
                                taxonomy_version=AI_TAXONOMY_VERSION,
                            )
                        )
                        classifications_by_theme[theme].append(item)

                sample_size = len(reviews)
                for theme, items in sorted(classifications_by_theme.items()):
                    review_ids = {item.review_id for item in items}
                    count = len(review_ids)
                    share = count / sample_size
                    confidence = sum(item.confidence for item in items) / len(items)
                    missing = sorted(
                        {
                            value
                            for item in items
                            for value in item.missing_info
                            if value.strip()
                        }
                    )
                    alternatives = sorted(
                        set(THEME_ALTERNATIVES[theme])
                        | {
                            value
                            for item in items
                            for value in item.alternative_explanations
                            if value.strip()
                        }
                    )
                    finding = create_finding(
                        project_id=project_id,
                        finding_type=f"review_ai_theme:{batch_id}:{theme}",
                        statement=(
                            f"批次“{batch.name}”的 {sample_size} 条评价中，{count} 条经模型"
                            f"分类包含“{THEME_LABELS[theme]}”主题，占 {share:.1%}。"
                        ),
                        epistemic_status="model_judgment",
                        confidence=confidence,
                        sample_size=sample_size,
                        denominator_value=sample_size,
                        denominator_type="reviews",
                        missing_information=missing,
                        alternative_explanations=alternatives,
                        suggested_actions=THEME_ACTIONS[theme],
                        evidence_ids=[
                            evidence_by_review_id[review_id].id
                            for review_id in sorted(review_ids)
                        ],
                        session=db,
                    )
                    finding.model_run_id = ai_run.id
                    submit_finding_for_review(finding.id, project_id=project_id, session=db)
                    finding_ids.append(finding.id)

                db.add(
                    AuditEvent(
                        project_id=project_id,
                        actor_role="项目负责人",
                        action="review_ai_analysis_completed",
                        entity_type="review_batch",
                        entity_id=batch_id,
                        detail_json=json.dumps(
                            {
                                "ai_run_id": ai_run.id,
                                "finding_ids": finding_ids,
                                "prompt_version": PROMPT_VERSION,
                            },
                            ensure_ascii=False,
                        ),
                    )
                )
                db.flush()
        except Exception:
            ai_run.status = "failed"
            ai_run.error_code = "MODEL_ANALYSIS_WRITE_FAILED"
            db.flush()
            raise

        return ReviewAIAnalysisResult(
            ai_run_id=ai_run.id,
            finding_ids=finding_ids,
            prompt_version=PROMPT_VERSION,
            status="success",
        )
