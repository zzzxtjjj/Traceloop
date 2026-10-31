"""Validated document-analysis boundary owned by the backend.

The service accepts an injected analyzer so tests and a future甲方 provider can use
the same persistence and evidence checks without triggering a real model call.
"""

import hashlib
import json
import time
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from core.db import session_context
from core.errors import CrossProjectReferenceError, ModelNotConfiguredError
from core.models import AiRun, Artifact, DocumentExtraction, ExtractedRequirement
from core.schemas import DocumentAnalysisOutput, DocumentAnalysisRequest
from services.auth_service import require_session_member
from services.evidence_service import create_evidence, link_evidence

PROMPT_VERSION = "document_analysis_v1"
SCHEMA_VERSION = "document_analysis_v1"


def _input_hash(request: DocumentAnalysisRequest, artifacts: list[Artifact]) -> str:
    payload = {
        "request": request.model_dump(mode="json"),
        "artifacts": [(item.id, item.sha256) for item in artifacts],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _validate_source(
    extraction: DocumentExtraction,
    artifact_id: int,
    locator: dict,
    excerpt: str,
) -> None:
    if not excerpt.strip() or excerpt not in extraction.text_excerpt:
        raise ValueError("EVIDENCE_MISSING")
    metadata = json.loads(extraction.locator_json)
    if extraction.parser_name == "csv_rows":
        row = locator.get("row", locator.get("row_number"))
        column = locator.get("column", locator.get("column_name"))
        if (
            not isinstance(row, int)
            or row < 2
            or row > int(metadata.get("row_count", 0)) + 1
        ):
            raise ValueError("EVIDENCE_LOCATOR_INVALID")
        if column is not None and column not in metadata.get("columns", []):
            raise ValueError("EVIDENCE_LOCATOR_INVALID")
    elif extraction.parser_name == "txt_lines":
        line = locator.get("line_start")
        if (
            not isinstance(line, int)
            or line < 1
            or line > int(metadata.get("line_count", 0))
        ):
            raise ValueError("EVIDENCE_LOCATOR_INVALID")


def analyze_project_documents(
    *,
    session_token: str,
    request: DocumentAnalysisRequest,
    analyzer: Callable[..., dict] | None = None,
    provider_name: str = "甲方 provider",
    session: Session | None = None,
) -> DocumentAnalysisOutput:
    started = time.perf_counter()
    with session_context(session) as db:
        require_session_member(session_token, request.project_id, session=db)
        artifacts = list(
            db.scalars(
                select(Artifact).where(
                    Artifact.project_id == request.project_id,
                    Artifact.id.in_(request.artifact_ids),
                )
            )
        )
        if len(artifacts) != len(set(request.artifact_ids)):
            raise CrossProjectReferenceError("部分文件不属于当前项目。")
        extractions = list(
            db.scalars(
                select(DocumentExtraction).where(
                    DocumentExtraction.project_id == request.project_id,
                    DocumentExtraction.artifact_id.in_(request.artifact_ids),
                    DocumentExtraction.status == "succeeded",
                )
            )
        )
        if not extractions:
            raise ValueError("当前文件没有可用的 CSV/TXT 解析结果。")
        run = AiRun(
            project_id=request.project_id,
            run_type="document_analysis",
            provider=provider_name,
            model=settings.model_name or "unconfigured",
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            input_hash=_input_hash(request, artifacts),
            status="pending",
        )
        db.add(run)
        db.flush()
        if analyzer is None:
            run.status = "failed"
            run.error_code = "MODEL_NOT_CONFIGURED"
            run.latency_ms = int((time.perf_counter() - started) * 1000)
            db.flush()
            raise ModelNotConfiguredError("文档分析模型尚未配置。")
        try:
            raw = analyzer(request=request, artifacts=artifacts, extractions=extractions)
            raw = dict(raw)
            raw["analysis_id"] = run.id
            output = DocumentAnalysisOutput.model_validate(raw)
            artifact_ids = {item.id for item in artifacts}
            for requirement in output.requirements:
                if requirement.source.artifact_id not in artifact_ids:
                    raise CrossProjectReferenceError("AI 需求引用了其他项目文件。")
                extraction = next(
                    (
                        item
                        for item in extractions
                        if item.artifact_id == requirement.source.artifact_id
                    ),
                    None,
                )
                if extraction is None:
                    raise ValueError("AI 需求引用了未成功解析的文件。")
                _validate_source(
                    extraction,
                    requirement.source.artifact_id,
                    requirement.source.locator,
                    requirement.source.excerpt,
                )
                requirement_row = ExtractedRequirement(
                    project_id=request.project_id,
                    artifact_id=requirement.source.artifact_id,
                    extraction_id=extraction.id,
                    statement=f"{requirement.title}\n{requirement.description}",
                    requirement_type=request.analysis_type,
                    owner_role=requirement.target_role,
                    acceptance_criteria_json="[]",
                    source_locator_json=json.dumps(
                        requirement.source.locator,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    source_excerpt=requirement.source.excerpt,
                    source_evidence_id=None,
                    epistemic_status="unknown" if output.unknowns else "draft",
                    priority=requirement.priority,
                    ai_run_id=run.id,
                    review_status="draft",
                )
                db.add(requirement_row)
                db.flush()
                evidence = create_evidence(
                    project_id=request.project_id,
                    evidence_type="document_requirement_source",
                    source_entity_type="document_extraction",
                    source_entity_id=extraction.id,
                    locator={
                        "artifact_id": requirement.source.artifact_id,
                        **requirement.source.locator,
                    },
                    excerpt=requirement.source.excerpt,
                    session=db,
                )
                requirement_row.source_evidence_id = evidence.id
                link_evidence(
                    project_id=request.project_id,
                    evidence_id=evidence.id,
                    target_type="extracted_requirement",
                    target_id=requirement_row.id,
                    relation_type="source_for",
                    session=db,
                )
            run.status = output.status
            run.latency_ms = int((time.perf_counter() - started) * 1000)
            db.flush()
            return output
        except Exception as exc:
            run.status = "failed"
            run.error_code = getattr(exc, "code", "MODEL_OUTPUT_VALIDATION")
            run.latency_ms = int((time.perf_counter() - started) * 1000)
            db.flush()
            raise
