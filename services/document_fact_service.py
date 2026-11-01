"""Persist exact parser blocks after an explicit human confirmation."""

import json

from core.db import session_context
from core.errors import CrossProjectReferenceError
from core.models import Artifact, DocumentExtraction
from services.evidence_service import create_evidence
from services.product_identity_service import assign_product


def source_blocks(metadata):
    """Flatten actual table cells while retaining the parser's row/column locators."""
    for block in metadata.get("document_blocks", []):
        if block.get("kind") == "table" and "rows" in block:
            for row in block["rows"]:
                for column, value in enumerate(row["values"]):
                    if value.strip():
                        yield {
                            "kind": "table_cell",
                            "table_index": block["table_index"],
                            "row_index": row["row_index"],
                            "column_index": column,
                            "text": value,
                        }
        else:
            yield block


def confirm_extraction_sources(
    *, project_id, session_token, product_id, extraction_id, session=None
):
    with session_context(session) as db:
        extraction = db.get(DocumentExtraction, extraction_id)
        artifact = db.get(Artifact, extraction.artifact_id) if extraction else None
        if (
            not extraction
            or not artifact
            or extraction.project_id != project_id
            or artifact.project_id != project_id
        ):
            raise CrossProjectReferenceError("解析记录不属于当前项目。")
        if extraction.status not in {"succeeded", "partial"}:
            raise ValueError("只能确认已解析且有文本的文件。")
        for kind, entity_id in (("artifact", artifact.id), ("extraction", extraction.id)):
            assign_product(
                project_id=project_id,
                session_token=session_token,
                product_id=product_id,
                kind=kind,
                entity_id=entity_id,
                session=db,
            )
        metadata = json.loads(extraction.locator_json or "{}")
        blocks = list(source_blocks(metadata))
        if not blocks and extraction.text_excerpt.strip():
            blocks = [{"text": extraction.text_excerpt, "kind": "text", "line_start": 1}]
        sources = []
        for index, block in enumerate(blocks):
            text = str(block.get("text") or block.get("value") or "").strip()
            if not text:
                continue
            locator = {key: value for key, value in block.items() if key not in {"text", "value"}}
            locator.update(
                file_id=artifact.id,
                file_version=artifact.version,
                filename=artifact.original_filename,
                block_index=block.get("block_index", index),
            )
            evidence = create_evidence(
                project_id=project_id,
                evidence_type="product_fact",
                source_entity_type="document_extraction",
                source_entity_id=extraction.id,
                locator=locator,
                excerpt=text,
                business_object_id=product_id,
                session=db,
            )
            assign_product(
                project_id=project_id,
                session_token=session_token,
                product_id=product_id,
                kind="evidence",
                entity_id=evidence.id,
                session=db,
            )
            sources.append(evidence)
        if not sources:
            raise ValueError("文件没有可确认的原文。")
        return sources
