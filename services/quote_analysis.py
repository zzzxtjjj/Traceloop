import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import CrossProjectReferenceError
from core.models import (
    Artifact,
    AuditEvent,
    BusinessObject,
    Decision,
    Evidence,
    Finding,
    SupplierQuote,
)
from core.schemas import QuoteAnalysis, QuoteRiskAssessment
from services.evidence_service import (
    create_evidence,
    create_finding,
    link_evidence,
    submit_finding_for_review,
)
from services.supplier_scoring import DEFAULT_WEIGHTS, calculate_supplier_scores


def _quote_evidence(db: Session, project_id: int, quote_id: int) -> Evidence:
    evidence = db.scalar(
        select(Evidence).where(
            Evidence.project_id == project_id,
            Evidence.source_entity_type == "supplier_quote",
            Evidence.source_entity_id == quote_id,
        )
    )
    if evidence:
        return evidence
    quote = db.get(SupplierQuote, quote_id)
    if not quote:
        raise ValueError("报价记录不存在。")
    supplier = db.scalar(
        select(BusinessObject).where(
            BusinessObject.project_id == project_id,
            BusinessObject.object_type == "supplier",
            BusinessObject.external_key == quote.supplier,
        )
    )
    if not supplier:
        supplier = BusinessObject(
            project_id=project_id,
            object_type="supplier",
            external_key=quote.supplier,
            display_name=quote.supplier,
        )
        db.add(supplier)
        db.flush()
    return create_evidence(
        project_id=project_id,
        evidence_type="supplier_quote_row",
        source_entity_type="supplier_quote",
        source_entity_id=quote.id,
        locator={
            "artifact_id": quote.artifact_id,
            "quote_id": quote.id,
            "backfilled_from_database": True,
        },
        excerpt=json.dumps(
            {
                "supplier": quote.supplier,
                "unit_price": quote.unit_price,
                "currency": quote.currency,
                "moq": quote.moq,
                "lead_time_days": quote.lead_time_days,
                "payment_terms": quote.payment_terms,
                "quality_note": quote.quality_note,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        business_object_id=supplier.id,
        session=db,
    )


def _clarifications(quote: SupplierQuote, risk_hits: list[str]) -> list[str]:
    questions = [
        "请确认单价对应的计价单位、规格和数量阶梯。",
        "请确认报价是否包含包装、运输、关税及其他落地费用。",
        "请确认适用的贸易术语（Incoterm）和有效期。",
    ]
    if not quote.quality_note.strip():
        questions.append("请补充样品确认、认证及近期质量记录。")
    if risk_hits:
        questions.append("请针对质量备注中的风险项提供证明材料和整改说明。")
    return questions


def analyze_quote_artifact(
    *,
    project_id: int,
    artifact_id: int,
    weights: dict[str, int | float] | None = None,
    session: Session | None = None,
) -> QuoteAnalysis:
    with session_context(session) as db:
        artifact = db.get(Artifact, artifact_id)
        if (
            not artifact
            or artifact.project_id != project_id
            or artifact.artifact_type != "supplier_quotes"
        ):
            raise CrossProjectReferenceError("报价批次不存在或不属于当前项目。")
        quotes = list(
            db.scalars(
                select(SupplierQuote)
                .where(SupplierQuote.artifact_id == artifact_id)
                .order_by(SupplierQuote.id)
            )
        )
        scores = calculate_supplier_scores(quotes, weights or DEFAULT_WEIGHTS)
        score_by_supplier = {score.supplier: score for score in scores}
        assessments: list[QuoteRiskAssessment] = []
        for quote in quotes:
            score = score_by_supplier[quote.supplier]
            evidence = _quote_evidence(db, project_id, quote.id)
            missing_information = [
                "当前 CSV 没有独立的计价单位/规格字段",
                "当前 CSV 没有运输、关税和其他落地成本字段",
                "当前 CSV 没有贸易术语和报价有效期字段",
            ]
            risk_level = (
                "yellow" if score.risk_hits or not quote.quality_note.strip() else "unknown"
            )
            risk_reasons = (
                [f"质量备注命中透明规则关键词：{item}" for item in score.risk_hits]
                if score.risk_hits
                else ["未命中已配置的质量风险关键词"]
            )
            finding_type = f"quote_risk:{artifact_id}:{quote.id}"
            finding = db.scalar(
                select(Finding).where(
                    Finding.project_id == project_id,
                    Finding.finding_type == finding_type,
                )
            )
            if not finding:
                finding = create_finding(
                    project_id=project_id,
                    finding_type=finding_type,
                    statement=(
                        f"供应商“{quote.supplier}”的报价质量备注"
                        + (
                            f"命中风险关键词：{'、'.join(score.risk_hits)}。"
                            if score.risk_hits
                            else "未命中当前风险关键词；这不代表不存在质量风险。"
                        )
                    ),
                    epistemic_status="confirmed_fact",
                    confidence=1.0,
                    missing_information=missing_information,
                    alternative_explanations=[
                        "关键词命中仅反映原始备注文本",
                        "完整风险仍取决于尚未提供的认证、样品和履约资料",
                    ],
                    suggested_actions=_clarifications(quote, score.risk_hits),
                    evidence_ids=[evidence.id],
                    session=db,
                )
                submit_finding_for_review(finding.id, project_id=project_id, session=db)
            assessments.append(
                QuoteRiskAssessment(
                    quote_id=quote.id,
                    supplier=quote.supplier,
                    finding_id=finding.id,
                    evidence_id=evidence.id,
                    risk_level=risk_level,
                    risk_reasons=risk_reasons,
                    missing_information=missing_information,
                    clarification_questions=_clarifications(quote, score.risk_hits),
                )
            )
        return QuoteAnalysis(
            artifact_id=artifact_id,
            scores=scores,
            assessments=assessments,
            comparability_notes=[
                "币种已在导入阶段统一校验。",
                "价格、MOQ 与交期只在本批次内归一化比较。",
                "缺少计价单位、规格和落地成本，不能据此比较总采购成本。",
            ],
        )


def confirm_supplier_decision(
    *,
    project_id: int,
    artifact_id: int,
    supplier: str,
    reason: str,
    actor_role: str,
    session: Session | None = None,
) -> Decision:
    if not reason.strip():
        raise ValueError("人工决策必须填写理由。")
    with session_context(session) as db:
        artifact = db.get(Artifact, artifact_id)
        if not artifact or artifact.project_id != project_id:
            raise CrossProjectReferenceError("报价批次不存在或不属于当前项目。")
        supplier_exists = db.scalar(
            select(SupplierQuote.id).where(
                SupplierQuote.artifact_id == artifact_id,
                SupplierQuote.supplier == supplier,
            )
        )
        if not supplier_exists:
            raise ValueError("所选供应商不在当前报价批次中。")
        existing = db.scalar(
            select(Decision).where(
                Decision.project_id == project_id,
                Decision.artifact_id == artifact_id,
            )
        )
        if existing:
            existing.human_choice = supplier
            existing.reason = reason.strip()
            decision = existing
        else:
            decision = Decision(
                project_id=project_id,
                artifact_id=artifact_id,
                ai_choice=None,
                human_choice=supplier,
                reason=reason.strip(),
            )
            db.add(decision)
            db.flush()
        evidence_ids = list(
            db.scalars(
                select(Evidence.id)
                .join(SupplierQuote, Evidence.source_entity_id == SupplierQuote.id)
                .where(
                    Evidence.project_id == project_id,
                    Evidence.source_entity_type == "supplier_quote",
                    SupplierQuote.artifact_id == artifact_id,
                )
            )
        )
        for evidence_id in evidence_ids:
            link_evidence(
                project_id=project_id,
                evidence_id=evidence_id,
                target_type="decision",
                target_id=decision.id,
                relation_type="considered_for",
                session=db,
            )
        db.add(
            AuditEvent(
                project_id=project_id,
                actor_role=actor_role,
                action="supplier_decision_confirmed",
                entity_type="decision",
                entity_id=decision.id,
                detail_json=json.dumps(
                    {"supplier": supplier, "evidence_ids": evidence_ids},
                    ensure_ascii=False,
                ),
            )
        )
        db.flush()
        return decision
