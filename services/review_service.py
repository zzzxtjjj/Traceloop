import hashlib
import io
import json
import re
from pathlib import Path
from typing import BinaryIO, Protocol

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from core.db import session_context
from core.errors import CrossProjectReferenceError, ModelOutputValidationError
from core.models import (
    Artifact,
    AuditEvent,
    BusinessObject,
    Evidence,
    EvidenceLink,
    Finding,
    ImprovementRecord,
    Insight,
    Review,
    ReviewBatch,
    ReviewImportMetadata,
    ReviewThemeAssignment,
)
from core.schemas import (
    BatchComparison,
    ReviewClassification,
    ReviewImportOutcome,
    ReviewImportPreview,
    ReviewRow,
    ReviewThemeSummary,
    RowError,
)
from services.evidence_service import (
    create_evidence,
    create_finding,
    link_evidence,
    submit_finding_for_review,
)

REVIEW_REQUIRED_COLUMNS = [
    "review_id",
    "batch",
    "rating",
    "date",
    "sku",
    "market",
    "review_text",
]
REVIEW_OPTIONAL_COLUMNS = ["order_id", "production_batch", "supplier"]
TAXONOMY_VERSION = "review_themes_v1"

THEME_LABELS = {
    "packaging_damage": "包装破损",
    "product_quality": "产品质量",
    "description_mismatch": "尺寸或描述不符",
    "logistics_delay": "物流时效",
    "usage_difficulty": "使用困难",
    "customer_service": "客服体验",
    "other": "其他",
}

THEME_KEYWORDS = {
    "packaging_damage": [
        "box arrived crushed",
        "packaging was damaged",
        "damaged box",
        "arrived crushed",
        "had a dent",
        "包装破损",
        "外箱破损",
        "凹陷",
    ],
    "product_quality": ["leak", "broken", "defect", "scratch", "质量", "漏水", "瑕疵"],
    "description_mismatch": [
        "different from the description",
        "dimensions could be clearer",
        "not as described",
        "描述不符",
        "尺寸不符",
    ],
    "logistics_delay": [
        "delivery took much longer",
        "delivery was late",
        "late delivery",
        "物流延迟",
        "到货慢",
    ],
    "usage_difficulty": [
        "instructions were difficult",
        "hard to follow",
        "difficult to use",
        "说明难懂",
        "使用困难",
    ],
    "customer_service": ["customer service", "no response", "support", "客服", "无人回复"],
}

THEME_ACTIONS = {
    "packaging_damage": ["核查包装规范与跌落/抗压测试记录", "补充物流节点或批次信息"],
    "product_quality": ["核查质检记录与缺陷样品", "确认是否存在同批次集中问题"],
    "description_mismatch": ["复核商品资料与实物规格", "更新容易误解的尺寸说明"],
    "logistics_delay": ["核查承诺时效与实际物流轨迹", "区分仓内与承运阶段"],
    "usage_difficulty": ["复核说明书与常见问题", "开展小范围可用性检查"],
    "customer_service": ["核查客服工单与响应时间", "补充客户沟通记录"],
    "other": ["人工阅读未归类评价", "决定是否扩展主题字典"],
}

THEME_ALTERNATIVES = {
    "packaging_damage": ["供应商装箱环节", "干线或末端物流挤压", "样本偏差"],
    "product_quality": ["生产批次差异", "运输或使用过程影响", "个别样本"],
    "description_mismatch": ["商品资料不清晰", "市场表达差异", "用户预期差异"],
    "logistics_delay": ["仓内处理", "承运商延误", "节假日或天气"],
    "usage_difficulty": ["说明书表达", "产品设计", "用户经验差异"],
    "customer_service": ["渠道工单遗漏", "时区差异", "评价未提供完整沟通记录"],
    "other": ["现有主题字典未覆盖", "评价语义不足"],
}


class ReviewClassifier(Protocol):
    def classify(self, review: Review) -> ReviewClassification: ...


