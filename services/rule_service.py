import hashlib
import json
import re
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from core.config import settings
from core.db import session_context
from core.errors import RuleSourceError
from core.models import RuleCheckRecord
from core.schemas import RuleDefinition, RuleEvaluation

RULES_FILE = settings.root_dir / "data" / "rules.json"


def load_rules(path: Path = RULES_FILE) -> list[RuleDefinition]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return TypeAdapter(list[RuleDefinition]).validate_python(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise RuleSourceError(f"规则文件无法读取或格式无效：{exc}") from exc


def _source_reference(rule: RuleDefinition) -> str:
    return rule.source_url or rule.source_file


def _source_is_usable(rule: RuleDefinition) -> tuple[bool, str]:
    if rule.source_type == "unverified":
        return False, "规则来源尚未核实，仅保留为待确认项。"
    reference = _source_reference(rule)
    if not reference or not rule.version.strip():
        return False, "规则缺少来源或版本信息。"
    if rule.source_type == "internal_file":
        source_path = settings.root_dir / reference
        if not source_path.is_file():
            return False, "内部规则文件不存在。"
    return True, ""


def _evaluate_rule(rule: RuleDefinition, text: str) -> RuleEvaluation:
    source_reference = _source_reference(rule)
    usable, reason = _source_is_usable(rule)
    if not usable:
        return RuleEvaluation(
            rule_id=rule.rule_id,
            market=rule.market,
            scenario=rule.scenario,
            rule_type=rule.rule_type,
            status="not_covered",
            explanation=reason,
            source_reference=source_reference or "待确认",
            source_version=rule.version,
        )

    if rule.check_type == "forbidden_regex":
        match = re.search(rule.pattern, text)
        status = "failed" if match else "passed"
        explanation = "命中禁止表达。" if match else "未命中该规则配置的禁止表达。"
        matched_text = match.group(0) if match else ""
    elif rule.check_type == "max_length":
        limit = rule.max_length
        if limit is None:
            return RuleEvaluation(
                rule_id=rule.rule_id,
                market=rule.market,
                scenario=rule.scenario,
                rule_type=rule.rule_type,
                status="not_covered",
                explanation="规则缺少最大长度参数。",
                source_reference=source_reference,
                source_version=rule.version,
            )
        status = "failed" if len(text) > limit else "passed"
        explanation = f"当前长度 {len(text)}，规则上限 {limit}。"
        matched_text = text[:200] if status == "failed" else ""
    elif rule.check_type == "required_term_groups":
        normalized = text.casefold()
        missing_groups = [
            group
            for group in rule.required_term_groups
            if not any(term.casefold() in normalized for term in group)
        ]
        status = "failed" if missing_groups else "passed"
        explanation = (
            "缺少字段组：" + "；".join("/".join(group) for group in missing_groups)
            if missing_groups
            else "所需信息组均有文本命中，仍需人工核对内容是否准确。"
        )
        matched_text = ""
    else:
        status = "warning"
        explanation = "该规则只能人工检查，程序未给出通过结论。"
        matched_text = ""

    return RuleEvaluation(
        rule_id=rule.rule_id,
        market=rule.market,
        scenario=rule.scenario,
        rule_type=rule.rule_type,
        status=status,
        matched_text=matched_text,
        explanation=explanation,
        source_reference=source_reference,
        source_version=rule.version,
        requires_human_review=True,
    )


def run_rule_checks(
    *,
    project_id: int,
    market: str,
    scenario: str,
    text: str,
    rules_path: Path = RULES_FILE,
    session: Session | None = None,
) -> list[RuleEvaluation]:
    if not text.strip():
        raise ValueError("待检查文本不能为空。")
    rules = [
        rule
        for rule in load_rules(rules_path)
        if rule.scenario == scenario and rule.market in {market, "ALL"}
    ]
    if not rules:
        raise RuleSourceError("当前市场和业务场景没有已配置规则。")
    results = [_evaluate_rule(rule, text) for rule in rules]
    input_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    by_id = {rule.rule_id: rule for rule in rules}
    with session_context(session) as db:
        for result in results:
            rule = by_id[result.rule_id]
            db.add(
                RuleCheckRecord(
                    project_id=project_id,
                    rule_id=result.rule_id,
                    market=market,
                    scenario=scenario,
                    source_type=rule.source_type,
                    source_reference=result.source_reference,
                    source_version=result.source_version,
                    status=result.status,
                    matched_text=result.matched_text,
                    explanation=result.explanation,
                    input_hash=input_hash,
                    human_review_status="pending_review",
                )
            )
        db.flush()
    return results
