from datetime import date

import pytest

from core.errors import ModelOutputValidationError, ModelTimeoutError
from core.models import AiRun, Task
from services.task_recommendation_ai_service import recommend_tasks, request_fingerprint
from services.task_recommendation_schemas import TaskRecommendationInput


class FakeProvider:
    model_name = "mock-task-model"
    max_attempts = 1

    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate(self, *, prompt, schema, repair_from=None):
        self.calls.append((prompt, schema, repair_from))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def make_request(**overrides):
    payload = {
        "project_id": 7,
        "project_context": "新品出口项目",
        "findings": [
            {
                "finding_id": 11,
                "project_id": 7,
                "statement": "评价中出现包装破损反馈。",
                "evidence_ids": [101],
                "review_status": "accepted",
            }
        ],
        "requirements": [],
        "evidence": [
            {
                "evidence_id": 101,
                "project_id": 7,
                "excerpt": "Review 11: package arrived damaged",
                "locator": {"source": "review", "row": 11},
            }
        ],
        "members": [{"member_id": 31, "display_name": "品控", "role": "quality_control"}],
        "dependencies": [
            {
                "dependency_id": "packaging-check",
                "description": "确认包装规范",
                "evidence_ids": [101],
            }
        ],
    }
    payload.update(overrides)
    return TaskRecommendationInput.model_validate(payload)


def draft(**overrides):
    payload = {
        "draft_id": "draft-1",
        "task_title": "核对包装防护",
        "problem_background": "评价原文显示包装破损。",
        "objective": "确认包装风险并提出改进方案。",
        "suggested_role": "quality_control",
        "suggested_assignee_id": None,
        "priority": "high",
        "priority_basis": "客户评价已观察到破损，但原因尚未确认。",
        "deadline": None,
        "deadline_basis": None,
        "dependencies": ["packaging-check"],
        "deliverables": ["包装检查记录"],
        "acceptance_criteria": ["记录包含检查范围和结论"],
        "evidence": [{"evidence_id": 101, "quote": "package arrived damaged"}],
        "missing_information": ["订单批次"],
        "risk_notes": ["不能仅凭评价追责供应商"],
        "review_required": True,
    }
    payload.update(overrides)
    return payload


def output(*drafts):
    return {
        "drafts": list(drafts),
        "global_missing_information": [],
        "global_risk_notes": [],
        "review_required": True,
        "publishable": False,
    }


def test_recommends_review_only_draft_without_persisting_task(db_session):
    provider = FakeProvider(output(draft()))
    request = make_request()
    result = recommend_tasks(request, provider=provider)
    assert result.review_required is True
    assert result.publishable is False
    assert result.drafts[0].suggested_assignee_id is None
    assert result.drafts[0].deadline is None
    assert db_session.query(Task).count() == 0
    assert db_session.query(AiRun).count() == 0
    assert len(provider.calls) == 1


def test_recommends_multiple_drafts_and_preserves_dependencies():
    first = draft()
    second = draft(
        draft_id="draft-2",
        task_title="复核改进方案",
        dependencies=["draft-1"],
    )
    result = recommend_tasks(make_request(), provider=FakeProvider(output(first, second)))
    assert [item.draft_id for item in result.drafts] == ["draft-1", "draft-2"]
    assert result.drafts[1].dependencies == ["draft-1"]


def test_evidence_quote_must_match_authorized_excerpt():
    bad = draft(evidence=[{"evidence_id": 101, "quote": "supplier caused it"}])
    with pytest.raises(ModelOutputValidationError, match="Evidence"):
        recommend_tasks(make_request(), provider=FakeProvider(output(bad)))


def test_assignee_must_be_authorized_member():
    with pytest.raises(ModelOutputValidationError, match="成员集合"):
        recommend_tasks(
            make_request(), provider=FakeProvider(output(draft(suggested_assignee_id=999)))
        )


def test_deadline_requires_exact_evidence_basis():
    bad = draft(deadline=date(2026, 12, 15), deadline_basis="2026-12-15")
    with pytest.raises(ModelOutputValidationError, match="截止日期依据"):
        recommend_tasks(make_request(), provider=FakeProvider(output(bad)))


def test_unknown_dependency_and_self_dependency_are_rejected():
    with pytest.raises(ModelOutputValidationError, match="未授权"):
        recommend_tasks(
            make_request(), provider=FakeProvider(output(draft(dependencies=["invented"])))
        )
    with pytest.raises(ModelOutputValidationError, match="自身"):
        recommend_tasks(
            make_request(), provider=FakeProvider(output(draft(dependencies=["draft-1"])))
        )


def test_duplicate_draft_ids_are_rejected():
    with pytest.raises(ModelOutputValidationError, match="重复"):
        recommend_tasks(make_request(), provider=FakeProvider(output(draft(), draft())))


def test_invalid_output_and_provider_failure_are_mapped():
    with pytest.raises(ModelOutputValidationError):
        recommend_tasks(make_request(), provider=FakeProvider({"drafts": []}))
    with pytest.raises(ModelTimeoutError):
        recommend_tasks(make_request(), provider=FakeProvider(TimeoutError()))


def test_input_scope_and_empty_reviewed_source_are_rejected():
    with pytest.raises(ValueError, match="项目"):
        make_request(
            findings=[
                {
                    "finding_id": 11,
                    "project_id": 99,
                    "statement": "x",
                    "evidence_ids": [101],
                    "review_status": "accepted",
                }
            ]
        )
    with pytest.raises(ValueError, match="至少需要"):
        make_request(findings=[], requirements=[])


def test_request_fingerprint_is_stable():
    request = make_request()
    assert request_fingerprint(request) == request_fingerprint(request.model_copy(deep=True))
