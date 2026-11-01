"""Offline, evidence-backed document intake and department routing."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import session_context
from core.errors import CrossProjectReferenceError
from core.models import Artifact, DocumentExtraction, Task
from services.auth_service import require_session_member
from services.document_parser import extract_artifact
from services.evidence_service import create_evidence, link_evidence


@dataclass(frozen=True)
class RoutingResult:
    document_type: str
    primary_department: str | None
    collaborating_departments: tuple[str, ...]
    related_product: str | None
    routing_confidence: float
    uncertainty: str
    routing_reason: str
    source_evidence: tuple[str, ...]
    missing_information: tuple[str, ...]


RULES = {
    "Supplier Quotation": ("采购", ("报价", "quotation", "supplier", "moq", "currency")),
    "Supplier Catalog": ("采购", ("catalog", "catalogue", "供应商目录", "product listing")),
    "Purchase Contract": ("采购", ("purchase contract", "采购合同", "payment terms", "incoterm")),
    "Product Specification": ("运营", ("specification", "规格", "product brief", "technical data")),
    "Product Manual": ("运营", ("manual", "说明书", "instruction")),
    "Product Certification": ("运营", ("certificate", "certification", "认证", "compliance")),
    "Quality Inspection Report": (
        "品控",
        ("inspection", "quality report", "检验", "缺陷", "defect"),
    ),
    "Customer Complaint": ("品控", ("complaint", "投诉", "broken", "defect")),
    "Customer Review": ("品控", ("review", "评价", "rating", "review_text")),
    "Return Record": ("品控", ("return", "退货", "refund")),
    "Marketing Material": ("运营", ("marketing", "广告", "campaign", "product copy")),
    "Sales Order": ("运营", ("sales order", "销售订单", "order number")),
    "Packing List": ("运营", ("packing list", "装箱单", "carton")),
    "Bill of Lading": ("运营", ("bill of lading", "提单", "consignee", "vessel")),
    "Logistics Record": ("运营", ("logistics", "物流", "tracking", "shipment", "delivery")),
}


def route_text(*, filename: str, text: str, columns: list[str] | None = None) -> RoutingResult:
    if filename.casefold().endswith((".html", ".htm")):
        return RoutingResult(
            "Unsupported HTML snapshot",
            None,
            (),
            None,
            0.0,
            "low",
            "HTML 已停止作为业务文件格式，需使用 PDF、DOCX、XLSX、CSV 或 TXT 版本。",
            (),
            ("可接受文件格式",),
        )
    haystack = " ".join([filename, *(columns or []), text[:50000]]).casefold()
    scored: list[tuple[int, str, str]] = []
    for document_type, (department, keywords) in RULES.items():
        score = sum(1 for keyword in keywords if keyword.casefold() in haystack)
        if score:
            scored.append((score, document_type, department))
    scored.sort(reverse=True)
    if not scored:
        return RoutingResult(
            "Unknown / Mixed Document",
            None,
            (),
            None,
            0.0,
            "low",
            "未找到足够的业务语义证据，必须人工分拣。",
            (),
            ("业务类型", "关联产品"),
        )
    top_score, doc_type, primary = scored[0]
    collaborators = tuple(dict.fromkeys(item[2] for item in scored[1:] if item[2] != primary))
    confidence = min(0.95, 0.55 + top_score * 0.12)
    uncertainty = "high" if confidence >= 0.8 else "medium" if confidence >= 0.6 else "low"
    if len({item[2] for item in scored if item[0] == top_score}) > 1:
        uncertainty, primary = "medium", None
    evidence = tuple(keyword for keyword in RULES[doc_type][1] if keyword.casefold() in haystack)[
        :5
    ]
    missing = (
        ("关联产品",)
        if not any(token in haystack for token in ("sku", "model", "型号", "na120"))
        else ()
    )
    return RoutingResult(
        doc_type,
        primary,
        collaborators,
        "NA120" if "na120" in haystack else None,
        confidence,
        uncertainty,
        f"命中业务关键词：{'、'.join(evidence)}。推荐由{primary or '多个候选部门'}人工确认。",
        evidence,
        missing,
    )


def route_artifact(
    *, project_id: int, artifact_id: int, session_token: str, session: Session | None = None
) -> RoutingResult:
    with session_context(session) as db:
        require_session_member(session_token, project_id, session=db)
        artifact = db.get(Artifact, artifact_id)
        if not artifact or artifact.project_id != project_id:
            raise CrossProjectReferenceError("文件不属于当前项目。")
        extraction = db.scalar(
            select(DocumentExtraction)
            .where(
                DocumentExtraction.project_id == project_id,
                DocumentExtraction.artifact_id == artifact_id,
            )
            .order_by(DocumentExtraction.id.desc())
        )
        if not extraction:
            extraction = extract_artifact(
                project_id=project_id,
                session_token=session_token,
                artifact_id=artifact_id,
                session=db,
            )
        blocks = json.loads(extraction.locator_json).get("document_blocks", [])
        columns = []
        for block in blocks:
            columns.extend(str(value) for value in block.get("values", []))
        return route_text(
            filename=artifact.original_filename, text=extraction.text_excerpt, columns=columns
        )


def create_routing_task_draft(
    *,
    project_id: int,
    artifact_id: int,
    result: RoutingResult,
    session_token: str,
    session: Session | None = None,
) -> Task:
    with session_context(session) as db:
        _actor, membership = require_session_member(session_token, project_id, session=db)
        if membership.role not in {"owner", "项目负责人", "department_lead", "Department Lead"}:
            raise CrossProjectReferenceError("只有项目负责人可以确认文件路由并创建任务草稿。")
        artifact = db.get(Artifact, artifact_id)
        if not artifact or artifact.project_id != project_id:
            raise CrossProjectReferenceError("文件不属于当前项目。")
        existing = db.scalar(
            select(Task).where(
                Task.project_id == project_id,
                Task.source_type == "document_routing",
                Task.source_id == artifact_id,
            )
        )
        if existing:
            return existing
        evidence = create_evidence(
            project_id=project_id,
            evidence_type="document_routing",
            source_entity_type="artifact",
            source_entity_id=artifact_id,
            locator={"artifact_id": artifact_id, "document_type": result.document_type},
            excerpt=result.routing_reason,
            session=db,
        )
        task = Task(
            project_id=project_id,
            source_type="document_routing",
            source_id=artifact_id,
            title=f"处理文件：{artifact.original_filename}",
            description=result.routing_reason,
            owner_role=result.primary_department or "项目负责人",
            status="draft",
            acceptance_criteria_json=json.dumps(
                ["确认文件类型和主责部门", "核对原始 Evidence", "完成对应业务流程分拣"],
                ensure_ascii=False,
            ),
            dependency="路由任务必须由负责人确认后发布。",
            confirmed=False,
        )
        db.add(task)
        db.flush()
        link_evidence(
            project_id=project_id,
            evidence_id=evidence.id,
            target_type="task",
            target_id=task.id,
            relation_type="source_for",
            session=db,
        )
        return task
