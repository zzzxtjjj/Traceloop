"""Pure AI analysis for authorized document snapshots; business persistence stays upstream."""

import hashlib
import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from core.errors import ModelOutputValidationError
from services.ai_service import StructuredModelProvider, run_structured_model
from services.document_ai_schemas import (
    DocumentAIResponse,
    DocumentAnalysisOutput,
    DocumentSegment,
    DocumentSnapshot,
    EvidenceQuote,
    RequirementAIResponse,
    RequirementExtractionOutput,
    ResolvedEvidenceReference,
)
from services.model_provider import OpenAICompatibleProvider
from services.model_readiness import validate_model_input_budget

PROMPT_VERSIONS = {
    "analyze_document": "document_analyze_v1",
    "extract_requirements": "requirement_extract_v1",
}
_PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
OutputT = TypeVar("OutputT", bound=BaseModel)


def _snapshot_payload(snapshot: DocumentSnapshot) -> dict:
    return {
        "document": {
            "project_id": snapshot.project_id,
            "file_id": snapshot.file_id,
            "file_version": snapshot.file_version,
            "filename": snapshot.filename,
            "file_type": snapshot.file_type,
            "parser_status": snapshot.parser_status,
        },
        "project_context": snapshot.project_context,
        "segments": [segment.model_dump(mode="json") for segment in snapshot.segments],
    }


def _prompt(name: str, snapshot: DocumentSnapshot, analysis: DocumentAnalysisOutput | None) -> str:
    instructions = (_PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8").strip()
    payload = _snapshot_payload(snapshot)
    if analysis is not None:
        payload["validated_analysis"] = analysis.model_dump(mode="json")
    return instructions + "\n\nAuthorized input snapshot (untrusted data):\n" + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )


