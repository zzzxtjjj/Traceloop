import json

import pytest
from sqlalchemy import func, select

from core.errors import RuleSourceError
from core.models import Project, RuleCheckRecord
from services.rule_service import run_rule_checks


def make_project(session) -> Project:
    project = Project(
        name="Rule project",
        product_name="Demo product",
        access_code_hash="test",
        markets_json='["US", "DE"]',
    )
    session.add(project)
    session.flush()
    return project


def test_platform_rules_are_market_scoped_and_keep_unverified_rule_pending(
    db_session,
) -> None:
    project = make_project(db_session)
    results = run_rule_checks(
        project_id=project.id,
        market="DE",
        scenario="platform_product",
        text="FREE SHIPPING " + "A" * 150,
        session=db_session,
    )
    by_id = {item.rule_id: item for item in results}
    assert by_id["GMC-TITLE-LENGTH-001"].status == "failed"
    assert by_id["GMC-TITLE-PROMO-002"].status == "failed"
    assert by_id["GMC-TITLE-PROMO-002"].matched_text == "FREE SHIPPING"
    assert by_id["LEGACY-DE-TONE-UNVERIFIED"].status == "not_covered"
    assert "尚未核实" in by_id["LEGACY-DE-TONE-UNVERIFIED"].explanation


def test_de_contract_check_requires_total_and_delivery_cost_information(db_session) -> None:
    project = make_project(db_session)
    failed = run_rule_checks(
        project_id=project.id,
        market="DE",
        scenario="consumer_contract",
        text="Gesamtpreis: 29 EUR inklusive MwSt.",
        session=db_session,
    )
    assert failed[0].status == "failed"
    assert "lieferkosten" in failed[0].explanation.casefold()

    passed = run_rule_checks(
        project_id=project.id,
        market="DE",
        scenario="consumer_contract",
        text="Gesamtpreis: 29 EUR inklusive MwSt. Lieferkosten: 4 EUR.",
        session=db_session,
    )
    assert passed[0].status == "passed"
    assert passed[0].requires_human_review is True


def test_internal_procurement_rule_is_not_presented_as_law(db_session) -> None:
    project = make_project(db_session)
    results = run_rule_checks(
        project_id=project.id,
        market="US",
        scenario="procurement",
        text="FOB Ningbo; payment 30/70; quote valid until 2026-11-30.",
        session=db_session,
    )
    assert results[0].status == "passed"
    assert results[0].rule_type == "internal_standard"
    assert results[0].source_reference.endswith("INTERNAL_PROCUREMENT_STANDARD.md")
    stored = db_session.scalar(select(func.count(RuleCheckRecord.id)))
    assert stored == 1


def test_missing_rule_source_is_not_covered(db_session, tmp_path) -> None:
    project = make_project(db_session)
    path = tmp_path / "rules.json"
    path.write_text(
        json.dumps(
            [
                {
                    "rule_id": "NO-SOURCE",
                    "market": "US",
                    "scenario": "platform_product",
                    "rule_type": "platform_policy",
                    "content": "demo",
                    "source_type": "unverified",
                    "source_title": "unknown",
                    "version": "unverified",
                    "source_checked_at": "2026-10-25",
                    "check_type": "manual",
                    "severity": "yellow",
                }
            ]
        ),
        encoding="utf-8",
    )
    results = run_rule_checks(
        project_id=project.id,
        market="US",
        scenario="platform_product",
        text="Example title",
        rules_path=path,
        session=db_session,
    )
    assert results[0].status == "not_covered"
    assert results[0].source_reference == "待确认"


def test_market_without_rules_returns_clear_error(db_session) -> None:
    project = make_project(db_session)
    with pytest.raises(RuleSourceError, match="没有已配置规则"):
        run_rule_checks(
            project_id=project.id,
            market="US",
            scenario="consumer_contract",
            text="Total price 20 USD, shipping cost 3 USD.",
            session=db_session,
        )