class RuleBasedReviewClassifier:
    def classify(self, review: Review) -> ReviewClassification:
        normalized = review.review_text.casefold()
        themes = [
            theme
            for theme, keywords in THEME_KEYWORDS.items()
            if any(keyword.casefold() in normalized for keyword in keywords)
        ]
        if not themes:
            themes = ["other"]
        return ReviewClassification(
            review_id=review.external_id,
            themes=themes,
            evidence_excerpt=review.review_text,
            confidence=1.0 if themes != ["other"] else 0.5,
            classification_method="rule_based",
            missing_information=[],
            alternative_explanations=[],
        )


def _read_source(source: str | Path | bytes | BinaryIO) -> tuple[bytes, str]:
    if isinstance(source, bytes):
        return source, "reviews.csv"
    if isinstance(source, (str, Path)):
        path = Path(source)
        return path.read_bytes(), path.name
    if hasattr(source, "getvalue"):
        return source.getvalue(), Path(getattr(source, "name", "reviews.csv")).name
    return source.read(), Path(getattr(source, "name", "reviews.csv")).name


def preview_review_csv(source: str | Path | bytes | BinaryIO) -> ReviewImportPreview:
    raw, filename = _read_source(source)
    digest = hashlib.sha256(raw).hexdigest()
    rows: list[ReviewRow] = []
    errors: list[RowError] = []
    try:
        frame = pd.read_csv(io.BytesIO(raw), dtype="string")
    except Exception as exc:
        return ReviewImportPreview(
            rows=[],
            errors=[RowError(row_number=1, field="file", message=f"无法读取 CSV：{exc}")],
            filename=filename,
            sha256=digest,
        )

    missing = [column for column in REVIEW_REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        return ReviewImportPreview(
            rows=[],
            errors=[
                RowError(row_number=1, field=column, message="缺少必填列")
                for column in missing
            ],
            filename=filename,
            sha256=digest,
        )

    for column in REVIEW_OPTIONAL_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""

    for index, record in frame[REVIEW_REQUIRED_COLUMNS + REVIEW_OPTIONAL_COLUMNS].iterrows():
        values = {key: ("" if pd.isna(value) else value) for key, value in record.to_dict().items()}
        try:
            rows.append(ReviewRow.model_validate(values))
        except ValidationError as exc:
            for issue in exc.errors():
                errors.append(
                    RowError(
                        row_number=int(index) + 2,
                        field=str(issue["loc"][0]),
                        message=issue["msg"],
                    )
                )

    if not len(frame.index):
        errors.append(RowError(row_number=2, field="file", message="CSV 中没有评价数据"))
    ids = [row.review_id.casefold() for row in rows]
    for duplicate in sorted({item for item in ids if ids.count(item) > 1}):
        errors.append(
            RowError(
                row_number=1,
                field="review_id",
                message=f"评价 ID 重复：{duplicate}",
            )
        )
    markets = sorted({row.market.upper() for row in rows})
    if len(markets) > 1:
        errors.append(
            RowError(
                row_number=1,
                field="market",
                message=f"一个批次只能包含一个市场：{', '.join(markets)}",
            )
        )
    return ReviewImportPreview(rows=rows, errors=errors, filename=filename, sha256=digest)


def _get_or_create_business_object(
    db: Session,
    *,
    project_id: int,
    object_type: str,
    external_key: str,
    display_name: str,
) -> BusinessObject | None:
    if not external_key:
        return None
    existing = db.scalar(
        select(BusinessObject).where(
            BusinessObject.project_id == project_id,
            BusinessObject.object_type == object_type,
            BusinessObject.external_key == external_key,
        )
    )
    if existing:
        return existing
    obj = BusinessObject(
        project_id=project_id,
        object_type=object_type,
        external_key=external_key,
        display_name=display_name,
    )
    db.add(obj)
    db.flush()
    return obj


def import_reviews(
    *,
    project_id: int,
    source: str | Path | bytes | BinaryIO,
    batch_name: str,
    upload_root: Path | None = None,
    session: Session | None = None,
) -> ReviewImportOutcome:
    preview = preview_review_csv(source)
    if not preview.is_valid:
        messages = "; ".join(f"{error.field}: {error.message}" for error in preview.errors)
        raise ValueError(f"评价 CSV 未通过校验：{messages}")
    raw, _ = _read_source(source)
    with session_context(session) as db:
        existing_artifact = db.scalar(
            select(Artifact).where(
                Artifact.project_id == project_id,
                Artifact.artifact_type == "review_batch",
                Artifact.sha256 == preview.sha256,
            )
        )
        if existing_artifact:
            metadata = db.scalar(
                select(ReviewImportMetadata).where(
                    ReviewImportMetadata.artifact_id == existing_artifact.id
                )
            )
            if metadata:
                return ReviewImportOutcome(
                    batch_id=metadata.batch_id,
                    artifact_id=metadata.artifact_id,
                    inserted_count=0,
                    duplicate_count=len(preview.rows),
                    duplicate_file=True,
                )

        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(preview.filename).name)
        artifact = Artifact(
            project_id=project_id,
            artifact_type="review_batch",
            batch_name=batch_name.strip() or preview.rows[0].batch,
            original_filename=preview.filename,
            sha256=preview.sha256,
            parse_status="valid",
        )
        db.add(artifact)
        db.flush()
        storage_root = upload_root or settings.upload_dir
        project_dir = storage_root / str(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        stored_path = project_dir / f"{artifact.id}_{safe_name}"
        stored_path.write_bytes(raw)
        artifact.stored_path = str(stored_path)

        batch = ReviewBatch(
            project_id=project_id,
            name=batch_name.strip() or preview.rows[0].batch,
            market=preview.rows[0].market.upper(),
            sample_size=0,
            prompt_version=TAXONOMY_VERSION,
        )
        db.add(batch)
        db.flush()

        existing_ids = {
            external_id.casefold()
            for external_id in db.scalars(
                select(Review.external_id)
                .join(ReviewBatch, Review.batch_id == ReviewBatch.id)
                .where(ReviewBatch.project_id == project_id)
            )
        }
        inserted = 0
        duplicates = 0
        for row_number, row in enumerate(preview.rows, start=2):
            normalized_review_id = row.review_id.casefold()
            if normalized_review_id in existing_ids:
                duplicates += 1
                continue
            review = Review(
                batch_id=batch.id,
                external_id=row.review_id,
                rating=row.rating,
                sku=row.sku,
                review_text=row.review_text,
            )
            db.add(review)
            db.flush()
            product = _get_or_create_business_object(
                db,
                project_id=project_id,
                object_type="product",
                external_key=row.sku,
                display_name=row.sku,
            )
            related_objects = []
            for object_type, key in (
                ("order", row.order_id),
                ("production_batch", row.production_batch),
                ("supplier", row.supplier),
            ):
                related = _get_or_create_business_object(
                    db,
                    project_id=project_id,
                    object_type=object_type,
                    external_key=key,
                    display_name=key,
                )
                if related:
                    related_objects.append(related)
            review_evidence = create_evidence(
                project_id=project_id,
                evidence_type="review_text",
                source_entity_type="review",
                source_entity_id=review.id,
                locator={
                    "artifact_id": artifact.id,
                    "batch_id": batch.id,
                    "csv_row": row_number,
                    "review_id": row.review_id,
                    "sku": row.sku,
                    "order_id": row.order_id,
                    "production_batch": row.production_batch,
                    "supplier": row.supplier,
                    "date": row.date.isoformat(),
                },
                excerpt=row.review_text,
                business_object_id=product.id if product else None,
                session=db,
            )
            for related in related_objects:
                link_evidence(
                    project_id=project_id,
                    evidence_id=review_evidence.id,
                    target_type="business_object",
                    target_id=related.id,
                    relation_type="exact_identifier",
                    session=db,
                )
            existing_ids.add(normalized_review_id)
            inserted += 1

        batch.sample_size = inserted
        dates = [row.date for row in preview.rows]
        metadata = ReviewImportMetadata(
            project_id=project_id,
            batch_id=batch.id,
            artifact_id=artifact.id,
            source_sha256=preview.sha256,
            time_window_start=pd.Timestamp(min(dates)).to_pydatetime(),
            time_window_end=pd.Timestamp(max(dates)).to_pydatetime(),
            taxonomy_version=TAXONOMY_VERSION,
        )
        db.add(metadata)
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role="项目负责人",
                action="review_batch_imported",
                entity_type="review_batch",
                entity_id=batch.id,
                detail_json=json.dumps(
                    {"inserted": inserted, "duplicates": duplicates}, ensure_ascii=False
                ),
            )
        )
        db.flush()
        return ReviewImportOutcome(
            batch_id=batch.id,
            artifact_id=artifact.id,
            inserted_count=inserted,
            duplicate_count=duplicates,
        )


