"""Explicit product assignments. No SKU/name inference or historical backfill."""

import json

from sqlalchemy import select

from core.db import session_context
from core.errors import CrossProjectReferenceError
from core.models import (
    Artifact,
    BusinessObject,
    DocumentExtraction,
    Evidence,
    EvidenceLink,
    Finding,
    Generation,
    ImprovementRecord,
    ProductEntityLink,
    Review,
    ReviewBatch,
    ValidationResult,
)
from services.auth_service import require_session_member

TARGETS = {
    "artifact": Artifact,
    "extraction": DocumentExtraction,
    "evidence": Evidence,
    "generation": Generation,
    "review_batch": ReviewBatch,
    "finding": Finding,
    "improvement": ImprovementRecord,
    "validation": ValidationResult,
}


def list_products(*, project_id, session_token, session=None):
    with session_context(session) as db:
        require_session_member(session_token, project_id, session=db)
        return list(
            db.scalars(
                select(BusinessObject)
                .where(
                    BusinessObject.project_id == project_id,
                    BusinessObject.object_type == "product",
                )
                .order_by(BusinessObject.id)
            )
        )


def product_for(db, kind, entity_id):
    if kind not in TARGETS:
        raise ValueError("不支持的业务记录类型。")
    return db.scalar(
        select(ProductEntityLink.product_id).where(
            getattr(ProductEntityLink, kind + "_id") == entity_id
        )
    )


def create_product(*, project_id, session_token, external_key, display_name, session=None):
    with session_context(session) as db:
        _, member = require_session_member(session_token, project_id, session=db)
        if member.role != "owner":
            from core.errors import ProjectAccessDeniedError

            raise ProjectAccessDeniedError("只有负责人可以创建产品。")
        if not external_key.strip() or not display_name.strip():
            raise ValueError("产品业务编号和名称不能为空。")
        existing = db.scalar(
            select(BusinessObject).where(
                BusinessObject.project_id == project_id,
                BusinessObject.object_type == "product",
                BusinessObject.external_key == external_key.strip(),
            )
        )
        if existing:
            return existing
        product = BusinessObject(
            project_id=project_id,
            object_type="product",
            external_key=external_key.strip(),
            display_name=display_name.strip(),
        )
        db.add(product)
        db.flush()
        return product


def assign_product(*, project_id, session_token, product_id, kind, entity_id, session=None):
    """Owner explicitly assigns a record; contradicting related identities are rejected."""
    with session_context(session) as db:
        actor, member = require_session_member(session_token, project_id, session=db)
        if member.role != "owner":
            from core.errors import ProjectAccessDeniedError

            raise ProjectAccessDeniedError("只有项目负责人可以确认产品关联。")
        product = db.get(BusinessObject, product_id)
        if not product or product.project_id != project_id or product.object_type != "product":
            raise CrossProjectReferenceError("产品不属于当前项目。")
        if kind not in TARGETS:
            raise ValueError("不支持的业务记录类型。")
        target = db.get(TARGETS[kind], entity_id)
        target_project = getattr(target, "project_id", None)
        if kind == "validation" and target:
            generation = db.get(Generation, target.generation_id)
            target_project = generation.project_id if generation else None
        if not target or target_project != project_id:
            raise CrossProjectReferenceError("业务记录不属于当前项目。")
        relations = []
        if kind == "extraction":
            relations.append(("artifact", target.artifact_id))
        elif kind == "generation":
            if target.parent_id:
                relations.append(("generation", target.parent_id))
            try:
                envelope = json.loads(target.content)
            except (ValueError, TypeError):
                envelope = {}
            relations.extend(
                ("evidence", source["evidence_id"]) for source in envelope.get("sources", [])
            )
        elif kind == "evidence":
            if target.business_object_id and target.business_object_id != product_id:
                raise CrossProjectReferenceError("证据已属于另一个业务对象。")
            source_kind = {
                "artifact": "artifact",
                "document_extraction": "extraction",
                "review_batch": "review_batch",
            }.get(target.source_entity_type)
            if source_kind:
                relations.append((source_kind, target.source_entity_id))
            elif target.source_entity_type == "review":
                review = db.get(Review, target.source_entity_id)
                if not review:
                    raise CrossProjectReferenceError("原始评价不存在。")
                relations.append(("review_batch", review.batch_id))
        elif kind == "finding":
            source_ids = list(
                db.scalars(
                    select(EvidenceLink.evidence_id).where(
                        EvidenceLink.project_id == project_id,
                        EvidenceLink.target_type == "finding",
                        EvidenceLink.target_id == target.id,
                    )
                )
            )
            if not source_ids:
                raise ValueError("问题结论缺少原始证据关联。")
            relations.extend(("evidence", item) for item in source_ids)
        elif kind == "improvement":
            relations += [
                ("finding", target.finding_id),
                ("review_batch", target.baseline_batch_id),
            ]
            if target.followup_batch_id:
                relations.append(("review_batch", target.followup_batch_id))
        elif kind == "validation":
            relations.append(("generation", target.generation_id))
        for relation_kind, relation_id in relations:
            related = db.get(TARGETS[relation_kind], relation_id)
            if not related or related.project_id != project_id:
                raise CrossProjectReferenceError("来源记录越过项目边界。")
            existing_product = product_for(db, relation_kind, relation_id)
            if existing_product != product_id:
                raise CrossProjectReferenceError("请先确认来源记录属于同一个产品。")
        existing = db.scalar(
            select(ProductEntityLink).where(getattr(ProductEntityLink, kind + "_id") == entity_id)
        )
        if existing:
            if existing.product_id != product_id or existing.project_id != project_id:
                raise CrossProjectReferenceError("记录已关联其他产品，不允许覆盖。")
            return existing
        link = ProductEntityLink(
            project_id=project_id,
            product_id=product_id,
            assigned_by=actor.id,
            **{kind + "_id": entity_id},
        )
        db.add(link)
        db.flush()
        return link


def link_revision(
    *,
    project_id,
    session_token,
    product_id,
    improvement_id,
    original_generation_id,
    revised_generation_id,
    session=None,
):
    with session_context(session) as db:
        link = assign_product(
            project_id=project_id,
            session_token=session_token,
            product_id=product_id,
            kind="improvement",
            entity_id=improvement_id,
            session=db,
        )
        for entity_id in (original_generation_id, revised_generation_id):
            assign_product(
                project_id=project_id,
                session_token=session_token,
                product_id=product_id,
                kind="generation",
                entity_id=entity_id,
                session=db,
            )
        revised = db.get(Generation, revised_generation_id)
        if revised.parent_id != original_generation_id:
            raise ValueError("修订版本必须直接引用原版本。")
        if link.original_generation_id and (
            link.original_generation_id != original_generation_id
            or link.revised_generation_id != revised_generation_id
        ):
            raise ValueError("改进版本关系已存在，不允许覆盖。")
        link.original_generation_id = original_generation_id
        link.revised_generation_id = revised_generation_id
        db.flush()
        return link
