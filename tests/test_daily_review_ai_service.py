from datetime import UTC, datetime

import pytest

from core.errors import ModelOutputValidationError, ModelTimeoutError
from core.models import AiRun, Task
from services.daily_review_ai_schemas import DailyReviewSnapshot
from services.daily_review_ai_service import summarize_daily_report


class FakeProvider:
    model_name = "mock-daily-model"
    max_attempts = 1

    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate(self, *, prompt, schema, repair_from=None):
        self.calls.append((prompt, schema, repair_from))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def make_snapshot(**overrides):
    payload = {
        "project_id": 7,
        "period_start": "2026-10-30",
        "period_end": "2026-10-31",
        "project_context": "出口项目",
        "reports": [
            {
                "report_id": 1,
                "project_id": 7,
                "report_date": "2026-10-31",
                "submitter_id": 10,
                "submitter_name": "张三",
                "role": "quality_control",
                "task_id": 101,
                "completed_text": "已完成包装检查",
                "blocker_text": "",
                "next_plan": "提交检查记录",
                "evidence_ids": [501],
            },
            {
                "report_id": 2,
                "project_id": 7,
                "report_date": "2026-10-31",
                "submitter_id": 11,
                "submitter_name": "李四",
                "role": "logistics",
                "task_id": 102,
                "completed_text": "等待承运商确认",
                "blocker_text": "承运商未回复",
                "next_plan": "明日跟进",
                "evidence_ids": [502],
            },
        ],
        "tasks": [
            {
                "task_id": 101,
                "project_id": 7,
                "title": "包装检查",
                "status": "doing",
                "owner_role": "quality_control",
                "due_at": None,
                "dependency_ids": [],
                "overdue": False,
                "blocked": False,
            },
            {
                "task_id": 102,
                "project_id": 7,
                "title": "物流确认",
                "status": "blocked",
                "owner_role": "logistics",
                "due_at": datetime(2026, 10, 30, tzinfo=UTC).isoformat(),
                "dependency_ids": [101],
                "overdue": True,
                "blocked": True,
            },
        ],
        "submissions": [
            {
                "submission_id": 201,
                "project_id": 7,
                "task_id": 101,
                "content": "包装检查记录已提交",
                "review_status": "pending_review",
                "reviewer_note": "",
                "evidence_ids": [501],
            }
        ],
        "evidence": [
            {
                "evidence_id": 501,
                "project_id": 7,
                "source_type": "daily_report",
                "source_id": 1,
                "excerpt": "已完成包装检查\n包装检查记录已提交",
            },
            {
                "evidence_id": 502,
                "project_id": 7,
                "source_type": "daily_report",
                "source_id": 2,
                "excerpt": "承运商未回复",
            },
        ],
    }
    payload.update(overrides)
    return DailyReviewSnapshot.model_validate(payload)


def review_output(**overrides):
    payload = {
        "progress_summary": "包装检查已提交但尚未验收，物流确认被阻塞。",
        "main_work": ["包装检查"],
        "accepted_deliverables": [],
        "pending_acceptance": [101],
        "overdue_tasks": [102],
        "blocked_tasks": [102],
        "dependency_risks": ["物流确认依赖包装检查"],
        "delivery_impacts": ["可能影响交付安排"],
        "risk_basis": [{"evidence_id": 502, "quote": "承运商未回复"}],
        "member_summaries": [
            {
                "submitter_name": "张三",
                "role": "quality_control",
                "summary": "声称完成包装检查，但交付仍待验收。",
                "claimed_completed": [101],
                "pending_acceptance": [101],
                "evidence": [{"evidence_id": 501, "quote": "已完成包装检查"}],
            },
            {
                "submitter_name": "李四",
                "role": "logistics",
                "summary": "承运商尚未回复。",
                "claimed_completed": [],
                "pending_acceptance": [],
                "evidence": [{"evidence_id": 502, "quote": "承运商未回复"}],
            },
        ],
        "discrepancies": ["日报声称完成不等于任务已验收"],
        "missing_information": ["承运商预计回复时间"],
        "coordination_suggestions": [
            {
                "priority": "high",
                "action": "协调品控完成包装记录验收并跟进物流",
                "recommended_role": "project_manager",
                "order": 1,
                "deliverables": ["验收结论", "物流回复记录"],
                "acceptance_criteria": ["验收状态和回复时间已记录"],
                "rationale": "当前任务有待验收和阻塞状态。",
                "evidence": [{"evidence_id": 502, "quote": "承运商未回复"}],
            }
        ],
        "evidence": [{"evidence_id": 501, "quote": "包装检查记录已提交"}],
        "review_required": True,
        "publishable": False,
    }
    payload.update(overrides)
    return payload


def test_summarizes_multiple_members_and_preserves_acceptance_boundary(db_session):
    snapshot = make_snapshot()
    result = summarize_daily_report(snapshot, provider=FakeProvider(review_output()))
    assert len(result.member_summaries) == 2
    assert result.pending_acceptance == [101]
    assert result.accepted_deliverables == []
    assert result.overdue_tasks == [102]
    assert result.blocked_tasks == [102]
    assert result.review_required is True
    assert result.publishable is False
    assert db_session.query(Task).count() == 0
    assert db_session.query(AiRun).count() == 0


def test_unaccepted_submission_cannot_be_reported_as_accepted():
    bad = review_output(accepted_deliverables=[101])
    with pytest.raises(ModelOutputValidationError, match="未验收"):
        summarize_daily_report(make_snapshot(), provider=FakeProvider(bad))


def test_program_risk_flags_cannot_be_invented_or_changed():
    with pytest.raises(ModelOutputValidationError, match="风险状态"):
        summarize_daily_report(
            make_snapshot(), provider=FakeProvider(review_output(overdue_tasks=[101]))
        )


def test_evidence_quotes_must_match_authorized_snapshot():
    bad = review_output(evidence=[{"evidence_id": 501, "quote": "not in source"}])
    with pytest.raises(ModelOutputValidationError, match="Evidence"):
        summarize_daily_report(make_snapshot(), provider=FakeProvider(bad))


def test_project_scope_and_missing_reports_are_explicit():
    with pytest.raises(ValueError, match="当前项目"):
        make_snapshot(tasks=[{**make_snapshot().tasks[0].model_dump(), "project_id": 99}])
    empty = make_snapshot(reports=[])
    result = summarize_daily_report(empty, provider=FakeProvider(review_output()))
    assert result.review_required is True


def test_invalid_json_and_timeout_are_rejected():
    with pytest.raises(ModelOutputValidationError):
        summarize_daily_report(make_snapshot(), provider=FakeProvider("not json"))
    with pytest.raises(ModelTimeoutError):
        summarize_daily_report(make_snapshot(), provider=FakeProvider(TimeoutError()))


def test_no_evidence_result_is_rejected():
    empty = review_output(
        evidence=[],
        risk_basis=[],
        member_summaries=[],
        coordination_suggestions=[],
    )
    with pytest.raises(ModelOutputValidationError, match="至少引用"):
        summarize_daily_report(make_snapshot(), provider=FakeProvider(empty))