def list_review_batches(project_id: int, session: Session | None = None) -> list[ReviewBatch]:
    with session_context(session) as db:
        return list(
            db.scalars(
                select(ReviewBatch)
                .where(ReviewBatch.project_id == project_id)
                .order_by(ReviewBatch.id.desc())
            )
        )


def _batch_missing_information(evidence: list[Evidence]) -> list[str]:
    locators = [json.loads(item.locator_json) for item in evidence]
    missing: list[str] = []
    if not any(locator.get("production_batch") for locator in locators):
        missing.append("评价未提供可验证的生产批次关联")
    if not any(locator.get("order_id") for locator in locators):
        missing.append("评价未提供可验证的订单关联")
    if not any(locator.get("supplier") for locator in locators):
        missing.append("评价未提供可验证的供应商关联")
    return missing


def analyze_review_batch(
    *,
    project_id: int,
    batch_id: int,
    classifier: ReviewClassifier | None = None,
    session: Session | None = None,
) -> list[ReviewThemeSummary]:
    classifier = classifier or RuleBasedReviewClassifier()
    with session_context(session) as db:
        batch = db.get(ReviewBatch, batch_id)
        if not batch or batch.project_id != project_id:
            raise CrossProjectReferenceError("评价批次不存在或不属于当前项目。")
        reviews = list(
            db.scalars(select(Review).where(Review.batch_id == batch_id).order_by(Review.id))
        )
        if not reviews:
            return []

        existing_assignments = list(
            db.scalars(
                select(ReviewThemeAssignment).where(
                    ReviewThemeAssignment.batch_id == batch_id,
                    ReviewThemeAssignment.taxonomy_version == TAXONOMY_VERSION,
                )
            )
        )
        if existing_assignments:
            insights = list(db.scalars(select(Insight).where(Insight.batch_id == batch_id)))
            findings = list(
                db.scalars(
                    select(Finding).where(
                        Finding.project_id == project_id,
                        Finding.finding_type.like(f"review_theme:{batch_id}:%"),
                    )
                )
            )
            finding_by_theme = {
                finding.finding_type.rsplit(":", maxsplit=1)[-1]: finding
                for finding in findings
            }
            return sorted(
                [
                    ReviewThemeSummary(
                        theme=insight.theme,
                        count=insight.count,
                        share=insight.share,
                        sample_size=len(reviews),
                        finding_id=(
                            finding_by_theme[insight.theme].id
                            if insight.theme in finding_by_theme
                            else None
                        ),
                    )
                    for insight in insights
                ],
                key=lambda item: (-item.count, item.theme),
            )

        review_by_external = {review.external_id: review for review in reviews}
        evidence_by_review = {
            evidence.source_entity_id: evidence
            for evidence in db.scalars(
                select(Evidence).where(
                    Evidence.project_id == project_id,
                    Evidence.source_entity_type == "review",
                    Evidence.source_entity_id.in_([review.id for review in reviews]),
                )
            )
        }
        theme_review_ids: dict[str, list[int]] = {}
        confidences: dict[str, list[float]] = {}
        classifier_missing: dict[str, list[str]] = {}
        classifier_alternatives: dict[str, list[str]] = {}
        for review in reviews:
            result = classifier.classify(review)
            if result.review_id != review.external_id or result.review_id not in review_by_external:
                raise ModelOutputValidationError("分类结果引用了错误或不存在的评价 ID。")
            if result.evidence_excerpt not in review.review_text:
                raise ModelOutputValidationError("分类证据不是评价原文的连续片段。")
            for theme in sorted(set(result.themes)):
                if theme not in THEME_LABELS:
                    raise ModelOutputValidationError(f"分类结果包含未知主题：{theme}")
                db.add(
                    ReviewThemeAssignment(
                        project_id=project_id,
                        batch_id=batch_id,
                        review_id=review.id,
                        theme=theme,
                        classification_method=result.classification_method,
                        confidence=result.confidence,
                        evidence_excerpt=result.evidence_excerpt,
                        taxonomy_version=TAXONOMY_VERSION,
                    )
                )
                theme_review_ids.setdefault(theme, []).append(review.id)
                confidences.setdefault(theme, []).append(result.confidence)
                classifier_missing.setdefault(theme, []).extend(result.missing_information)
                classifier_alternatives.setdefault(theme, []).extend(
                    result.alternative_explanations
                )

        summaries: list[ReviewThemeSummary] = []
        sample_size = len(reviews)
        for theme, review_ids in sorted(theme_review_ids.items()):
            count = len(set(review_ids))
            share = count / sample_size
            insight = Insight(
                batch_id=batch_id,
                theme=theme,
                count=count,
                share=share,
                confidence=sum(confidences[theme]) / len(confidences[theme]),
                evidence_review_ids_json=json.dumps(review_ids),
            )
            db.add(insight)
            evidence = [
                evidence_by_review[item] for item in review_ids if item in evidence_by_review
            ]
            finding = create_finding(
                project_id=project_id,
                finding_type=f"review_theme:{batch_id}:{theme}",
                statement=(
                    f"批次“{batch.name}”的 {sample_size} 条评价中，{count} 条经"
                    f"{('规则' if isinstance(classifier, RuleBasedReviewClassifier) else '模型')}"
                    f"分类包含“{THEME_LABELS[theme]}”主题，占 {share:.1%}。"
                ),
                epistemic_status=(
                    "statistical_result"
                    if isinstance(classifier, RuleBasedReviewClassifier)
                    else "model_judgment"
                ),
                confidence=insight.confidence,
                sample_size=sample_size,
                denominator_value=sample_size,
                denominator_type="reviews",
                missing_information=sorted(
                    set(_batch_missing_information(evidence) + classifier_missing[theme])
                ),
                alternative_explanations=sorted(
                    set(THEME_ALTERNATIVES[theme] + classifier_alternatives[theme])
                ),
                suggested_actions=THEME_ACTIONS[theme],
                evidence_ids=[item.id for item in evidence],
                session=db,
            )
            submit_finding_for_review(finding.id, project_id=project_id, session=db)
            summaries.append(
                ReviewThemeSummary(
                    theme=theme,
                    count=count,
                    share=share,
                    sample_size=sample_size,
                    finding_id=finding.id,
                )
            )
        db.flush()
        return sorted(summaries, key=lambda item: (-item.count, item.theme))


