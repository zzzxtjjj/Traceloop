"""Evidence-grounded, persistence-neutral AI task recommendation."""

import hashlib
import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from core.errors import ModelOutputValidationError
from services.ai_service import StructuredModelProvider, run_structured_model
from services.model_provider import OpenAICompatibleProvider
from services.task_recommendation_schemas import (
    TaskRecommendationInput,
    TaskRecommendationOutput,
)

PROMPT_VERSION = "task_recommendation_v1"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / f"{PROMPT_VERSION}.txt"
OutputT = TypeVar("OutputT", bound=BaseModel)


def _prompt(request: TaskRecommendationInput) -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip() + "\n" + json.dumps(
        request.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
    )


def _verify_output(
    output: TaskRecommendationOutput, request: TaskRecommendationInput
) -> TaskRecommendationOutput:
    evidence = {item.evidence_id: item for item in request.evidence}
    member_ids = {item.member_id for item in request.members}
    dependency_ids = {item.dependency_id for item in request.dependencies}
    draft_ids = {draft.draft_id for draft in output.drafts}
    if len(draft_ids) != len(output.drafts):
        raise ModelOutputValidationError("模型生成了重复的任务草稿编号。")
    for draft in output.drafts:
        if (
            draft.suggested_assignee_id is not None
            and draft.suggested_assignee_id not in member_ids
        ):
            raise ModelOutputValidationError("模型建议了不在授权成员集合中的负责人。")
        unknown_dependencies = set(draft.dependencies) - dependency_ids - draft_ids
        if unknown_dependencies:
            raise ModelOutputValidationError("模型引用了未授权的任务依赖。")
        if draft.draft_id in draft.dependencies:
            raise ModelOutputValidationError("任务草稿不能依赖自身。")
        if len(draft.dependencies) != len(set(draft.dependencies)):
            raise ModelOutputValidationError("同一任务的依赖不能重复。")
        for quote in draft.evidence:
            source = evidence.get(quote.evidence_id)
            if source is None or quote.quote not in source.excerpt:
                raise ModelOutputValidationError("模型任务草稿包含无效或不匹配的 Evidence 引用。")
        if draft.deadline_basis and not any(
            draft.deadline_basis in evidence[quote.evidence_id].excerpt for quote in draft.evidence
        ):
            raise ModelOutputValidationError("截止日期依据必须出现在所引用的 Evidence 原文中。")
    return output


def recommend_tasks(
    request: TaskRecommendationInput,
    *,
    provider: StructuredModelProvider | None = None,
) -> TaskRecommendationOutput:
    """Return review-only drafts; never creates or publishes a Task."""
    prompt = _prompt(request)
    active = provider or OpenAICompatibleProvider.from_settings()
    result = run_structured_model(
        project_id=request.project_id,
        run_type="task_recommendation",
        prompt_version=PROMPT_VERSION,
        prompt=prompt,
        evidence_ids=[item.evidence_id for item in request.evidence],
        output_model=TaskRecommendationOutput,
        provider=active,
        record_run=False,
    )
    return _verify_output(result, request)


def request_fingerprint(request: TaskRecommendationInput) -> str:
    """Stable caller-side key for avoiding accidental duplicate UI requests."""
    return hashlib.sha256(
        json.dumps(request.model_dump(mode="json"), ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