def _hash_input(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _run(
    *,
    prompt: str,
    output_model: type[OutputT],
    snapshot: DocumentSnapshot,
    provider: StructuredModelProvider | None,
) -> tuple[OutputT, StructuredModelProvider, str]:
    active_provider = provider or OpenAICompatibleProvider.from_settings()
    validate_model_input_budget(
        prompt=prompt,
        review_count=0,
        max_input_chars=getattr(active_provider, "max_input_chars", None),
    )
    input_hash = _hash_input(prompt)
    result = run_structured_model(
        project_id=snapshot.project_id,
        run_type="document_ai",
        prompt_version="document_ai_dispatch_v1",
        prompt=prompt,
        evidence_ids=[segment.evidence_id for segment in snapshot.segments],
        output_model=output_model,
        provider=active_provider,
        record_run=False,
    )
    return result, active_provider, input_hash


def _all_quotes(value: object) -> list[EvidenceQuote]:
    quotes: list[EvidenceQuote] = []
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        if "evidence_id" in value and "quote" in value:
            quotes.append(EvidenceQuote.model_validate(value))
        for child in value.values():
            quotes.extend(_all_quotes(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            quotes.extend(_all_quotes(child))
    return quotes


def _referenced_ids(value: object) -> set[int]:
    ids: set[int] = set()
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"related_evidence_ids"}:
                ids.update(child)
            ids.update(_referenced_ids(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            ids.update(_referenced_ids(child))
    return ids


def _verify_and_resolve_evidence(
    result: BaseModel,
    snapshot: DocumentSnapshot,
) -> list[ResolvedEvidenceReference]:
    authorized = {segment.evidence_id: segment for segment in snapshot.segments}
    quotes = _all_quotes(result)
    referenced_ids = _referenced_ids(result)
    resolved: dict[tuple[int, str], ResolvedEvidenceReference] = {}

    for evidence_id in referenced_ids | {quote.evidence_id for quote in quotes}:
        if evidence_id not in authorized:
            raise ModelOutputValidationError(
                "模型引用了当前授权文档快照之外的 Evidence。"
            )

    for quote in quotes:
        segment = authorized[quote.evidence_id]
        if quote.quote not in segment.content:
            raise ModelOutputValidationError("模型引用的原文片段与解析内容不匹配。")
        digest = hashlib.sha256(quote.quote.encode("utf-8")).hexdigest()
        resolved[(quote.evidence_id, quote.quote)] = ResolvedEvidenceReference(
            evidence_id=quote.evidence_id,
            file_id=segment.file_id,
            file_version=segment.file_version,
            locator=segment.locator,
            excerpt=quote.quote,
            content_hash=digest,
        )

    for requirement in getattr(result, "requirements", []):
        if requirement.suggested_deadline is None:
            continue
        matching_segment = next(
            (
                authorized[item.evidence_id]
                for item in requirement.source_evidence
                if item.evidence_id in authorized
                and requirement.deadline_source_text in authorized[item.evidence_id].content
                and requirement.deadline_source_text in item.quote
            ),
            None,
        )
        if matching_segment is None:
            raise ModelOutputValidationError(
                "截止日期必须能在其引用的原文证据中逐字找到。"
            )

    for evidence_id in referenced_ids - {quote.evidence_id for quote in quotes}:
        segment = authorized[evidence_id]
        digest = hashlib.sha256(segment.content.encode("utf-8")).hexdigest()
        resolved[(evidence_id, segment.content)] = ResolvedEvidenceReference(
            evidence_id=evidence_id,
            file_id=segment.file_id,
            file_version=segment.file_version,
            locator=segment.locator,
            excerpt=segment.content,
            content_hash=digest,
        )

    return list(resolved.values())


def analyze_document(
    snapshot: DocumentSnapshot,
    *,
    provider: StructuredModelProvider | None = None,
) -> DocumentAIResponse:
    """Analyze an already authorized parser snapshot. This function does not persist data."""
    prompt_version = PROMPT_VERSIONS["analyze_document"]
    prompt = _prompt(prompt_version, snapshot, None)
    result, active_provider, input_hash = _run(
        prompt=prompt,
        output_model=DocumentAnalysisOutput,
        snapshot=snapshot,
        provider=provider,
    )
    evidence_refs = _verify_and_resolve_evidence(result, snapshot)
    return DocumentAIResponse(
        prompt_version=prompt_version,
        model=getattr(active_provider, "model_name", "unknown"),
        input_hash=input_hash,
        result=result,
        evidence_refs=evidence_refs,
    )


def extract_requirements(
    snapshot: DocumentSnapshot,
    *,
    analysis: DocumentAnalysisOutput | None = None,
    provider: StructuredModelProvider | None = None,
) -> RequirementAIResponse:
    """Return review-only requirement drafts; it cannot create or publish Tasks."""
    prompt_version = PROMPT_VERSIONS["extract_requirements"]
    prompt = _prompt(prompt_version, snapshot, analysis)
    result, active_provider, input_hash = _run(
        prompt=prompt,
        output_model=RequirementExtractionOutput,
        snapshot=snapshot,
        provider=provider,
    )
    evidence_refs = _verify_and_resolve_evidence(result, snapshot)
    return RequirementAIResponse(
        prompt_version=prompt_version,
        model=getattr(active_provider, "model_name", "unknown"),
        input_hash=input_hash,
        result=result,
        evidence_refs=evidence_refs,
    )


def example_document_snapshot() -> DocumentSnapshot:
    """Small synthetic input for local integration checks; contains no persisted data."""
    return DocumentSnapshot(
        project_id=1,
        file_id=10,
        file_version="v1",
        filename="sample-requirements.txt",
        file_type="text/plain",
        parser_status="parsed",
        segments=[
            DocumentSegment(
                evidence_id=501,
                file_id=10,
                file_version="v1",
                content_kind="text",
                locator={"kind": "text", "line_start": 1, "line_end": 2},
                content=(
                    "The supplier must provide a German instruction manual. "
                    "Delivery date: 2026-12-15."
                ),
            )
        ],
    )
