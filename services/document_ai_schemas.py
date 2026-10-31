"""Typed, persistence-neutral contracts for document AI analysis."""

import hashlib
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["pdf", "text", "spreadsheet", "document", "image", "unknown"]
    page: int | None = Field(default=None, ge=1)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    sheet: str | None = Field(default=None, max_length=120)
    cell_range: str | None = Field(default=None, max_length=120)
    paragraph_index: int | None = Field(default=None, ge=0)
    table_index: int | None = Field(default=None, ge=0)
    row_index: int | None = Field(default=None, ge=0)
    column_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_line_range(self):
        if self.line_start is not None and self.line_end is not None:
            if self.line_end < self.line_start:
                raise ValueError("line_end must not precede line_start")
        return self


class DocumentSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    evidence_id: int = Field(gt=0)
    file_id: int = Field(gt=0)
    file_version: str = Field(min_length=1, max_length=120)
    content_kind: Literal["text", "table"]
    locator: SourceLocation
    content: str = Field(min_length=1, max_length=20_000)
    content_hash: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")

    @model_validator(mode="after")
    def validate_content_hash(self):
        if self.content_hash:
            actual = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
            if actual.casefold() != self.content_hash.casefold():
                raise ValueError("content_hash must match the supplied Evidence excerpt")
        return self


class DocumentSnapshot(BaseModel):
    """Authorized, parsed input supplied by the business backend."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    project_id: int = Field(gt=0)
    file_id: int = Field(gt=0)
    file_version: str = Field(min_length=1, max_length=120)
    filename: str = Field(min_length=1, max_length=255)
    file_type: str = Field(min_length=1, max_length=30)
    parser_status: Literal["parsed", "partial"]
    segments: list[DocumentSegment] = Field(min_length=1, max_length=500)
    project_context: str = Field(default="", max_length=5_000)

    @model_validator(mode="after")
    def validate_snapshot_scope(self):
        seen: set[int] = set()
        for segment in self.segments:
            if segment.evidence_id in seen:
                raise ValueError("Evidence IDs must be unique within a document snapshot")
            if segment.file_id != self.file_id or segment.file_version != self.file_version:
                raise ValueError("Every segment must match the snapshot file and version")
            seen.add(segment.evidence_id)
        return self


class EvidenceQuote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    evidence_id: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=2_000)


EpistemicStatus = Literal["explicit", "inferred", "unknown"]
SuggestedRole = Literal[
    "project_manager",
    "export_sales",
    "procurement",
    "production",
    "quality_control",
    "product_engineering",
    "logistics",
]


class EvidenceStatement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    statement: str = Field(min_length=1, max_length=2_000)
    epistemic_status: EpistemicStatus
    evidence: list[EvidenceQuote] = Field(default_factory=list, max_length=20)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def require_evidence_for_claim(self):
        if self.epistemic_status != "unknown" and not self.evidence:
            raise ValueError("Explicit or inferred statements must cite source Evidence")
        return self


class RequirementSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    statement: str = Field(min_length=1, max_length=2_000)
    epistemic_status: EpistemicStatus
    evidence: list[EvidenceQuote] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_evidence_for_claim(self):
        if self.epistemic_status != "unknown" and not self.evidence:
            raise ValueError("Explicit or inferred signals must cite source Evidence")
        return self


class DocumentConflict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    description: str = Field(min_length=1, max_length=2_000)
    evidence: list[EvidenceQuote] = Field(min_length=2, max_length=20)
    review_required: Literal[True] = True


class InformationGap(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=1_000)
    related_evidence_ids: list[int] = Field(default_factory=list, max_length=20)


class DocumentRisk(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    description: str = Field(min_length=1, max_length=2_000)
    epistemic_status: Literal["explicit", "inferred", "unknown"]
    severity: Literal["low", "medium", "high", "unknown"]
    evidence: list[EvidenceQuote] = Field(default_factory=list, max_length=20)
    review_required: Literal[True] = True

    @model_validator(mode="after")
    def require_evidence_for_claim(self):
        if self.epistemic_status != "unknown" and not self.evidence:
            raise ValueError("Explicit or inferred risks must cite source Evidence")
        return self


class DocumentAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    summary: list[EvidenceStatement] = Field(max_length=30)
    important_facts: list[EvidenceStatement] = Field(max_length=100)
    requirement_signals: list[RequirementSignal] = Field(max_length=100)
    conflicts: list[DocumentConflict] = Field(max_length=50)
    missing_information: list[InformationGap] = Field(max_length=100)
    risks: list[DocumentRisk] = Field(max_length=100)
    review_required: Literal[True] = True
    publishable: Literal[False] = False


class RequirementDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    requirement_title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4_000)
    epistemic_status: EpistemicStatus
    suggested_role: SuggestedRole | None = None
    suggested_deadline: date | None = None
    deadline_source_text: str | None = Field(default=None, max_length=200)
    dependencies: list[str] = Field(default_factory=list, max_length=30)
    deliverables: list[str] = Field(default_factory=list, max_length=30)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=30)
    source_evidence: list[EvidenceQuote] = Field(default_factory=list, max_length=20)
    missing_information: list[str] = Field(default_factory=list, max_length=30)
    review_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_deadline_source(self):
        if (self.suggested_deadline is None) != (self.deadline_source_text is None):
            raise ValueError("A deadline and its exact source text must be supplied together")
        if self.epistemic_status != "unknown" and not self.source_evidence:
            raise ValueError("Explicit or inferred requirements must cite source Evidence")
        return self


class RequirementExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    requirements: list[RequirementDraft] = Field(max_length=100)
    missing_information: list[InformationGap] = Field(max_length=100)
    review_required: Literal[True] = True
    publishable: Literal[False] = False


class ResolvedEvidenceReference(BaseModel):
    """Source location copied from the authorized input, never generated by AI."""

    evidence_id: int
    file_id: int
    file_version: str
    locator: SourceLocation
    excerpt: str
    content_hash: str


class DocumentAIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    status: Literal["needs_review"] = "needs_review"
    prompt_version: str
    model: str
    input_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    result: DocumentAnalysisOutput
    evidence_refs: list[ResolvedEvidenceReference]
    review_required: Literal[True] = True
    publishable: Literal[False] = False


class RequirementAIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    status: Literal["needs_review"] = "needs_review"
    prompt_version: str
    model: str
    input_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    result: RequirementExtractionOutput
    evidence_refs: list[ResolvedEvidenceReference]
    review_required: Literal[True] = True
    publishable: Literal[False] = False
