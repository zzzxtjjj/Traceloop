"""Evidence-grounded project review; persistence and status changes stay in B7."""

import json
from pathlib import Path

from core.errors import ModelOutputValidationError
from services.ai_service import StructuredModelProvider, run_structured_model
from services.daily_review_ai_schemas import DailyProjectReviewResult, DailyReviewSnapshot
from services.model_provider import OpenAICompatibleProvider

PROMPT_VERSION = "daily_project_review_v1"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / f"{PROMPT_VERSION}.txt"


def _prompt(snapshot: DailyReviewSnapshot) -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip() + "\n" + json.dumps(
        snapshot.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
    )


def _verify_result(
    result: DailyProjectReviewResult, snapshot: DailyReviewSnapshot
) -> DailyProjectReviewResult:
    evidence = {item.evidence_id: item for item in snapshot.evidence}
    task_ids = {item.task_id for item in snapshot.tasks}
    accepted = {
        item.task_id for item in snapshot.submissions if item.review_status == "accepted"
    }
    pending = {
        item.task_id for item in snapshot.submissions if item.review_status == "pending_review"
    }
    overdue = {item.task_id for item in snapshot.tasks if item.overdue}
    blocked = {item.task_id for item in snapshot.tasks if item.blocked}
    if not set(result.accepted_deliverables) <= accepted:
        raise ModelOutputValidationError("模型把未验收的交付记录标记为已验收。")
    if not set(result.pending_acceptance) <= pending:
        raise ModelOutputValidationError("模型引用了不存在的待验收任务。")
    if not set(result.overdue_tasks) <= overdue or not set(result.blocked_tasks) <= blocked:
        raise ModelOutputValidationError("模型修改或虚构了程序计算的任务风险状态。")
    referenced_task_ids = [
        *result.accepted_deliverables,
        *result.pending_acceptance,
        *result.overdue_tasks,
        *result.blocked_tasks,
    ]
    for task_id in referenced_task_ids:
        if task_id not in task_ids:
            raise ModelOutputValidationError("模型引用了当前项目快照之外的任务。")
    quotes = [
        *result.evidence,
        *result.risk_basis,
        *(quote for item in result.member_summaries for quote in item.evidence),
        *(quote for item in result.coordination_suggestions for quote in item.evidence),
    ]
    if not quotes:
        raise ModelOutputValidationError("项目复盘必须至少引用一条授权 Evidence。")
    for quote in quotes:
        source = evidence.get(quote.evidence_id)
        if source is None or quote.quote not in source.excerpt:
            raise ModelOutputValidationError("模型日报复盘包含无效或不匹配的 Evidence 引用。")
    orders = [item.order for item in result.coordination_suggestions]
    if len(orders) != len(set(orders)):
        raise ModelOutputValidationError("协调建议的处理顺序不能重复。")
    return result


def summarize_daily_report(
    snapshot: DailyReviewSnapshot,
    *,
    provider: StructuredModelProvider | None = None,
) -> DailyProjectReviewResult:
    """Analyze an authorized snapshot without persisting or changing B7 state."""
    active = provider or OpenAICompatibleProvider.from_settings()
    result = run_structured_model(
        project_id=snapshot.project_id,
        run_type="daily_project_review",
        prompt_version=PROMPT_VERSION,
        prompt=_prompt(snapshot),
        evidence_ids=[item.evidence_id for item in snapshot.evidence],
        output_model=DailyProjectReviewResult,
        provider=active,
        record_run=False,
    )
    return _verify_result(result, snapshot)
