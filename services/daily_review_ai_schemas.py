"""Persistence-neutral contracts for AI daily project review."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DailyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    evidence_id: int = Field(gt=0)
    project_id: int = Field(gt=0)
    source_type: Literal["daily_report", "task", "submission", "acceptance", "other"]
    source_id: int = Field(gt=0)
    excerpt: str = Field(min_length=1, max_length=4_000)


class DailyReportSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    report_id: int = Field(gt=0)
    project_id: int = Field(gt=0)
    report_date: date
    submitter_id: int | None = Field(default=None, gt=0)
    submitter_name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=80)
    task_id: int | None = Field(default=None, gt=0)
    completed_text: str = Field(default="", max_length=4_000)
    blocker_text: str = Field(default="", max_length=4_000)
    next_plan: str = Field(default="", max_length=4_000)
    evidence_ids: list[int] = Field(default_factory=list, max_length=30)


class TaskSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    task_id: int = Field(gt=0)
    project_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    status: str = Field(min_length=1, max_length=40)
    owner_role: str = Field(min_length=1, max_length=80)
    due_at: datetime | None = None
    dependency_ids: list[int] = Field(default_factory=list, max_length=30)
    overdue: bool = False
    blocked: bool = False


class SubmissionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    submission_id: int = Field(gt=0)
    project_id: int = Field(gt=0)
    task_id: int = Field(gt=0)
    content: str = Field(min_length=1, max_length=4_000)
    review_status: Literal["pending_review", "accepted", "rejected"]
    reviewer_note: str = Field(default="", max_length=2_000)
    evidence_ids: list[int] = Field(default_factory=list, max_length=30)


class DailyReviewSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_id: int = Field(gt=0)
    period_start: date
    period_end: date
    project_context: str = Field(default="", max_length=5_000)
    reports: list[DailyReportSnapshot] = Field(default_factory=list, max_length=200)
    tasks: list[TaskSnapshot] = Field(default_factory=list, max_length=200)
    submissions: list[SubmissionSnapshot] = Field(default_factory=list, max_length=200)
    evidence: list[DailyEvidence] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.period_end < self.period_start:
            raise ValueError("统计周期结束日期不能早于开始日期。")
        all_items = [*self.reports, *self.tasks, *self.submissions, *self.evidence]
        if any(item.project_id != self.project_id for item in all_items):
            raise ValueError("日报、任务、交付或 Evidence 不属于当前项目。")
        task_ids = {item.task_id for item in self.tasks}
        report_ids = {item.report_id for item in self.reports}
        submission_ids = {item.submission_id for item in self.submissions}
        evidence_ids = {item.evidence_id for item in self.evidence}
        if any(item.task_id is not None and item.task_id not in task_ids for item in self.reports):
            raise ValueError("日报引用了快照之外的任务。")
        if any(item.task_id not in task_ids for item in self.submissions):
            raise ValueError("交付记录引用了快照之外的任务。")
        refs = {
            evidence_id
            for item in [*self.reports, *self.submissions]
            for evidence_id in item.evidence_ids
        }
        if not refs <= evidence_ids:
            raise ValueError("日报或交付记录引用了未授权 Evidence。")
        if len(report_ids) != len(self.reports) or len(submission_ids) != len(self.submissions):
            raise ValueError("日报或交付记录编号不能重复。")
        return self


class DailyEvidenceQuote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    evidence_id: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=2_000)


class DailyMemberSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    submitter_name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=2_000)
    claimed_completed: list[int] = Field(default_factory=list, max_length=50)
    pending_acceptance: list[int] = Field(default_factory=list, max_length=50)
    evidence: list[DailyEvidenceQuote] = Field(default_factory=list, max_length=20)


class CoordinationSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    priority: Literal["low", "medium", "high", "urgent"]
    action: str = Field(min_length=1, max_length=2_000)
    recommended_role: str | None = Field(default=None, max_length=80)
    order: int = Field(ge=1, le=100)
    deliverables: list[str] = Field(min_length=1, max_length=20)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=20)
    rationale: str = Field(min_length=1, max_length=2_000)
    evidence: list[DailyEvidenceQuote] = Field(min_length=1, max_length=20)


class DailyProjectReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    progress_summary: str = Field(min_length=1, max_length=4_000)
    main_work: list[str] = Field(default_factory=list, max_length=50)
    accepted_deliverables: list[int] = Field(default_factory=list, max_length=100)
    pending_acceptance: list[int] = Field(default_factory=list, max_length=100)
    overdue_tasks: list[int] = Field(default_factory=list, max_length=100)
    blocked_tasks: list[int] = Field(default_factory=list, max_length=100)
    dependency_risks: list[str] = Field(default_factory=list, max_length=50)
    delivery_impacts: list[str] = Field(default_factory=list, max_length=50)
    risk_basis: list[DailyEvidenceQuote] = Field(default_factory=list, max_length=50)
    member_summaries: list[DailyMemberSummary] = Field(default_factory=list, max_length=100)
    discrepancies: list[str] = Field(default_factory=list, max_length=50)
    missing_information: list[str] = Field(default_factory=list, max_length=50)
    coordination_suggestions: list[CoordinationSuggestion] = Field(max_length=50)
    evidence: list[DailyEvidenceQuote] = Field(default_factory=list, max_length=100)
    review_required: Literal[True] = True
    publishable: Literal[False] = False