def list_batch_findings(
    project_id: int, batch_id: int, session: Session | None = None
) -> list[Finding]:
    with session_context(session) as db:
        return list(
            db.scalars(
                select(Finding)
                .where(
                    Finding.project_id == project_id,
                    Finding.finding_type.like(f"review_theme:{batch_id}:%"),
                )
                .order_by(Finding.id)
            )
        )


def get_finding_evidence(
    project_id: int, finding_id: int, session: Session | None = None
) -> list[Evidence]:
    with session_context(session) as db:
        return list(
            db.scalars(
                select(Evidence)
                .join(EvidenceLink, Evidence.id == EvidenceLink.evidence_id)
                .where(
                    EvidenceLink.project_id == project_id,
                    EvidenceLink.target_type == "finding",
                    EvidenceLink.target_id == finding_id,
                )
                .order_by(Evidence.id)
            )
        )


def compare_review_batches(
    *,
    project_id: int,
    baseline_batch_id: int,
    followup_batch_id: int,
    theme: str,
    minimum_sample_size: int = 10,
    session: Session | None = None,
) -> BatchComparison:
    with session_context(session) as db:
        baseline_batch = db.get(ReviewBatch, baseline_batch_id)
        followup_batch = db.get(ReviewBatch, followup_batch_id)
        if (
            not baseline_batch
            or not followup_batch
            or baseline_batch.project_id != project_id
            or followup_batch.project_id != project_id
        ):
            raise CrossProjectReferenceError("对比批次不存在或不属于当前项目。")
        base = db.scalar(
            select(Insight).where(Insight.batch_id == baseline_batch_id, Insight.theme == theme)
        )
        follow = db.scalar(
            select(Insight).where(Insight.batch_id == followup_batch_id, Insight.theme == theme)
        )
        base_count = base.count if base else 0
        follow_count = follow.count if follow else 0
        base_share = base.share if base else 0.0
        follow_share = follow.share if follow else 0.0
        share_delta = follow_share - base_share
        limitation = "评价占比不是商品实际故障率，前后变化不能单独证明改进措施造成结果。"
        if (
            baseline_batch.sample_size < minimum_sample_size
            or followup_batch.sample_size < minimum_sample_size
        ):
            conclusion = "样本量不足，暂不能判断趋势。"
            limitation = f"两批样本均需至少 {minimum_sample_size} 条；" + limitation
        elif share_delta < -0.02:
            conclusion = "在相同评价分类口径下，问题评价占比出现下降趋势。"
        elif share_delta > 0.02:
            conclusion = "在相同评价分类口径下，问题评价占比出现上升趋势。"
        else:
            conclusion = "在相同评价分类口径下，问题评价占比暂未出现明显变化。"
        return BatchComparison(
            theme=theme,
            baseline_batch_id=baseline_batch_id,
            followup_batch_id=followup_batch_id,
            baseline_count=base_count,
            followup_count=follow_count,
            baseline_share=base_share,
            followup_share=follow_share,
            baseline_sample_size=baseline_batch.sample_size,
            followup_sample_size=followup_batch.sample_size,
            count_delta=follow_count - base_count,
            share_delta=share_delta,
            conclusion=conclusion,
            limitation_note=limitation,
        )


def apply_comparison_to_improvement(
    *,
    improvement_id: int,
    comparison: BatchComparison,
    project_id: int,
    session: Session | None = None,
) -> ImprovementRecord:
    with session_context(session) as db:
        record = db.get(ImprovementRecord, improvement_id)
        if not record or record.project_id != project_id:
            raise CrossProjectReferenceError("改进记录不存在或不属于当前项目。")
        if (
            record.theme != comparison.theme
            or record.baseline_batch_id != comparison.baseline_batch_id
        ):
            raise ValueError("复检主题或基线批次与改进记录不一致。")
        record.followup_batch_id = comparison.followup_batch_id
        record.followup_count = comparison.followup_count
        record.followup_share = comparison.followup_share
        record.followup_sample_size = comparison.followup_sample_size
        record.count_delta = comparison.count_delta
        record.share_delta = comparison.share_delta
        record.status = "rechecked"
        record.limitation_note = comparison.limitation_note
        db.flush()
        return record

