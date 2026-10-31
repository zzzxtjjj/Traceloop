"""Persistence-neutral contracts for AI task recommendation drafts."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AuthorizedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    evidence_id: int = Field(gt=0)
    project_id: int = Field(gt=0)
    excerpt: str = Field(min_length=1, max_length=4_000)
    locator: dict[str, str | int] = Field(default_factory=dict)


class ReviewedFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    finding_id: int = Field(gt=0)
    project_id: int = Field(gt=0)
    statement: str = Field(min_length=1, max_length=4_000)
    evidence_ids: list[int] = Field(min_length=1, max_length=50)
    review_status: Literal["accepted", "revised"]


class ReviewedRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    requirement_id: str = Field(min_length=1, max_length=120)
    project_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4_000)
    evidence_ids: list[int] = Field(min_length=1, max_length=50)
    review_status: Literal["accepted", "revised"]


class AuthorizedMember(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    member_id: int = Field(gt=0)
    display_name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=80)


class DependencyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    dependency_id: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1_000)
    evidence_ids: list[int] = Field(default_factory=list, max_length=50)


class TaskRecommendationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    project_id: int = Field(gt=0)
    project_context: str = Field(default="", max_length=5_000)
    findings: list[ReviewedFinding] = Field(default_factory=list, max_length=50)
    requirements: list[ReviewedRequirement] = Field(default_factory=list, max_length=50)
    evidence: list[AuthorizedEvidence] = Field(min_length=1, max_length=200)
    members: list[AuthorizedMember] = Field(default_factory=list, max_length=100)
    dependencies: list[DependencyInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_scope(self):
        if not self.findings and not self.requirements:
            raise ValueError("至少需要一个已审核 Finding 或 Requirement。")
        if any(item.project_id != self.project_id for item in [*self.findings, *self.requirements]):
            raise ValueError("输入业务对象不属于当前项目。")
        if any(item.project_id != self.project_id for item in self.evidence):
            raise ValueError("Evidence 不属于当前项目。")
        evidence_ids = {item.evidence_id for item in self.evidence}
        referenced = {
            evidence_id
            for item in [*self.findings, *self.requirements]
            for evidence_id in item.evidence_ids
        }
        if not referenced <= evidence_ids:
            raise ValueError("业务对象引用了未授权的 Evidence。")
        dependency_evidence = {
            evidence_id for item in self.dependencies for evidence_id in item.evidence_ids
        }
        if not dependency_evidence <= evidence_ids:
            raise ValueError("依赖关系引用了未授权的 Evidence。")
        dependency_ids = [item.dependency_id for item in self.dependencies]
        if len(dependency_ids) != len(set(dependency_ids)):
            raise ValueError("依赖编号不能重复。")
        return self


class TaskEvidenceQuote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    evidence_id: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=2_000)


class TaskDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    draft_id: str = Field(min_length=1, max_length=120)
    task_title: str = Field(min_length=1, max_length=200)
    problem_background: str = Field(min_length=1, max_length=4_000)
    objective: str = Field(min_length=1, max_length=4_000)
    suggested_role: str | None = Field(default=None, max_length=80)
    suggested_assignee_id: int | None = Field(default=None, gt=0)
    priority: Literal["low", "medium", "high", "urgent"]
    priority_basis: str = Field(min_length=1, max_length=1_000)
    deadline: date | None = None
    deadline_basis: str | None = Field(default=None, max_length=500)
    dependencies: list[str] = Field(default_factory=list, max_length=30)
    deliverables: list[str] = Field(min_length=1, max_length=30)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=30)
    evidence: list[TaskEvidenceQuote] = Field(min_length=1, max_length=30)
    missing_information: list[str] = Field(default_factory=list, max_length=30)
    risk_notes: list[str] = Field(default_factory=list, max_length=30)
    review_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_deadline(self):
        if (self.deadline is None) != (self.deadline_basis is None):
            raise ValueError("截止日期和其依据必须同时提供或同时为空。")
        return self


class TaskRecommendationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    drafts: list[TaskDraft] = Field(min_length=1, max_length=50)
    global_missing_information: list[str] = Field(default_factory=list, max_length=50)
    global_risk_notes: list[str] = Field(default_factory=list, max_length=50)
    review_required: Literal[True] = True
    publishable: Literal[False] = False
