import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import CrossProjectReferenceError, EvidenceRequiredError
from core.models import (
    Artifact,
    BusinessObject,
    DailyReport,
    Decision,
    Evidence,
    EvidenceLink,
    Finding,
    Generation,
    ImprovementRecord,
    Review,
    ReviewBatch,
    SupplierQuote,
    Task,
    TaskSubmission,
    ValidationResult,
)

DIRECT_PROJECT_TARGETS = {
    "artifact": Artifact,
    "business_object": BusinessObject,
    "daily_report": DailyReport,
    "decision": Decision,
    "finding": Finding,
    "generation": Generation,
    "improvement_record": ImprovementRecord,
    "review_batch": ReviewBatch,
    "task": Task,
    "task_submission": TaskSubmission,
}


def _target_project_id(db: Session, target_type: str, target_id: int) -> int | None:
    model = DIRECT_PROJECT_TARGETS.get(target_type)
    if model is not None:
        target = db.get(model, target_id)
        return target.project_id if target else None

    if target_type == "review":
        review = db.get(Review, target_id)
        batch = db.get(ReviewBatch, review.batch_id) if review else None
        return batch.project_id if batch else None
    if target_type == "supplier_quote":
        quote = db.get(SupplierQuote, target_id)
        artifact = db.get(Artifact, quote.artifact_id) if quote else None
        return artifact.project_id if artifact else None
    if target_type == "validation_result":
        result = db.get(ValidationResult, target_id)
        generation = db.get(Generation, result.generation_id) if result else None
        return generation.project_id if generation else None
    return None


def _canonical_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_evidence_dedupe_key(
    source_entity_type: str,
    source_entity_id: int,
    locator: dict,
    excerpt: str,
) -> tuple[str, str]:
    content_hash = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    payload = f"{source_entity_type}:{source_entity_id}:{_canonical_json(locator)}:{content_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), content_hash


def create_evidence(
    *,
    project_id: int,
    evidence_type: str,
    source_entity_type: str,
    source_entity_id: int,
    locator: dict,
    excerpt: str,
    business_object_id: int | None = None,
    observed_at: datetime | None = None,
    session: Session | None = None,
) -> Evidence:
    if not excerpt.strip():
        raise ValueError("证据原文不能为空。")
    dedupe_key, content_hash = build_evidence_dedupe_key(
        source_entity_type, source_entity_id, locator, excerpt
    )
    with session_context(session) as db:
        existing = db.scalar(
            select(Evidence).where(
                Evidence.project_id == project_id,
                Evidence.dedupe_key == dedupe_key,
            )
        )
        if existing:
            return existing
        evidence = Evidence(
            project_id=project_id,
            evidence_type=evidence_type,
            source_entity_type=source_entity_type,
            source_entity_id=source_entity_id,
            locator_json=_canonical_json(locator),
            excerpt=excerpt,
            content_hash=content_hash,
            dedupe_key=dedupe_key,
            business_object_id=business_object_id,
            observed_at=observed_at,
        )
        db.add(evidence)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise
        return evidence


def link_evidence(
    *,
    project_id: int,
    evidence_id: int,
    target_type: str,
    target_id: int,
    relation_type: str = "supports",
    session: Session | None = None,
) -> EvidenceLink:
    with session_context(session) as db:
        evidence = db.get(Evidence, evidence_id)
        if not evidence or evidence.project_id != project_id:
            raise CrossProjectReferenceError("证据不存在或不属于当前项目。")
        target_project_id = _target_project_id(db, target_type, target_id)
        if target_project_id != project_id:
            raise CrossProjectReferenceError(
                f"关联目标 {target_type} 不存在、不受支持或不属于当前项目。"
            )

        existing = db.scalar(
            select(EvidenceLink).where(
                EvidenceLink.evidence_id == evidence_id,
                EvidenceLink.target_type == target_type,
                EvidenceLink.target_id == target_id,
                EvidenceLink.relation_type == relation_type,
            )
        )
        if existing:
            return existing
        link = EvidenceLink(
            project_id=project_id,
            evidence_id=evidence_id,
            target_type=target_type,
            target_id=target_id,
            relation_type=relation_type,
        )
        db.add(link)
        db.flush()
        return link


def create_finding(
    *,
    project_id: int,
    finding_type: str,
    statement: str,
    epistemic_status: str,
    confidence: float | None = None,
    sample_size: int | None = None,
    denominator_value: int | None = None,
    denominator_type: str | None = None,
    missing_information: list[str] | None = None,
    alternative_explanations: list[str] | None = None,
    suggested_actions: list[str] | None = None,
    evidence_ids: list[int] | None = None,
    session: Session | None = None,
) -> Finding:
    allowed_epistemic = {
        "confirmed_fact",
        "statistical_result",
        "model_judgment",
        "causal_hypothesis",
        "unknown",
    }
    if epistemic_status not in allowed_epistemic:
        raise ValueError("无效的认识状态。")
    with session_context(session) as db:
        finding = Finding(
            project_id=project_id,
            finding_type=finding_type,
            statement=statement.strip(),
            epistemic_status=epistemic_status,
            review_status="draft",
            confidence=confidence,
            sample_size=sample_size,
            denominator_value=denominator_value,
            denominator_type=denominator_type,
            missing_info_json=json.dumps(missing_information or [], ensure_ascii=False),
            alternative_explanations_json=json.dumps(
                alternative_explanations or [], ensure_ascii=False
            ),
            suggested_actions_json=json.dumps(suggested_actions or [], ensure_ascii=False),
        )
        db.add(finding)
        db.flush()
        for evidence_id in evidence_ids or []:
            link_evidence(
                project_id=project_id,
                evidence_id=evidence_id,
                target_type="finding",
                target_id=finding.id,
                session=db,
            )
        return finding


def submit_finding_for_review(
    finding_id: int, *, project_id: int, session: Session | None = None
) -> Finding:
    with session_context(session) as db:
        finding = db.get(Finding, finding_id)
        if not finding or finding.project_id != project_id:
            raise CrossProjectReferenceError("发现不存在或不属于当前项目。")
        evidence_count = len(
            list(
                db.scalars(
                    select(EvidenceLink).where(
                        EvidenceLink.project_id == project_id,
                        EvidenceLink.target_type == "finding",
                        EvidenceLink.target_id == finding_id,
                    )
                )
            )
        )
        if finding.epistemic_status == "confirmed_fact" and evidence_count == 0:
            raise EvidenceRequiredError("已确认事实必须关联至少一条证据。")
        finding.review_status = "pending_review"
        db.flush()
        return finding

